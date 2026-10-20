from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import PlainTextResponse

from .benchmarks.local import LocalBenchmark
from .config import Settings, load_models
from .schema import CreateRun, TERMINAL
from .service import enqueue, public_run, repository
from .storage import Conflict


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    if len(settings.admin_token) < 24 or settings.admin_token.startswith("replace-"):
        raise ValueError("SWE_ADMIN_TOKEN must be a fresh random token of at least 24 characters")
    repo = repository(settings)
    benchmark, profiles = LocalBenchmark(settings.task_dir), load_models(settings.models_file)
    app = FastAPI(title="Independent SWE Evaluation", version="0.1.0", docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.state.repository = repo
    bearer = HTTPBearer(auto_error=False)

    def administrator(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not credentials or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(
                credentials.credentials.encode(), settings.admin_token.encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "administrator authentication required",
                                headers={"WWW-Authenticate": "Bearer"})

    def find(run_id):
        record = repo.get(run_id)
        if record is None:
            raise HTTPException(404, "run not found")
        return record

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        # API readiness is independent of Docker and model credentials.
        repo.list(limit=1)
        return {"status": "ok", "database": "ready", "service": "swe-eval", "version": "0.1.0"}

    auth = [Depends(administrator)]

    @app.get("/api/v1/tasks", dependencies=auth)
    def tasks():
        return {"items": [task.public() for task in benchmark.list_tasks()]}

    @app.get("/api/v1/models", dependencies=auth)
    def models():
        return {"items": [profile.public() for profile in profiles.values()]}

    @app.post("/api/v1/runs", status_code=202, dependencies=auth)
    def create_run(body: CreateRun):
        try:
            record = enqueue(repo, benchmark, profiles, body.task_id, body.model_profile_id)
        except KeyError:
            raise HTTPException(422, "unknown trusted task or model profile") from None
        return public_run(record)

    @app.get("/api/v1/runs", dependencies=auth)
    def runs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return {"items": [public_run(record) for record in repo.list(limit, offset)], "limit": limit, "offset": offset}

    @app.get("/api/v1/runs/{run_id}", dependencies=auth)
    def run(run_id: str):
        return public_run(find(run_id))

    @app.get("/api/v1/runs/{run_id}/logs", dependencies=auth)
    def logs(run_id: str, after: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000)):
        find(run_id)
        items = repo.logs(run_id, after, limit)
        return {"items": items, "next_after": items[-1]["seq"] if items else after}

    @app.get("/api/v1/runs/{run_id}/patch", dependencies=auth, response_class=PlainTextResponse)
    def patch(run_id: str):
        record = find(run_id)
        return PlainTextResponse(repo.patch(run_id), headers={
            "Content-Disposition": f'attachment; filename="{record["id"]}.patch"'})

    @app.post("/api/v1/runs/{run_id}/cancel", dependencies=auth, status_code=202)
    def cancel(run_id: str):
        find(run_id)
        try:
            return public_run(repo.cancel(run_id))
        except Conflict as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/runs/{run_id}/retry", dependencies=auth, status_code=202)
    def retry(run_id: str):
        record = find(run_id)
        if record["state"] not in TERMINAL or record["mode"] != "agent":
            raise HTTPException(409, "only terminal agent runs can be retried")
        try:
            return public_run(enqueue(repo, benchmark, profiles, record["task"]["id"], record["model"]["id"], parent_id=run_id))
        except KeyError:
            raise HTTPException(422, "task or profile is no longer configured") from None

    return app

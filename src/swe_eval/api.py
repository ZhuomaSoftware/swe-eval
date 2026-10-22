from __future__ import annotations

import hmac
import hashlib
import json
import time
import secrets
import io
import csv
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import PlainTextResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from .benchmarks.local import LocalBenchmark
from .benchmarks.official import TaskRegistry, Catalogue, DATASET, SUBSET
from .config import ConfigurationError, Settings, load_models
from .schema import CreateRun, TERMINAL, RunState
from .service import enqueue, public_run, repository
from .storage import Conflict
from .center_schema import BatchSubmission, Login
from .center import submit_batch
from . import sessions
from .analytics import comparison, shadow_export, summary, records, eligible_attempt, trusted_attempt
from .integrations import synchronize
from .diagnostics import public_log
from .exports import csv_cell


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    if len(settings.admin_token) < 24 or settings.admin_token.startswith("replace-"):
        raise ConfigurationError("SWE_ADMIN_TOKEN: set a fresh random token of at least 24 characters; do not use the replace- placeholder")
    repo = repository(settings)
    benchmark, profiles = TaskRegistry(settings), load_models(settings.models_file)
    app = FastAPI(title="Independent SWE Evaluation", version="0.2.0", docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.state.repository = repo
    bearer = HTTPBearer(auto_error=False)

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        # Never serialize input, ctx, request body or the exception repr. These
        # may contain credentials even when the field itself is unsupported.
        details = [{key: item[key] for key in ("type", "loc", "msg")}
                   for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    def administrator(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials and credentials.scheme.lower() == 'bearer' and hmac.compare_digest(
                credentials.credentials.encode(), settings.admin_token.encode()):
            return
        token = request.cookies.get(sessions.COOKIE)
        if sessions.authorized(repo, token):
            if request.method not in ('GET','HEAD','OPTIONS'):
                if request.headers.get('origin') != settings.public_origin or not sessions.authorized(repo,token,request.headers.get('x-csrf-token','')):
                    raise HTTPException(403,'CSRF validation failed')
            return
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
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if response.status_code>=400 and request.url.path.startswith('/api/'):
            repo.event('http_error', str(response.status_code))
        return response

    @app.get("/health")
    def health():
        # API readiness is independent of Docker and model credentials.
        repo.list(limit=1)
        return {"status": "ok", "database": "ready", "service": "swe-eval", "version": "0.2.0"}

    auth = [Depends(administrator)]
    from .management import current_profiles
    from .management_api import install_management
    install_management(app,settings,repo,benchmark,auth)
    def available_profiles():return current_profiles(settings,repo)

    @app.get("/api/v1/tasks", dependencies=auth)
    def tasks(dataset: str | None=None, repo_filter: str | None=Query(None,alias="repo"), validation_status: str | None=None, instance_id: str | None=None, benchmark_type: str | None=None, subset: str | None=None):
        selected=benchmark.list_tasks()
        selected=[t for t in selected if (not dataset or t.benchmark==dataset) and (not repo_filter or getattr(t,"repo",None)==repo_filter) and (not validation_status or getattr(t,"validation_status","validated")==validation_status) and (not instance_id or instance_id.lower() in getattr(t,"instance_id",t.id).lower()) and (not benchmark_type or getattr(t,"benchmark_type","local")==benchmark_type) and (not subset or getattr(t,"subset",None)==subset)]
        return {"items": [task.public() for task in selected],"total":len(selected)}

    @app.get("/api/v1/datasets",dependencies=auth)
    def datasets():
        catalogue=benchmark.catalogue
        selected=catalogue.list_tasks()
        from collections import Counter
        return {"schema_version":"swe-dataset-catalogue-v1","items":[{"dataset":DATASET,"revisions":catalogue.revisions(),"imported":len(selected),"validation_counts":dict(Counter(t.validation_status for t in selected)),"environment_ready":sum(t.environment_ready for t in selected),"subset":SUBSET,"subset_members":sum(t.subset==SUBSET for t in selected),"label":"SWE-bench Verified — Internal 20-Instance Subset","harness_version":"5.0.2","grading_protocol":"swebench-official-v5","trust_limit":"Official harness parses candidate test logs; this is distinct from isolated grading-v2."}]}

    @app.get("/api/v1/models", dependencies=auth)
    def models():
        return {"items": [dict(profile.public(), endpoint_identity=hashlib.sha256(profile.base_url.rstrip('/').encode()).hexdigest()[:16]) for profile in available_profiles().values()]}

    @app.post("/api/v1/runs", status_code=202, dependencies=auth)
    def create_run(body: CreateRun):
        try:
            record = enqueue(repo, benchmark, available_profiles(), body.task_id, body.model_profile_id, max_pending=settings.max_pending_runs)
        except KeyError:
            raise HTTPException(422, "unknown trusted task or model profile") from None
        except ValueError:
            raise HTTPException(422,"official task environment is not validated for execution") from None
        return public_run(record)

    @app.get("/api/v1/runs", dependencies=auth)
    def runs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=2**63-1),
             model_profile_id: str | None = None, upstream_id: str | None = None, benchmark: str | None = None,
             state: str | None = None, batch_id: str | None = None, grading_protocol: str | None = None,
             created_after: float | None = Query(None,ge=0,le=253402300799),
             created_before: float | None = Query(None,ge=0,le=253402300799)):
        if state and state not in {x.value for x in RunState}:
            raise HTTPException(422,'unknown run state')
        page = repo.query_runs(limit=limit,offset=offset,model_profile_id=model_profile_id,upstream_id=upstream_id,
            benchmark=benchmark,state=state,batch_id=batch_id,grading_protocol=grading_protocol,
            created_after=created_after,created_before=created_before)
        page['items']=[public_run(r) for r in page['items']]
        return page

    @app.get("/api/v1/runs/{run_id}", dependencies=auth)
    def run(run_id: str):
        return public_run(find(run_id))

    @app.get("/api/v1/runs/{run_id}/logs", dependencies=auth)
    def logs(run_id: str, after: int = Query(0, ge=0, le=2**63-1), limit: int = Query(200, ge=1, le=1000)):
        find(run_id)
        items = [public_log(item) for item in repo.logs(run_id, after, limit)]
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
            return public_run(enqueue(repo, benchmark, available_profiles(), record["task"]["id"], record["model"]["id"], parent_id=run_id, max_pending=settings.max_pending_runs))
        except KeyError:
            raise HTTPException(422, "task or profile is no longer configured") from None

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse(status_code=409, content={'detail': str(error)})

    @app.post('/api/v1/session')
    def login(body: Login, request: Request, response: Response):
        if request.headers.get('origin') != settings.public_origin:
            raise HTTPException(403,'same-origin login required')
        if not settings.ui_password_hash:
            raise HTTPException(503,'dashboard login disabled; configure SWE_UI_PASSWORD_HASH')
        with repo.connect() as db:
            failures=db.execute("SELECT count(*) FROM operational_events WHERE kind='login_failed' AND at>?",(time.time()-60,)).fetchone()[0]
        if failures>=10:
            raise HTTPException(429,'login rate limit; retry in one minute')
        if not sessions.verify_password(body.password,settings.ui_password_hash):
            repo.event('login_failed')
            raise HTTPException(401,'invalid administrator credentials')
        token,csrf,expires=sessions.issue(repo)
        response.set_cookie(sessions.COOKIE,token,max_age=8*3600,httponly=True,secure=settings.cookie_secure,samesite='strict',path='/')
        return {'role':'administrator','csrf_token':csrf,'expires_at':expires}

    @app.get('/api/v1/session',dependencies=auth)
    def current_session(request: Request):
        token=request.cookies.get(sessions.COOKIE)
        csrf=secrets.token_urlsafe(32)
        with repo.connect(write=True) as db:
            db.execute('UPDATE admin_sessions SET csrf_hash=? WHERE token_hash=?',(sessions.hashed(csrf),sessions.hashed(token or '')))
        return {'role':'administrator','csrf_token':csrf}

    @app.delete('/api/v1/session',dependencies=auth)
    def logout(request: Request,response: Response):
        with repo.connect(write=True) as db:
            db.execute('DELETE FROM admin_sessions WHERE token_hash=?',(sessions.hashed(request.cookies.get(sessions.COOKIE,'')),))
        response.delete_cookie(sessions.COOKIE,path='/')
        return {'status':'logged_out'}

    @app.get('/api/v1/overview',dependencies=auth)
    def overview():
        all_runs=list(records(repo))
        trusted=[r for r in all_runs if trusted_attempt(r)]
        diagnostic=[r for r in all_runs if eligible_attempt(r)]
        return {'total_runs':len(all_runs),'states':dict(__import__('collections').Counter(r['state'] for r in all_runs)),
                'trusted_metrics':summary(trusted), 'diagnostic_metrics':summary(diagnostic),
                'trusted_metrics_origin':'live', 'legacy_or_unattributed_runs':sum(not eligible_attempt(r) for r in all_runs),
                'non_live_diagnostic_runs':sum(not trusted_attempt(r) for r in diagnostic),
                'operations':repo.operations(),
                'resources':{'available_models':len(available_profiles()),'imported_official_tasks':len(benchmark.catalogue.list_tasks()),'validated_official_tasks':sum(t.environment_ready for t in benchmark.catalogue.list_tasks())}}

    @app.get('/api/v1/system',dependencies=auth)
    def system():
        from .administration_jobs import AdministrativeJobs
        result=repo.operations();result['administrative_jobs']=AdministrativeJobs(repo,settings).list()
        return result

    @app.post('/api/v1/batches',dependencies=auth,status_code=202)
    def create_batch(body: BatchSubmission):
        try:
            return submit_batch(repo,benchmark,available_profiles(),body,settings)
        except KeyError:
            raise HTTPException(422,'unknown trusted task or model profile') from None
        except ValueError as error:
            raise HTTPException(422,str(error)) from None

    @app.get('/api/v1/batches',dependencies=auth)
    def batches(limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0,le=2**63-1)):
        return {'items':repo.batches(limit,offset)}

    @app.get('/api/v1/batches/{batch_id}',dependencies=auth)
    def batch(batch_id: str):
        value=repo.batch(batch_id)
        if value is None:
            raise HTTPException(404,'batch not found')
        return value

    @app.post('/api/v1/batches/{batch_id}/cancel',dependencies=auth,status_code=202)
    def cancel_batch(batch_id: str):
        try:
            return repo.cancel_batch(batch_id)
        except KeyError:
            raise HTTPException(404,'batch not found') from None

    @app.get('/api/v1/comparison',dependencies=auth)
    def compare(profile_ids: str | None=None,batch_id: str | None=None):
        return comparison(repo,profile_ids=profile_ids.split(',') if profile_ids else None,batch_id=batch_id)

    @app.get('/api/v1/comparison/export',dependencies=auth)
    def export(format: str=Query('json',pattern='^(json|csv)$'),profile_ids: str | None=None,batch_id: str | None=None):
        value=compare(profile_ids,batch_id)
        if format=='json':
            return JSONResponse(value,headers={'Content-Disposition':'attachment; filename="swe-comparison.json"'})
        output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['schema_version','benchmark','dataset_version','grading_protocol','harness_revision','subset','official_harness_version','agent_version','profile_id','model_id','upstream_id','reasoning_effort','task_count','matched_task_count','attempts','valid_evaluations','resolved_rate','pass_at_1','total_cost','currency','mixed_currencies','unknown_cost_attempts','http_attempts','http_retries','operational_recovery_runs','operational_http_attempts','operational_known_cost_subtotal','operational_unknown_cost_runs','methodology'])
        for group in value['groups']:
            row=[value['schema_version']]+[group[x] for x in ('benchmark','dataset_version','grading_protocol','harness_revision','subset','official_harness_version','agent_version','profile_id','model_id','upstream_id','reasoning_effort','task_count','matched_task_count')]+[group['metrics'][x] for x in ('attempts','valid_evaluations','resolved_rate','pass_at_1','total_cost','currency','mixed_currencies','unknown_cost_attempts','http_attempts','http_retries','operational_recovery_runs','operational_http_attempts','operational_known_cost_subtotal','operational_unknown_cost_runs')]+[json.dumps(value['methodology'],ensure_ascii=False)]
            writer.writerow([csv_cell(v) for v in row])
        return PlainTextResponse(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="swe-comparison.csv"'})

    @app.get('/api/v1/shadow/results')
    def shadow(credentials: HTTPAuthorizationCredentials | None=Depends(bearer)):
        value=credentials.credentials if credentials else ''
        allowed=bool(value and (hmac.compare_digest(value.encode(),settings.admin_token.encode()) or
            (len(settings.shadow_token)>=24 and hmac.compare_digest(value.encode(),settings.shadow_token.encode()))))
        if not allowed:
            raise HTTPException(401,'read-only export authentication required')
        return shadow_export(repo)

    @app.get('/api/v1/integrations/sub2api',dependencies=auth)
    def integration():
        with repo.connect() as db:
            items=[dict(x) for x in db.execute('SELECT * FROM integration_metadata')]
        return {'configured':settings.integration_file is not None,'federation':'blocked: no compatible server-side identity exchange verified',
                'items':[{'source_id':x['source_id'],'observed_at':x['observed_at'],'metadata':json.loads(x['metadata_json'])} for x in items]}

    @app.post('/api/v1/integrations/sub2api/sync',dependencies=auth)
    def sync():
        if settings.integration_file is None:
            raise HTTPException(503,'SWE_INTEGRATION_FILE not configured')
        try:
            source,metadata=synchronize(settings.integration_file,profiles)
        except ValueError as error:
            raise HTTPException(502,str(error)) from None
        with repo.connect(write=True) as db:
            db.execute('INSERT OR REPLACE INTO integration_metadata VALUES (?,?,?)',(source,time.time(),json.dumps(metadata)))
        return metadata

    static=Path(__file__).parent/'static'
    if (static/'assets').is_dir():
        app.mount('/assets',StaticFiles(directory=static/'assets'),name='assets')

    @app.get('/',include_in_schema=False)
    @app.get('/console',include_in_schema=False)
    def dashboard():
        if not (static/'index.html').is_file():
            raise HTTPException(503,'dashboard assets missing; run frontend build')
        return FileResponse(static/'index.html')

    return app

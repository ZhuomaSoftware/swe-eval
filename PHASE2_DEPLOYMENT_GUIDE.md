# SWE Evaluation Center deployment and administration

> Current local deployment is running the verified Phase 2.5 images. Use
> [PHASE25_LOCAL_DEPLOYMENT.md](PHASE25_LOCAL_DEPLOYMENT.md) for its exact Compose
> files and restart commands. The general fresh-deployment guidance below is
> retained; the existing local default phase1 image tags are obsolete.


Use a **new Linux Docker worker host/disposable VM**. Do not run untrusted
benchmarks on a production gateway host. These commands do not authorize
replacing existing deployments. Back up and rehearse migrations on a copied DB.

## Install and build

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-core.lock \
  -r requirements-agent.lock -r requirements-test.lock -r requirements-build.lock
cd frontend
npm ci
npm test
npm run build
cd ..
.venv/bin/python -m pip install --no-deps --no-compile --no-build-isolation .
.venv/bin/python -m swe_eval.dependency_check --lean-agent
```

Node 22.12+ is required; Docker builds use a pinned Node image digest. Python
core/agent versions remain pinned. The documented lean mini dependency exception
remains: raw worker `pip check` fails for exactly nine excluded upstream extras;
the compatibility gate must pass. API `pip check` should be clean. No new Python
runtime dependency is required. Build assets before creating a wheel/sdist:

```bash
.venv/bin/python -m build --no-isolation
.venv/bin/python tools/package_release.py
```

The wheel includes dashboard assets and migration SQL. Source/release bundles
include frontend source and npm lockfile. No `.env`, databases or node_modules
belong in artifacts.

## Configure a fresh deployment

Copy `.env.example` to `.env` **only in a fresh directory**. Set a random
`SWE_ADMIN_TOKEN` (minimum 24 characters) for programmatic administration.
Generate a separate dashboard password hash without putting the password in
shell history:

```bash
.venv/bin/python -c 'from getpass import getpass; from swe_eval.sessions import password_hash; print("SWE_UI_PASSWORD_HASH=" + chr(39) + password_hash(getpass("Console password: ")) + chr(39))'
```

Put that entire output line in `.env`, preserving single quotes around the hash
so Compose does not interpolate its dollar signs. Set:

- `SWE_PUBLIC_ORIGIN=https://swe.example.com` (exact browser origin, no path).
- `SWE_COOKIE_SECURE=true` behind HTTPS. Local HTTP testing only: false.
- `SWE_SHADOW_TOKEN`: separate random read-only credential, at least 24 chars.
- `SWE_MAX_BATCH_RUNS=100`, `SWE_MAX_PENDING_RUNS=200` by default.
- `SWE_MAX_BATCH_DURATION=86400`, `SWE_MAX_BATCH_REQUESTS=10000` server maxima.

Configure the existing `config/models.json`; do not create a competing profile
store. API keys are environment/file references and are supplied **only** to the
worker. For genuine inference profiles explicitly set `data_origin: "live"`.
Default `unverified` profiles remain usable for runs but cannot enter trusted
router exports. Local stubs must use `local_stub`; audit profiles use `audit`.
Set `upstream_verified: true` only after independently confirming a fixed routing
path. A group/public model name alone does not prove an upstream identity.

```bash
docker build -t swe-eval-sandbox:phase1 -f docker/sandbox.Dockerfile .
docker build -t swe-eval-grader:phase1 -f docker/grader.Dockerfile .
docker compose -p swe-center --env-file .env -f compose.yaml -f compose.center.yaml \
  --profile local-worker build api worker
```

These tags must contain the corrected v2 controller; do not assume old images
with the same names are safe. Run commands on the fresh/disposable host, not
against the pre-existing production project. Linux socket group can be supplied
with `DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)`.

## Database migration and rollback

Schema 1 → 2 is additive. Startup and `swe-eval init-db` apply it once inside a
transaction. Historical run metrics/logs/patches are never rewritten, and no
historical snapshot is invented. Pause submissions and drain/stop the **intended**
worker through your deployment process before upgrade. Use SQLite's backup API,
not an isolated copy of a live WAL database file:

```bash
# Example on an offline/staging copy; replace both paths deliberately.
.venv/bin/python - <<'PY'
import sqlite3
source = sqlite3.connect('staging/runs.sqlite3')
target = sqlite3.connect('staging/pre-phase2.sqlite3')
source.backup(target)
target.close()
source.close()
PY
SWE_DATA_DIR=staging SWE_MODELS_FILE=config/models.json .venv/bin/swe-eval init-db
# Repeating init-db is safe. Check PRAGMA user_version == 2 and integrity_check == ok.
```

Fresh Docker database initialization:

```bash
docker compose -p swe-center --env-file .env -f compose.yaml -f compose.center.yaml \
  run --rm --no-deps api swe-eval init-db
# Before starting the persistent worker (single-worker lease):
docker compose -p swe-center --env-file .env -f compose.yaml -f compose.center.yaml \
  --profile local-worker run --rm --no-deps worker swe-eval verify-fixture --case both
```

`002_center.down.sql` is for offline restored copies only; it removes Phase 2
metadata but retains runs/logs. Prefer restoring the pre-upgrade backup and prior
application version. Never downgrade a live shared database. Do not allow old
workers to share a schema-2 deployment. Existing queued configurations whose
snapshot/configuration no longer matches fail safely; they are not silently rerun.

## Start and verify

```bash
docker compose -p swe-center --env-file .env -f compose.yaml -f compose.center.yaml \
  --profile local-worker up -d api worker
curl --fail http://127.0.0.1:8000/health
# SWE_ADMIN_TOKEN must be exported securely in the calling shell for curl.
curl --fail -H "Authorization: Bearer $SWE_ADMIN_TOKEN" http://127.0.0.1:8000/api/v1/system
docker compose -p swe-center --env-file .env -f compose.yaml -f compose.center.yaml \
  --profile local-worker exec -T worker swe-eval doctor
```

Serve the API behind `deploy/nginx-center.conf` with real TLS certificates.
Open `https://swe.example.com/` and use the independent console password.
The worker must report `worker_ready=true`, a valid lease, and successful cleanup.
`/health` alone checks only API/database. Model availability is deliberately
`not_probed`; the health page makes no inference charge.

For local HTTP set public origin exactly to `http://127.0.0.1:8000`, disable Secure
cookies only locally, and visit that exact address. For frontend hot reload:
`cd frontend && npm run dev`; set backend public origin to `http://localhost:5173`
and use that address. Vite proxies `/api` to the local API. The worker still runs
in Linux Docker. Native macOS worker supervision remains unverified.

## Create a bounded experiment

This request creates real, potentially paid jobs. Use authorized test profiles.
Profile IDs, not gateway model aliases, are selected:

```bash
curl --fail http://127.0.0.1:8000/api/v1/batches \
  -H "Authorization: Bearer $SWE_ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Coding comparison","task_ids":["intervals-001"],"model_profile_ids":["gateway-primary"],"attempts":1,"idempotency_key":"coding-comparison-001","limits":{"timeout":180,"steps":6,"requests":8,"output_tokens":2048,"total_tokens":20000},"max_duration":600,"max_requests":8}'
```

Poll `/api/v1/batches/{id}` or use the UI. Identical idempotent resubmission returns
the same jobs; changed input with the same key gets 409. Batch cancellation is
`POST /api/v1/batches/{id}/cancel`. Reconciliation never automatically retries a
failed paid attempt. Individual explicit retries are child runs outside the
original batch's reserved request budget. Monetary caps are not available;
spending-limit requests return 422. Token usage can be unknown and token budgets
are enforced between responses, not as a guaranteed billing cap.

## Comparisons, export and eligibility

Use `/api/v1/comparison?profile_ids=profile-a,profile-b&batch_id=...` and
`/api/v1/comparison/export?format=csv` (or json). Exports carry versions, protocol,
harness, sample counts and methodology. All authenticated administrators can
inspect diagnostic logs; no export includes hidden expected answers or secrets.
The run history can include historical data; trusted analytics cannot.

```bash
curl --fail -H "Authorization: Bearer $SWE_SHADOW_TOKEN" \
  http://127.0.0.1:8000/api/v1/shadow/results
```

Shadow token cannot submit/cancel jobs or synchronize metadata. The interface is
`gpt-auto-swe-v1`, informational and read-only. No model weights/routing/billing
writes exist. Legacy, non-agent, stub/audit, unverified upstream, unsupported
benchmark and incomplete outcomes are excluded from scoring. Reliability retains
all attempts. One fixture never produces a capability weight or general ranking.

## sub2api integration status and configuration

**Live federation and metadata sync: BLOCKED pending an authorized compatible
staging environment and management key.** Only source inspection and local HTTP
contract tests have been performed. Do not use existing inference API keys as
management credentials. No production gateway request was made.

Copy `config/sub2api.example.json` to a private server-owned config. Map existing
profile IDs to group IDs, set `SWE_INTEGRATION_FILE`, and explicitly mount that
file read-only into the API container. Supply `SUB2API_METADATA_ADMIN_KEY` only
to that server process. This is a metadata-management credential, never sent to
inference boxes or browsers. Call `POST /api/v1/integrations/sub2api/sync` with
admin authorization. The adapter calls only GET effective-models, never account
or credential-list APIs. Schema mismatch preserves the prior snapshot.
Metadata does not automatically edit model profiles, prices, routing or secrets.
Upstream attribution always remains unverified in imported metadata.

The inspected gateway supports admin-visible Markdown custom pages. A minimal
entry can contain a plain `[打开 SWE 评测中心](https://swe.example.com/)` link in
an admin-visible Markdown page; use the installed admin UI's supported page/menu
configuration. This avoids its iframe helper, which places a JWT in query strings.
No gateway menu was installed automatically. Secure shared-session login requires
an actual supported server-side identity exchange; none is invented here.

## Verification commands

```bash
PYTHONPATH=src SWE_DOCKER_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
cd frontend && npm test && npm run build && cd ..
docker build --target development -t swe-center-tests -f docker/service.Dockerfile .
# Dedicated trusted orchestrator alone gets the daemon. Candidates never do.
docker run --rm --network none --read-only --group-add "$(stat -c '%g' /var/run/docker.sock)" \
  --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:size=128m \
  -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD/tests:/audit-tests:ro" \
  -e PYTHONPATH=/audit-tests -e SWE_DOCKER_TESTS=1 -e MSWEA_GLOBAL_CONFIG_DIR=/tmp/mini \
  swe-center-tests python -m unittest discover -s /audit-tests -v
# Same Docker invocation, replace its final Python arguments to isolate the attack:
# python -m unittest test_remediation.GradingIntegrityTests.test_original_f01_exploit -v
```

Browser regression requires an isolated deployment seeded with deterministic stub
runs, using the audit profiles in `data/phase2-20261021/`; it is not suitable for a
production endpoint because it creates a test session. Build
`docker/browser-tests.Dockerfile`, set `SWE_BROWSER_URL` to that deployment, and
mount a writable `/evidence` directory for screenshots. No live model test is
included in Phase 2 verification without explicit authorization.


### One-command reproducible local full-stack smoke

This committed helper generates a NEW isolated Compose project, volume and local
model stub, executes a genuine mini/Docker three-profile batch, optionally runs
all three Chromium tests, and removes only its own resources. No external model
credentials or paid calls are used. Choose a free port and a new output path.
On Linux adjust Docker socket group policy if necessary (helper defaults GID 0).

```bash
.venv/bin/python tools/center_smoke.py --build --browser \
  --port 18090 --output data/center-smoke-fresh
```

It builds uniquely named smoke image tags. To reuse prebuilt images omit
`--build` and pass `--api-image`, `--worker-image`, `--sandbox-image`,
`--grader-image`, `--browser-image`. Evidence includes batch identities, browser
results/screenshots, service logs and cleanup. The API is bound only to loopback;
headless browser uses the private Compose network and matching internal Origin.
Do not point this helper at an existing service or use production model profiles.


## Phase 2.5 lifecycle, confidentiality and observability

Never edit a source-mounted auto-reload checkout while it serves an existing
shared database. Develop/build from a separate copy first. Coordinate stopping
only the intended SWE development services before applying source; do not
restart/migrate/rebuild production sub2api. Deploy corrected immutable images on
a fresh staging project, rehearse schema-1 migration on a SQLite backup, and
retain the old image/database for rollback. Phase 2.5 needs no new schema version.

Completed batches ignore later deadlines. Cancelling any terminal batch returns
HTTP 202 with unchanged state (idempotent no-op). A batch with all completed
attempts is completed, including genuine unresolved repairs. A terminal batch
with infrastructure failures is failed unless cancellation stopped the batch;
queued/running cancellation preserves completed attempts. No automatic retry.

Public logs expose assertion expected/executed/passed/failed counts, errors and
safe classifications; raw hidden operation inputs/outputs and verdict details
are withheld. Existing database records are filtered on ordinary reads, not
destructively scrubbed. Old DB copies, Docker logs and forensic evidence may
still contain historical private data: keep them in a server-only directory
(mode 0700, backup files 0600), outside the web root; restrict operator access.
Do not upload forensic backups through ordinary artifact/export endpoints.

Trusted dashboard metrics and latest success include live-origin eligible v2
agent evaluations only. `diagnostic_metrics` includes labeled local/audit
experiments; comparison JSON includes `trusted_evidence` and separate origin
groups. These diagnostic experiments are not real model rankings. CSV text is
neutralized for formula prefixes after whitespace/control/BOM characters;
numeric metrics remain numeric. Run details show known cost and currency or an
explicit unknown state. Pricing supports USD; unknown cost remains null.

Pass@1 is a micro-average across unique versioned-task/full-configuration pairs:
select earliest parentless numbered-1 (or unnumbered) run by creation time then
ID. Profile/upstream, endpoint, configuration/effective settings, protocol and
harness remain distinct. Retry children and numbered attempts >1 are excluded.
Infrastructure failure in the first attempt counts as failure in this denominator.
A cross-configuration micro-average is not a model ranking. Percentiles retain
linear interpolation; terminal cancelled duration samples are included.

Shadow quality freshness uses only valid completed live evidence. The response
separates `evaluated_at`, `last_attempted_at`, `last_trusted_success_at`, and
`generated_at`. Pending/cancelled/stub/audit activity cannot refresh quality.

Check authenticated `/api/v1/system`, not just `/health`: API/database readiness,
actual `last_worker_heartbeat_at`, `worker_lease_status`, lease expiry,
`last_completed_evaluation`, queue/active/oldest pending, recent infrastructure
errors and observed `orphan_cleanup`. Acquisition/renewal records the heartbeat;
no timestamp is reconstructed from an assumed lease duration. Old databases can
report null until the corrected worker writes a real observation. Docker is the
last worker probe, upstream remains not_probed, and cleanup reports observations
rather than an invented orphan count. Retained start events are not Docker restart
telemetry; the original worker's historical restart cause remains undetermined.

## Reproducible external staging acceptance (still BLOCKED)

Use a separately authorized compatible staging sub2api instance and metadata-only
administrator key, never existing production credentials. Record its revision,
origin and supported admin entry mechanism. Current sibling source at
5de4efe9f68d3c0aca65ecda87627fb1a1ac026b exposes GET
`/api/v1/admin/groups/:id/effective-models` behind admin middleware. Recheck that
contract on the exact staging revision before supplying a key.

1. Build/start the SWE deployment on a separate origin/DB. Configure an
   admin-visible plain Markdown link in staging only; verify admin access,
   non-admin rejection, refresh, expiry and logout through the real interface.
   Standalone SWE login remains required; no SSO exchange is implemented.
2. Configure the server-only mapping/key described above. Observe network calls
   during sync: GET effective-models only, no account/credential or write APIs.
3. Test repeated sync, duplicate aliases, disabled/removed models, metadata
   changes, malformed schema, 401 and outage. Confirm last good metadata survives
   failed sync and API restart. Imported upstream attribution must remain false.
4. Inspect browser requests/assets/storage: neither management key nor SWE admin
   bearer may appear. Keep CSP frame-ancestors none; do not use JWT query URLs.
5. Have the actual staging gpt-auto consumer GET the versioned shadow export with
   its read-only credential. Verify protocol/origin/identity, missing cost,
   authoritative freshness, small samples and no routing/billing/weight writes.
   Record consumer revision and ingestion results. No consumer is available here.

Only observed success against these actual dependencies can remove the external
BLOCKED statuses. Local HTTP contract tests alone cannot do so.

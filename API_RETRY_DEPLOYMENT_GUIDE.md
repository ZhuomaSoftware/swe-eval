# Reliable retries — local deployment and operations

Current rollout (2026-10-22): the user authorized deployment to the local test console on port18327. The verified API retry images and explicit migration are now deployed, login/worker/persistence checks PASS. See [API_RETRY_LOCAL_DEPLOYMENT_REPORT.md](API_RETRY_LOCAL_DEPLOYMENT_REPORT.md) for current image IDs and evidence. Existing credentials remain unchanged. Earlier acceptance/deployment boundaries below describe their original test scope.

The verified source is in the main working tree. The tested deployment is an additional project `swe-api-retry-acceptance` at **http://127.0.0.1:18328**. Existing console **http://127.0.0.1:18327** was not replaced. Production/sub2api/gpt-auto and the historical live batch were not changed.

## Inspect the running acceptance stack

```sh
RETRY_EVIDENCE="$(cat data/api-retry-current.txt)"
"$RETRY_EVIDENCE/stack" ps
"$RETRY_EVIDENCE/stack" logs --tail 100 api worker
curl --fail http://127.0.0.1:18328/health
```

Worker readiness requires the authenticated `/api/v1/system` worker_ready/heartbeat/lease fields, not merely /health. The protected login password is in `$RETRY_EVIDENCE/login-password.txt`; persistent administrator, signing/password and encryption configuration is in `private.env` (0600 in a 0700 directory). No actual secret value belongs in this guide, Git, browser storage or ordinary evidence. Back up the protected env/key separately from the database; never regenerate the encryption key for an existing deployment.

## Exact final builds and tests

```sh
python3 data/api-retry-20261022T083434Z/build_images.py
python3 data/api-retry-20261022T083434Z/run_installed_tests.py
python3 data/api-retry-20261022T083434Z/run_frontend.py
```

The builder uses docker/service.Dockerfile target api and docker/worker-from-accepted.Dockerfile targets worker/development, with the retained accepted batch-budget runtimes and pinned official tools image. Exact build arrays and image IDs are in build-results.json / final-images.json. The offline path preserves mini-SWE-agent2.4.6 and official SWE-bench5.0.2. A new host needs those accepted base images or the canonical service.Dockerfile official-worker/official-development targets and pinned dependency locks; registry access may be required. Do not silently upgrade dependencies.

## Fresh isolated database initialization

Prepare a new project/env/named volume and approved local model origin using the existing Compose security/storage pattern. The retained compose.json is the actual accepted configuration. `prepare_staging.py` deliberately refuses to overwrite an existing secret file. Bootstrap in order:

```sh
"$RETRY_EVIDENCE/stack" config --quiet
"$RETRY_EVIDENCE/stack" run --rm --no-deps api swe-eval init-db
"$RETRY_EVIDENCE/stack" run --rm --no-deps api swe-eval migrate-admin
"$RETRY_EVIDENCE/stack" run --rm --no-deps api swe-eval migrate-retries
"$RETRY_EVIDENCE/stack" up -d
```

Only the intended new schema3 database is migrated. Retry migration adds three tables and metadata api_retry_schema=1 in one transaction, retaining core user_version3. Re-running migrate-retries is idempotent. Startup does not silently apply it. Preserve the catalogue via SQLite online backup; metadata count alone does not validate environments. The retained approved catalogue still has 500 imported / 20 curated / 13 READY / seven ineligible; no readiness was upgraded.

## Request policy and bounds

Batch creation → 执行预算 → 自动重试与失败恢复. Defaults: API retry ON, three total attempts, 1s initial / 2x backoff / 20s ordinary maximum / 60s overall request-retry budget; recovery OFF. Recovery may be enabled for at most one clean child per independent attempt, with configurable eligible categories and minimum remaining time. The full effective per-run timeout must also fit before the original batch deadline.

Independent attempts, API retries and clean run recovery are different. API retries share the run's physical HTTP cap; enabling three API attempts does not multiply that cap. Optional full-run recovery reserves an additional whole run/call allowance and can exceed server run limits. For the previous 78-run experiment, enabling one recovery each would reserve 156 runs and exceed a 100-run server cap. Reduce the experiment or explicitly change authorized server limits; do not bypass checks.

API callers configure fields on POST /api/v1/batches (including one-item batches):

```json
{"api_retry":{"enabled":true,"max_attempts":3,"initial_delay":1,"multiplier":2,"max_delay":20,"time_budget":60},"run_recovery":{"enabled":false,"max_recoveries":1,"minimum_remaining_seconds":60,"eligible_categories":["transient_http","rate_limited","network","request_timeout","capacity_unavailable"]}}
```

Include the existing required task/model/name/limits/idempotency fields. Preview first through POST /api/v1/manage/batch-preview. Older clients omitting these optional fields retain prior behavior/idempotency; already admitted jobs are not retroactively given retries. The legacy individual-run/manual retry API is preserved; use a one-item batch for configurable policies. Never automatically retry the historical paid batch. Unknown cost/usage remains unknown; physical requests can be billed even when the response times out. A known-price subtotal is not a guaranteed spending cap.

## Online backup and restore

Use SQLite backup on the running trusted API inside its Linux volume, after identifying the exact project/database. Do not copy a live main file without its WAL state. The exact executed backup/check script is in final_checks.py. Its final backup is `/data/backups/api-retry-final/runs.sqlite3`. A schematic safe operation inside the intended API is:

```python
import sqlite3
with sqlite3.connect('/data/runs.sqlite3') as source, sqlite3.connect('/data/backups/UNIQUE-BACKUP.sqlite3') as target:
    source.backup(target)
with sqlite3.connect('/data/backups/UNIQUE-BACKUP.sqlite3') as backup:
    assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not backup.execute('PRAGMA foreign_key_check').fetchall()
```

Create the protected destination directory first and use a new filename; preserve the master key separately. The catalogue is a distinct private database and also needs an online backup. Export protected backups only to private storage. The original accepted database was backed up inside its existing API container without stopping/migrating it; the migration test used a consistent independent copy and preserved all records.

For restore, drain/cancel authorized work, stop only the intended isolated project's API/worker, preserve a new backup of current state, restore the verified backup into its Linux named volume using SQLite's backup API, set owner10001 and restrictive permissions, restore the matching key/env/images, then restart and verify schema/foreign keys/configuration/worker readiness. Do not restore directly over an active connection or silently discard records created after the backup. Never attach a macOS directory as active SQLite storage.

## Restart/recreate/stop

After confirming only this project's jobs are safe to interrupt:

```sh
"$RETRY_EVIDENCE/stack" restart api worker
"$RETRY_EVIDENCE/stack" up -d
"$RETRY_EVIDENCE/stack" stop
# Restart later without removing volumes:
"$RETRY_EVIDENCE/stack" up -d
# Inspect storage without printing secret-bearing container configuration:
docker volume inspect swe-api-retry-acceptance_retry-data
```

The tested stack is left running. Do not use down --volumes, volume deletion or system prune. Manual restart during active evaluation may intentionally produce worker_interrupted; no automatic crash/whole-timeout retry is promised. Persisted queued recovery survives graceful restart; stale owners cannot write after lease loss. Follow the existing lease expiry/cleanup rules after a crash.

## Promotion and rollback boundary

Replacing the existing port-18327 stack is **not authorized by this task**. A later approved rollout must verify its queue is empty, online-back up both databases and persistent key/env, record old images/Compose settings, stop only the authorized worker, apply migrate-retries explicitly to that intended database, select final tested images and recreate only those services. Verify health, zero-dispatch safety and a bounded local-stub workflow before any paid experiment. Do not change sub2api/gpt-auto.

Retain old image IDs and pre-migration backups. To roll back, first drain/cancel recovery work: old binaries do not understand deferred recovery eligibility and must never consume such queued rows. Preserve all post-migration records, then deliberately restore the matching pre-migration database/key and old images if authorized, reconciling newer results instead of discarding them. Do not drop tables or lower schema flags to force compatibility. This migration is additive, but that alone does not make an old worker safe to run with pending recovery jobs.

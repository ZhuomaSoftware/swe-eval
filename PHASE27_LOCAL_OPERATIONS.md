# Phase 2.7 local operations

Current operational state: all four local SWE test Docker projects are stopped at the user’s request; databases and named volumes are preserved. See [SWE_TEST_DOCKER_SHUTDOWN_REPORT.md](SWE_TEST_DOCKER_SHUTDOWN_REPORT.md). The deployment commands and URLs below remain reference procedures.

Current rollout (2026-10-22): the user authorized deployment to the local test console on port18327. The verified API retry images and explicit migration are now deployed, login/worker/persistence checks PASS. See [API_RETRY_LOCAL_DEPLOYMENT_REPORT.md](API_RETRY_LOCAL_DEPLOYMENT_REPORT.md) for current image IDs and evidence. Existing credentials remain unchanged. Earlier acceptance/deployment boundaries below describe their original test scope.

This operates **only** the new `swe-p27-local` deployment. Leave existing port-8000/18372, sub2api and gpt-auto services untouched. The verified local console is **http://127.0.0.1:18327**. Keep Docker Desktop running.

## Select the deployment and log in

```sh
cd /Users/user/Program/swe-eval
LOCAL_DEPLOY=/Users/user/Program/swe-eval/data/phase27-local-20261022T023632Z
LOCAL_STACK="$LOCAL_DEPLOY/stack"
"$LOCAL_STACK" ps
open http://127.0.0.1:18327
```

The login form asks for the console password, not an email or bearer API token. Read `data/phase27-local-20261022T023632Z/login-password.txt` locally. It is a newly generated password for this deployment, separate from earlier services. No secret value is printed in these documents. Do not share that file or the external environment file.

The wrapper selects `-p swe-p27-local`, the existing `compose.management.yaml`, and its new-project override. It supplies the exact public origin and external raw env file. Do not print resolved Compose configuration: it contains secrets. Use `config --quiet`.

The enabled provider `browser-stub` / model `browser-dynamic` is a local deterministic infrastructure test. It makes a source comment and normally gets an unresolved official result. It does not establish model quality. `browser-quick-2` contains two READY official tasks. `curated-20-v1` preserves all original twenty members, including seven blocked members; it cannot be submitted as an all-ready experiment. New real provider credentials can be entered in the WebUI, but this acceptance did not authorize paid inference.

## Add models from an upstream list

In **模型配置 → 从上游选择模型**, choose an enabled provider (for example APINode), then click **读取上游模型列表**. Search and select up to twenty entries, then click **添加所选模型**. This reads only the provider model-list endpoint; the key stays server-side and no inference is sent.

Imported configurations are disabled by default, with unknown pricing and unverified execution/upstream identity. Review the profile's reasoning capabilities, execution origin, token/request/time limits and pricing before enabling it. The optional **导入后启用模型** checkbox makes new profiles immediately selectable without submitting any evaluation. Existing aliases under the same provider are marked already configured; the same alias under another provider remains independent. Each selected entry gets its own versioned profile. Partial failures retain only failed selections for retry.

## Batch request reservations

The batch wizard shows the minimum request reservation before review and provides **使用最低所需预留** as an explicit operator action. Required reservation is task count × attempts per combination × the sum of each selected model's effective call cap. Effective caps take the smaller experiment/profile limit. For the current thirteen-task, three-model, two-attempt selection with profile call caps of 15, reserve at least **1170**, not 100. This is an upper-bound request reservation, not an assertion of actual calls or known spend.

Larger experiment values do not increase model-profile ceilings. The wizard now displays each effective limit; increase a model's configuration first if a larger per-run budget is intended. Correcting preview does not submit a batch. Final creation remains an explicit operator action and may invoke paid providers.

## Build the exact components

From the accepted main source, with the pinned tools image available:

```sh
docker build --progress=plain -f docker/service.Dockerfile --target api -t swe-p27-batch-budget-api:20261022 .
docker build --progress=plain -f docker/service.Dockerfile --target official-worker -t swe-p27-batch-budget-worker:20261022 .
docker build --progress=plain -f docker/service.Dockerfile --target official-development -t swe-p27-batch-budget-development:20261022 .
docker build --progress=plain -f docker/sandbox.Dockerfile -t swe-p27-local-sandbox:20261022 .
docker build --progress=plain --build-arg SANDBOX_IMAGE=swe-p27-local-sandbox:20261022 -f docker/grader.Dockerfile -t swe-p27-local-grader:20261022 .
```

The tools image is `swe-eval-swebench-tools:5.0.2-02e7a74`, verified identity `sha256:a7613db2bc745ddfe61d9319adf94252462b1db0e1e609bf6e8412d642de2dff`. Its dedicated `/opt/swebench` environment contains official SWE-bench 5.0.2. mini-SWE-agent stays 2.4.6 in the worker environment. Do not replace pins to solve a registry outage. If this specific tools image is absent, its reproducible Dockerfile is `docker/swebench.Dockerfile`; rebuilding requires external package/Git access and separate identity verification. Startup does not build all benchmark environments.

New server-owned task manifests in `$LOCAL_DEPLOY/tasks/` select the new sandbox/grader tags. The older default grader tag was not source-equal and is not used here. Do not substitute it. No old image tag was overwritten. The root Compose template's tmpfs entry must remain quoted as one string.

Building an image does not update running containers. Drain both queues, back up, rerun regressions, then explicitly recreate this project only.

## Start, stop, restart and recreate

```sh
"$LOCAL_STACK" config --quiet
"$LOCAL_STACK" up -d
"$LOCAL_STACK" ps
"$LOCAL_STACK" logs --tail 100 api worker
# Follow new-project logs; Ctrl-C only ends log following.
"$LOCAL_STACK" logs -f --tail 100 api worker
```

Before maintenance, inspect **系统健康** and **数据集管理**: no active/queued evaluations or administrative jobs. Gracefully stop only this stack:

```sh
"$LOCAL_STACK" stop worker api stub
# Start again without deleting the database.
"$LOCAL_STACK" up -d
```

After a supported online backup and empty queues:

```sh
"$LOCAL_STACK" restart api worker
# Container recreation retains the same named volume and external key.
"$LOCAL_STACK" up -d --force-recreate api worker
```

Never use `down -v`, `docker volume rm`, `docker system prune`, or delete data to resolve startup failures. Do not apply these commands to unrelated projects. Do not regenerate `private.env` over stored encrypted credentials.

## Health and worker readiness

```sh
curl --fail http://127.0.0.1:18327/health
"$LOCAL_STACK" exec -T worker swe-eval doctor
"$LOCAL_STACK" exec -T worker /opt/swebench/bin/python -c 'import swebench; print(swebench.__version__)'
"$LOCAL_STACK" exec -T worker python -c 'from importlib.metadata import version; print(version("mini-swe-agent"))'
"$LOCAL_STACK" exec -T api python - <<'PY'
import os,json,urllib.request
request=urllib.request.Request('http://127.0.0.1:8000/api/v1/system',headers={'Authorization':'Bearer '+os.environ['SWE_ADMIN_TOKEN']})
state=json.load(urllib.request.urlopen(request,timeout=10))
print(json.dumps({k:state[k] for k in ['api','database','worker_ready','worker_lease_status','last_worker_heartbeat_at','queue_depth','active_run','last_completed_evaluation','orphan_cleanup','recent_infrastructure_errors']},indent=2))
PY
```

`/health` establishes only API/database availability. Inspect actual worker liveness, heartbeat/lease, queue, Docker observation and recent failures independently. `upstream=not_probed` is honest; it is not inferred healthy. Provider **测试连接** performs bounded GET model-list, not paid inference.

```sh
docker inspect swe-p27-local-api-1 swe-p27-local-worker-1 --format '{{.Name}} state={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}'
docker inspect swe-p27-local-api-1 swe-p27-local-worker-1 --format '{{.Name}} {{json .Mounts}}'
docker volume inspect swe-p27-local_management-data
```

Expected `/data` mount type is `volume`, same name in both components. `/data/runs.sqlite3`, WAL/SHM, catalogue and artifacts must not be host DB binds. The read-only host configuration/task mounts contain no active database. API and worker use immutable images without auto-reload.

## Explicit database migration

This deployment is already schema 3. Do not rerun initialization to reset it. Normal startup does not automatically migrate administration schema. For a fresh authorized copy or explicit future migration, first back up and verify the target identity:

```sh
"$LOCAL_STACK" run --rm --no-deps api swe-eval migrate-admin
"$LOCAL_STACK" exec -T api python - <<'PY'
from swe_eval.storage import SQLiteRepository
from pathlib import Path
r=SQLiteRepository(Path('/data/runs.sqlite3'))
with r.connect() as d:
    print('schema',d.execute('pragma user_version').fetchone()[0])
    print('journal',d.execute('pragma journal_mode').fetchone()[0])
    print('foreign_keys',d.execute('pragma foreign_keys').fetchone()[0])
    print('integrity',d.execute('pragma integrity_check').fetchone()[0])
    assert not d.execute('pragma foreign_key_check').fetchall()
PY
```

Fresh bootstrap uses `swe-eval init-db` (schema 2) followed by explicit `migrate-admin` (schema 3). The fresh deployment already completed both and migration idempotency was verified. Never run this against production or existing unrelated development volumes.

## Online backups

Drain evaluation/administrative queues before taking an operational recovery set. Main SQLite backup is WAL-consistent. The catalogue is backed up separately; there is no cross-database distributed transaction, so quiescence preserves a coherent recovery set.

```sh
"$LOCAL_STACK" exec -T api python - <<'PY'
import sqlite3,datetime
from pathlib import Path
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder=Path('/data/backups')/stamp
folder.mkdir(mode=0o700,parents=True,exist_ok=False)
for label,source in [('runs',Path('/data/runs.sqlite3')),('catalogue',Path('/data/datasets/catalogue.sqlite3'))]:
    destination=folder/(label+'.sqlite3')
    with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    destination.chmod(0o600)
    with sqlite3.connect('file:'+str(destination)+'?mode=ro&immutable=1',uri=True) as check:
        assert check.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not check.execute('pragma foreign_key_check').fetchall()
print(str(folder))
PY
```

Copy only these completed backup files out, not live database main files. Preserve completed `datasets/evaluations/` and `history/` artifacts under restricted access as part of a quiescent recovery set. The acceptance archive `$LOCAL_DEPLOY/local-private-evidence.tar` contains verified online DB backups and private artifacts, mode 0600, and is never web served. Do not place it in frontend/public directories.

The persistent encryption master must be backed up **separately**. `private.env` and `secrets-backup.env` are restricted local files, not Git content; preserve an access-controlled recovery copy outside the host as appropriate. They contain administrator credentials and the master key. Do not print them in logs, resolved Compose output or support reports. Restore the original key with its database; arbitrary replacement cannot decrypt credentials. There is no plaintext fallback or automatic key rotation/re-encryption.

## Restore procedure

Restoration was tested on a **separate** `swe-p27-local_restore-check` named volume, not over the running database. Prefer verifying any recovery set in a fresh named volume first. In-place restoration replaces local state with the selected snapshot; retain a new online backup of current state and confirm that losing later records is intended. Never restore while API/worker are using the database.

Example for this project only, after draining queues and taking a fresh recovery copy:

```sh
"$LOCAL_STACK" stop worker api
# Select an already verified online-backup directory, e.g. the acceptance snapshot.
LOCAL_RECOVERY=backups/final-acceptance
docker run --rm -i --network none --read-only --user 10001:10001 \
  -e LOCAL_RECOVERY="$LOCAL_RECOVERY" \
  -v swe-p27-local_management-data:/data \
  swe-p27-batch-budget-api:20261022 python - <<'PY'
import sqlite3,os
from pathlib import Path
base=Path('/data').resolve();folder=(base/os.environ['LOCAL_RECOVERY']).resolve()
assert folder.is_relative_to(base/'backups') and folder.is_dir()
for name,target in [('runs',base/'runs.sqlite3'),('catalogue',base/'datasets/catalogue.sqlite3')]:
    source=folder/(name+'.sqlite3')
    with sqlite3.connect('file:'+str(source)+'?mode=ro&immutable=1',uri=True) as src:
        assert src.execute('pragma integrity_check').fetchone()[0]=='ok'
        with sqlite3.connect(target) as dst:
            src.backup(dst)
            assert dst.execute('pragma integrity_check').fetchone()[0]=='ok'
            assert not dst.execute('pragma foreign_key_check').fetchall()
            dst.execute('pragma wal_checkpoint(TRUNCATE)')
    target.chmod(0o600)
print('Restored selected local online backups through SQLite API')
PY
# Ensure private.env still contains the original matching master; never generate a replacement.
"$LOCAL_STACK" up -d api worker
```

SQLite's backup/restore API handles the destination correctly; do not copy over an active main file or manually delete its WAL. Restore associated artifacts from the same restricted recovery set if needed. Afterward verify schema, FK/integrity, provider connection, subsets, run history and worker queue/lease. No restore procedure authorizes changes to other volumes.

## Reproduce accepted checks

```sh
python3 "$LOCAL_DEPLOY/run_frontend.py"
python3 "$LOCAL_DEPLOY/run_installed_tests.py"
```

The backend runner uses final installed official-development image with `SWE_DOCKER_TESTS=1`, `SWE_SWEBENCH_RUNTIME_TESTS=1`, real Docker socket and read-only catalogue reference, no application source mount. It passed 157 with zero skips. Frontend passed 20 plus TypeScript/Vite. These tests create disposable restricted candidate containers under separate service IDs and perform no paid requests.

The original `run_browser.py`, `recovery_test.py`, `backup_verify.py`, `run_http_checks.py` are retained **creation/fault-injection evidence**, not routine health checks. They contain fixed persistent test identities and expected preconditions. Do not blindly rerun destructive/interruption or creation scenarios against the retained operator stack. For repetition, preserve evidence and prepare a separately authorized fresh project/IDs. Read `recovery-result.json` and raw runner correction logs; the final assertions used the genuine four-row pre-crash online backup, without creating duplicate attempts. Native read-only screenshots can be repeated using the documented host Playwright runner; its temporary Python environment must still exist or be recreated using Python Playwright 1.64.0.

## Troubleshooting and boundaries

- **Port 18327 occupied:** identify the listener; do not stop port-8000/18372 services. Any selected alternative must update both published port and exact public origin, browser/test URLs and trusted configuration together.
- **Invalid tmpfs nodev mount:** retain the quoted single mount string in the root template. This was corrected during deployment.
- **Wrong/missing master key:** management/credential use fails safely. Recover the original externally stored key; never overwrite secrets or reset the database to conceal the error.
- **CSRF login/mutation 403:** open the exact `http://127.0.0.1:18327` origin, not `localhost` or a container hostname. SameSite/HttpOnly and CSRF protections stay enabled.
- **Private/Fake-IP provider DNS denied:** only explicit server-owned approved origins are permitted. Current local exceptions are `http://stub:8080` and, with explicit user approval on 2026-10-22, `https://api.zhuomatech.cn`. APINode resolved to non-public Fake-IP-style addresses and was rejected before HTTP; the exact HTTPS-origin exception resolved it. Its saved root Base URL remained valid. The actual authenticated non-inference connection test returned 10 models. Public HTTPS otherwise uses default restrictions. Metadata/link-local addresses remain denied even for approved origins; do not approve broad proxies or uncontrolled redirectors. Evidence: `data/phase27-provider-diagnostic-20261022T035221Z/result.json`.
- **Worker died:** inspect actual container state, lease/heartbeat, logs and active attempt. Natural lease expiry is about 90 seconds. Recovery marks unfinalized work failed; it does not silently repeat model calls. Do not rewrite worker_lock, timestamps or resolved flags. The acceptance SIGKILL produced exit 137 intentionally; that differs from the historical SIGBUS/135.
- **SIGBUS / exit 135 / WAL/lock error:** verify `/data` really is a Linux named volume and preserve crash/DB evidence. Stop claiming runtime stability if it recurs. Do not disable WAL/integrity controls. Historical host-bind crash root cause remains unproven; this deployment avoids that unsupported mode.
- **Image digest changed/missing:** official tasks reject mismatches. Use explicit bounded preparation/validation; no automatic eligibility upgrade. Preserve all original twenty identities. Thirteen READY images matched accepted evidence; seven remain ineligible.
- **Browser favicon 404:** known cosmetic native Chrome warning at `/favicon.ico`; application requests/pages/assets passed. It is documented, not hidden.
- **Overview trusted metrics:** local_stub official runs remain diagnostic; local-v2 trusted score cards remain zero/unknown. Inspect comparison diagnostics and System Health for the intentional infrastructure failure. Gold validation is not a model score.

No paid inference, public leaderboard, external server deployment, sub2api/gpt-auto change or production migration is part of this environment. Leave named volumes and the tested stack available.

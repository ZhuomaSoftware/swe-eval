# Phase 2.7 deployment and operator guide

Development is in the main repository. Existing running SWE development services and all sub2api services are outside this deployment procedure. Do not mount the new source into an old running database or promote these images automatically.

## Build

From the main directory:

```sh
docker build -f docker/service.Dockerfile --target api -t swe-main-p27-api:20261021 .
docker build -f docker/service.Dockerfile --target official-worker -t swe-main-p27-worker:20261021 .
docker build -f docker/service.Dockerfile --target official-development -t swe-main-p27-development:20261021 .
```

Keep the pinned `swe-eval-swebench-tools:5.0.2-02e7a74` tools image available. Its dependency environment is separate from mini-SWE-agent 2.4.6. Existing local sandbox/controller images are still required. No bulk image preparation is part of startup.

## Explicit schema migration

First take a SQLite online backup in the process/container owning the database. For example, on an authorized staging deployment:

```python
import sqlite3
with sqlite3.connect('/data/runs.sqlite3') as source, sqlite3.connect('/backup/pre-phase27.sqlite3') as backup:
    source.backup(backup)
```

Store backups outside public/static directories with restricted access. Back up the dataset catalogue separately using the same mechanism. Confirm both evaluation and administrative queues are empty before replacing staging API/worker images.

Using the new image and the copied/authorized staging data volume:

```sh
swe-eval migrate-admin
```

Normal startup does not apply migration 3. Management routes report unavailable on schema 2; existing core routes retain compatibility. Migration 3 is transactional and idempotent. It adds configuration, encrypted credential, subset, administrative job and audit tables without reinterpreting old results.

## External secret and network policy

Generate a random 32-byte master key with a secure generator and supply its base64 encoding to both trusted API and worker environments as `SWE_CONFIG_MASTER_KEY`. Keep it in a restricted external secret store or server-owned environment file, never Git, Compose interpolation output, browser storage, candidate environments or run snapshots. Losing it makes stored provider credentials unavailable. Back up it separately under appropriate access controls. Replacing it requires an explicit offline re-encryption procedure; there is no insecure plaintext fallback.

Configure approved private gateway origins, for example `SWE_APPROVED_PROVIDER_ORIGINS=http://stub:8080`, only in trusted server configuration. Entries are exact scheme/hostname/port origins without paths. Approving an origin permits its resolved private addresses; operators must control that hostname. Do not approve general-purpose forwarding services. Redirects and inherited proxy variables are not honored. Link-local/metadata addresses remain denied. Public HTTPS providers need no private-origin exception.

Retain existing `SWE_ADMIN_TOKEN`, `SWE_UI_PASSWORD_HASH`, cookie and exact public-origin controls. Generate dashboard password hashes with `swe_eval.sessions.password_hash`, not an independently implemented salt conversion. Use secure cookies over HTTPS outside local isolated tests.

## WebUI workflow

1. Open **API 提供商**, create an approved provider and save a credential. The saved key is never shown again. **测试连接** reads the model list without billable inference.
2. Open **模型配置**, create a profile with a unique ID and provider, model API ID, explicit upstream label, limits, reasoning capability and optional pricing/currency. Unverified upstream identity remains visible. Use `local_stub` for deterministic infrastructure tests.
3. Open **数据集管理**, inspect pinned revisions and actual readiness. Metadata synchronization requires a full dataset commit. Environment validation accepts at most five explicit official instance IDs and optional explicit image preparation.
4. In **基准任务**, search/filter dataset, repository, revision, instance, validation and readiness. Private gold/test materials are never displayed.
5. In **题单管理**, save a versioned subset. Blocked members remain visible and prevent batch admission. New revisions preserve old membership.
6. In **批量实验**, choose tasks/subset, enabled models, attempts and budgets, then review before submission. Total attempts equals tasks × models × attempts. Oversized, unready and over-reserved jobs are rejected before creation. Pricing does not establish a hard monetary cap.
7. Inspect real progress, run details, safe logs, patch, comparisons and JSON/CSV export. Local stubs are diagnostic evidence, not model capability scores.
8. Provider/model edits affect new submissions. Rotation preserves old credential bindings; explicit revocation causes remaining users of that version to fail safely. Disable/archive prevents new admission.

## Isolated acceptance reproduction

Evidence and runner scripts are under `data/phase27-dynamic-20261021T172902Z/`. The test deployment uses a separate SQLite/catalogue copy and port 18372. Its Compose file contains no master key or stored provider key; a restricted `private.env` supplies test secrets. The browser runner can restart only that isolated project's API/worker after verifying both queues are empty. It never restarts `swe-eval-api-1` or `swe-eval-worker-1`.

```sh
python3 data/phase27-dynamic-20261021T172902Z/build_final_images.py
# Use the retained private test fixture; do not regenerate its master key over encrypted data.
docker compose -f data/phase27-dynamic-20261021T172902Z/compose.json run --rm --no-deps api swe-eval migrate-admin
docker compose -f data/phase27-dynamic-20261021T172902Z/compose.json up -d
python3 data/phase27-dynamic-20261021T172902Z/run_browser.py
```

Browser tests create persistent IDs; reproduce in a fresh isolated database/catalogue copy, preserving the previous evidence first. See the acceptance report for exact final automated test commands and observed results.

## Rollback and limits

Keep the Phase 2.6 Git checkpoint/tag and pre-migration database backups. Old Phase 2.6 binaries do not support schema 3. Do not lower `user_version` or drop tables to force compatibility. For staging rollback, stop only that authorized deployment after its queues drain, retain a complete online backup of schema 3/new records, and restore the pre-migration copy with the old image. Newly created records need deliberate reconciliation before restoration; do not silently discard them.

The accepted official subset remains 13/20 executable unless fresh actual positive/negative validation changes that evidence. Seven environment blockers are not solved by management forms. Larger/native-x86 validation and any production rollout require separate infrastructure/authorization. No sub2api or gpt-auto integration is implemented in this phase.

## Independent management deployment with Linux database storage

Use the committed `compose.management.yaml` for a fresh isolated staging project. It uses a new named Docker volume, empty read-only compatibility profiles in `config/models.managed.json`, and externally supplied credentials. Administrators then create providers and models entirely through the WebUI; no model JSON editing is required.

Set `SWE_MANAGEMENT_ENV_FILE` to an absolute, restricted server-owned environment file containing `SWE_CONFIG_MASTER_KEY`, `SWE_ADMIN_TOKEN` and `SWE_UI_PASSWORD_HASH`. Its raw env-file format preserves the PBKDF2 dollar separators. Optional `SWE_APPROVED_PROVIDER_ORIGINS` belongs in that trusted file. Do not print resolved Compose configuration containing secrets. Set `DOCKER_GID` for the trusted worker's daemon access where required.

```sh
docker compose -f compose.management.yaml config --quiet
docker compose -f compose.management.yaml run --rm --no-deps api swe-eval migrate-admin
docker compose -f compose.management.yaml up -d
# Local staging console: http://127.0.0.1:18327
```

For an HTTPS deployment set the exact `SWE_MANAGEMENT_ORIGIN` and `SWE_COOKIE_SECURE=true`. This template is an independent project; it does not attach the existing `swe-eval_swe-data` volume or restart existing services. A fresh dataset catalogue starts empty. Import the pinned official metadata through **数据集管理**, then validate explicitly; metadata import alone does not recreate accepted readiness evidence.

Use native Linux storage for SQLite databases and WAL/shared-memory files. During acceptance, a macOS host bind-mounted SQLite database produced worker SIGBUS exits at `connection.commit()`; the exact filesystem/runtime root cause was not established. That bind-mounted deployment mode is excluded from the supported acceptance scope. Its databases and crash evidence were retained. The final acceptance report records the Linux-volume rerun and actual post-restart execution rather than inferring worker health from API availability.

For the existing local fixture, ensure the expected sandbox/controller image names are available (or use an explicitly configured, server-owned task manifest). The normal builds are:

```sh
docker build -f docker/sandbox.Dockerfile -t swe-eval-sandbox:phase1 .
docker build -f docker/grader.Dockerfile -t swe-eval-grader:phase1 .
```

File profiles remain operator-owned compatibility configuration. Managed profiles receive version-bound encrypted credentials and the new DNS-pinned network policy. Moving a legacy profile into management is an explicit administrator operation; existing historical snapshots are not rewritten.

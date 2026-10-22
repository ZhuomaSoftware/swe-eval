# Phase 2.7 local Docker deployment report

**PASS — isolated local administration deployment, with the retained 13-task executable scope.** The stack remains running at **http://127.0.0.1:18327**. This is local staging acceptance, not production rollout or full 20/20 benchmark readiness.

Generated 2026-10-22T03:30:33.089347+00:00. Working directory `/Users/user/Program/swe-eval`. Source tag `phase27-main-verified-20261021T183759Z`; HEAD `6bcf4340fc5e47901bdb1bc41852cf6908d567b8`. Accepted application source is unchanged. The only tracked deployment change is quoting the existing tmpfs YAML string in `compose.management.yaml`; the unquoted flow list had produced `invalid mount path: nodev mount path must be absolute`. No other baseline tracked file was changed. Unrelated dirty files and original five containers' IDs/images/start times/restart counts were preserved.

Evidence: `data/phase27-local-20261022T023632Z/` (0700). Original Phase 1–2.7 evidence was read, never overwritten. Deployment uses the existing Compose template plus a restricted-directory override and `stack` wrapper, project **swe-p27-local**, independent network and volumes, no application source mount/auto-reload. No sub2api/gpt-auto or port-8000/18372 service was changed. No paid inference occurred.

## Runtime and images

Docker Desktop 4.96.0; Engine/client 29.9.1; Compose v5.6.0. macOS ARM64 host, Linux ARM64 daemon/worker, official amd64 images under existing emulation. Native Linux x86_64 verification is NOT TESTED.

| Image | Identity | Architecture |
|---|---|---|
| swe-p27-local-api:20261022 | `sha256:27ab18dfaee231d7ad032c24acae4cbacaed3308b7dbc704ecdc8bdcca6e2374` | arm64 |
| swe-p27-local-worker:20261022 | `sha256:70f3c4fe075e9374f96492bdf0f44103c2d5d32535408b012d8db12179f3fc40` | arm64 |
| swe-p27-local-development:20261022 | `sha256:d1d9ffe567b7892e231244f10f2081d39653d5a70fa7da36445aaa2f7ab512a8` | arm64 |
| swe-eval-swebench-tools:5.0.2-02e7a74 | `sha256:a7613db2bc745ddfe61d9319adf94252462b1db0e1e609bf6e8412d642de2dff` | arm64 |
| swe-p27-local-sandbox:20261022 | `sha256:3bb698290df7c4f6125561d98581caec31a43bd309f41076e81db798de9ab8af` | arm64 |
| swe-p27-local-grader:20261022 | `sha256:01a5e8d5a3729a3b736a719b8305500da92f1505dcee9325c72739f7d026ed2f` | arm64 |

API, official-worker, official-development, local sandbox and grader builds completed with exit 0 using existing Dockerfiles and locks. The existing official-tools image was reused after identity/version verification: SWE-bench 5.0.2, commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`; mini-SWE-agent 2.4.6. All three application images have identical 50-file installed packages and 47 source/data files matching main. Production frontend asset IDs match the accepted build.

The old default `swe-eval-grader:phase1` failed source equality for `/opt/hidden/grade.py`. It was **not reused or retagged**. Fresh project-specific sandbox/grader builds are pinned by the new server-owned read-only task manifest. Correct/incorrect local grading and the entire installed suite passed against these images.

| Container | Final state | Automatic restarts | Image |
|---|---|---|---|
| `swe-p27-local-api-1` | running | 0 | `sha256:27ab18dfaee231d7ad032c24acae4cbacaed3308b7dbc704ecdc8bdcca6e2374` |
| `swe-p27-local-worker-1` | running | 0 | `sha256:70f3c4fe075e9374f96492bdf0f44103c2d5d32535408b012d8db12179f3fc40` |
| `swe-p27-local-stub-1` | running | 0 | `sha256:27ab18dfaee231d7ad032c24acae4cbacaed3308b7dbc704ecdc8bdcca6e2374` |

API exposes only `127.0.0.1:18327→8000`. Worker/stub have no published ports. Trusted worker alone mounts Docker socket; API/candidate do not. API/worker are non-root with read-only roots, dropped capabilities, tmpfs and no-new-privileges. The dummy stub is confined to the new project and stores only non-secret authorization-version observations.

## Persistence, migration and secrets

Active main database `/data/runs.sqlite3` and WAL/SHM, catalogue `/data/datasets/catalogue.sqlite3`, artifacts/history and administrative state live on **swe-p27-local_management-data**. Docker's inspected mount type is volume, Linux mountpoint `/var/lib/docker/volumes/swe-p27-local_management-data/_data`. No live SQLite file is bound from macOS. The only host binds are read-only configuration/task manifests, trusted stub code/test secrets and non-database test trace output.

Fresh CLI initialization created schema 2; explicit `migrate-admin` applied schema 3. Eleven management tables, main WAL mode, connection FK enforcement, integrity_check and foreign_key_check passed. Repeated migration is idempotent. No existing service database was migrated. Catalogue metadata was seeded using a supported SQLite online backup of the accepted promotion catalogue; immutable metadata/subset hashes match before and after testing.

`private.env` and `login-password.txt` are ignored, 0600, under the 0700 evidence directory. A random persistent AES-256-GCM master key and administrator bearer credential were generated once. Both trusted components use the same external key. UI login uses an independent PBKDF2 password and opaque HttpOnly/SameSite Strict server-side session, not a browser-held administrator bearer token. HTTP Secure-cookie=false is explicit for this loopback-only deployment; public origin is exactly http://127.0.0.1:18327. No invented session-signing variable was added.

The local console password is available only in `data/phase27-local-20261022T023632Z/login-password.txt`; no password/key value appears in these reports. The server key backup is `data/phase27-local-20261022T023632Z/secrets-backup.env`, separate from the database/private artifact archive. Protect and back it up separately. Original key reuse after restart and restore was verified; missing/wrong keys fail closed without plaintext fallback.

Online backups exist inside `/data/backups/local-acceptance/` and final `/data/backups/final-acceptance/`. A real restore into the separate new **swe-p27-local_restore-check** Linux volume passed integrity and encrypted-credential connection checks. Restricted `data/phase27-local-20261022T023632Z/local-private-evidence.tar` contains online DB snapshots and private official artifacts, excludes the external master file, and is not web served.

## Current catalogue and operator resources

Dataset revision `78f471bf655a3137b2e8a75af1501690ec009ec3`: **500 metadata / 20 original selected / 16 recorded prepared digests / 13 READY / 7 ineligible**. All thirteen READY digests actually exist and match. Fresh positive/negative verification covered SymPy 20590; READY status for the others preserves accepted evidence rather than claiming a fresh thirteen-task regrade.

The enabled usable local provider is `browser-stub`; model `browser-dynamic` produces a harmless actual source comment and is explicitly local_stub. The original twenty-task subset and saved two-READY-task `browser-quick-2` are visible in the UI. The intentionally interrupted test profile and secondary test provider/model are archived. Provider disable was verified then the normal local stub was re-enabled for operator use. No real provider credentials were imported.

## Health and deployment limitations

Final API/database ready, worker lease active, queue zero, active run none, orphan cleanup complete. Final three containers are running with zero automatic restarts. Six records persist: five completed unresolved official evaluations, one expected `worker_interrupted` from the intentional SIGKILL. No SIGBUS, exit 135, OOM, SQLite locked or WAL failure was observed on this named-volume deployment. This observation does not establish the root cause of historical macOS bind-mode crashes.

Remaining benchmark blockers:

- `psf__requests-1724` — blocked
- `psf__requests-1766` — blocked
- `psf__requests-1921` — blocked
- `psf__requests-2317` — interrupted
- `pytest-dev__pytest-10081` — blocked
- `pytest-dev__pytest-10356` — blocked
- `sphinx-doc__sphinx-10435` — blocked

Native Chrome has one explained cosmetic `/favicon.ico` 404; all actual page/API/asset workflows succeeded. No unresolved critical runtime/security/scoring defect was found in the tested scope. Long production soak, paid model capability, native x86_64 and external integrations are NOT TESTED. Operational commands and restore safeguards: `PHASE27_LOCAL_OPERATIONS.md`.

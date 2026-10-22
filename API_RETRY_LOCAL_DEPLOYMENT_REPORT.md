# API retry local deployment — PASS

User authorized deployment to the local test environment on 2026-10-22. The verified retry implementation is now running on **http://127.0.0.1:18327**, Compose project `swe-p27-local`. The original separate acceptance stack on port 18328 remains available. No port-8000/18372, sub2api, gpt-auto or unrelated service was changed.

## Deployment

- API: `swe-api-retry-api:20261022`, image `sha256:b5d500b52c2b180a18f272ea4dfdc7e503827b7fedf422b8b49901dcbf84c5af`.
- Worker: `swe-api-retry-worker:20261022`, image `sha256:0435a045df78e9ce7e533f0a07215ad93f25752444ad77381df360aab01c5089`.
- API/worker queues were verified idle before stopping. The API was stopped first, followed by a final database queue check before stopping the worker. Only these two authorized local services were recreated.
- Explicit `swe-eval migrate-retries` PASS. Core schema3 retained, feature marker `api_retry_schema=1`; integrity and foreign-key checks PASS.
- Persistent Linux named volume `swe-p27-local_management-data` remains shared by API and worker. SQLite WAL remains enabled; no active macOS bind-mounted database.
- 84 historical runs, 1006 logs, 11 model revisions and every other prior application table retain identical row hashes. Dataset catalogue unchanged: 500 metadata, 20 selected, 13 READY / seven ineligible. No historical batch was retried.
- Existing administrator/password/encryption configuration is byte-for-byte unchanged. Existing enabled provider credential decrypts with the original master key. Three enabled models remain available.
- All nine unrelated containers retain IDs/images/restart counters. New API/worker running with zero unexpected automatic restarts; worker ready, queue empty.

## Browser and verification

Actual host Chromium155 login PASS using the existing password. New batch controls default to three API attempts; automatic full-run recovery remains OFF unless selected. Recovery-category controls, mobile layout and session refresh PASS. No batch/evaluation was submitted, and no external/paid inference was made. No page errors or failed requests; the initial unauthenticated session401 and known cosmetic favicon404 were observed separately.

Prior exact-image acceptance remains 216 backend / 33 frontend tests, zero backend skips, with real Docker/official-grader retry and recovery workflows. This rollout used those image identities without rebuilding or changing source.

Actual evidence: `data/api-retry-local-deploy-20261022T093037Z/`: preflight, online database backups and row hashes, previous private configuration/Compose, deployment.log, verification.json, containers-after.json, browser-result.json and real screenshots. This directory is0700; private configuration and backups are0600. Password is not copied into this report.

## Operations and rollback

Continue using `data/phase27-local-20261022T023632Z/stack` for this console. The Compose override now selects the verified retry images. The password-only login is recorded in the existing protected `login-password.txt` beside that wrapper; no email/username is required.

Online backups are retained both inside the named volume at `/data/backups/api-retry-local-deploy-20261022T093037Z/` and privately under `data/api-retry-local-deploy-20261022T093037Z/database-backups/`. Secrets/configuration backups are separate protected `before-*` files. The original encryption key must accompany database recovery.

For rollback, first verify/drain both job queues and stop only this project's API/worker. Preserve a fresh online backup before changing data. The previous image/override settings are in before-compose.override.json; copying those settings back can restore the previous binaries only after ensuring no deferred recovery jobs remain. If restoring pre-migration data is required, use the verified backup via SQLite backup API while stopped and reconcile any records created after this deployment; never silently discard them. Do not delete named volumes or lower schema flags to force compatibility.

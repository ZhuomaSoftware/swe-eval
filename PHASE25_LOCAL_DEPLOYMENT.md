# Current local Phase 2.5 deployment

The verified changes are applied. Open http://127.0.0.1:8000/ and use the temporary
password already supplied. Only its PBKDF2 hash is stored in `.env`; no password
or API credential belongs in this guide. The API binds to loopback only.

Use these exact files for this local deployment:

```bash
docker compose -p swe-eval -f compose.yaml -f compose.console.local.yaml \
  -f compose.phase25.local.yaml --profile local-worker up -d --no-build --pull never api worker
```

To restart the same configured services without recreating them:

```bash
docker compose -p swe-eval -f compose.yaml -f compose.console.local.yaml \
  -f compose.phase25.local.yaml --profile local-worker restart api worker
```

Do not add `compose.dev.yaml`: these services run the verified installed packages,
with matching built frontend assets, instead of importing a watched source mount.
Future code edits require a deliberately tested image update. Do not run
`--build` with this override expecting a new deployment: its image IDs are pinned.
The existing model-profile file, worker key references, loopback port and named
SQLite volume are preserved. No model inference was used during promotion.

The API and worker image IDs are pinned in `compose.phase25.local.yaml`. Tasks
are loaded from `data/phase25-local/tasks` (mounted read-only). This is a copy of
the original fixture with only runtime image references changed to the verified
`swe-p25-remediation-sandbox:20261021t114531` and
`swe-p25-remediation-grader:20261021t114531`. Keep that directory for this running
deployment. Old default `swe-eval-*:phase1` tags were obsolete and are not used.
The hidden controller source and benchmark repository were not altered.

Promotion validation:13 HTTP/storage/artifact checks PASS; actual Chromium login,
health, safe logs and Git patch PASS; genuine good/bad hidden-grading fixtures both
matched expected outcomes without model calls. The prior accepted installed suite
was109/109 with zero skips; this promotion reuses those exact package images.

Evidence/rollback: `data/phase25-promotion-20261021T133012Z/`. Four prior runs and
all prior logs remain unchanged. Schema stays2. Two explicit patch-verification
results were added and do not count as model benchmarks. Backup/source copies
are private; preserve them rather than overwriting or restoring them into a live
service. Prior audit evidence was not changed. Actual external sub2api and
gpt-auto consumer integration remain BLOCKED; no such service was modified.

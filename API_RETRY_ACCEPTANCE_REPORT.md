# Reliable API retries — acceptance report

**PASS — isolated standalone reliability acceptance. Existing active console rollout NOT TESTED / pending authorization.**

Final source: main checkout HEAD `6bcf4340fc5e47901bdb1bc41852cf6908d567b8` plus source-manifest.json; no unrelated user changes committed/reset. Evidence `data/api-retry-20261022T083434Z/`. Host macOS ARM64, Docker `29.9.1`, Compose `5.6.0`, `linux/aarch64` worker; official amd64 task image uses the previously verified emulation. mini-SWE-agent `2.4.6`, official SWE-bench `5.0.2`. No native x86_64 verification or paid-model score is claimed.

## Final acceptance gates

| Gate | Status | Actual evidence |
|---|---|---|
| Temporary HTTP/network retries | PASS | Real 502/502/200 worker pipeline; real local HTTP read-timeout/reset and structured 503/429 tests |
| Permanent failures fail fast | PASS | 400/401/403/404/405/413/422, permanent DNS/TLS/quota/unknown tests; actual quota run one HTTP attempt |
| Rate-limit timing/cooldown | PASS | Retry-After minimum and numeric fields; actual 8-second durable deferred recovery; queue skips cooldown endpoints |
| Request timeout safety | PASS | Real timed-out buffered HTTP request then success; total retry/run/batch budgets bound requests |
| Optional linked run recovery | PASS | Actual transient exhaustion creates exactly one child, original task/profile/provider/limits snapshot retained |
| Budgets and cancellation | PASS | Real SQLite caps/deadline/cancel/stale-lease tests; original deadlines unchanged; no recovery after terminal cancellation/deadline |
| Independent-attempt identity | PASS | One original batch_attempt plus separate child; original failure remains; Pass@1 zero after operational recovery |
| Restart durability/idempotency | PASS | Actual API/worker restart with pending cooldown; same child/due timestamp; repeated scans/rollback/insertion/crash-window regressions |
| WebUI controls/history | PASS | Host Chromium real submission, desktop/mobile screenshots, parent/child recovery history, warnings and safe status display |
| Terminal/history integrity | PASS | Original parent metrics/error unchanged; sixteen historical run/log records exactly equal; completed/cancelled invariants pass |
| Cost/usage/statistics | PASS | Known subtotals separate, uncertain usage remains null, mixed currencies not summed, reasoning not double-counted, real CSV parser |
| Existing grading/credential security | PASS | Exact Phase 1.5 forgery, hidden isolation/confidentiality, encryption/SSRF/CSRF/leases/legacy/CSV/local-official tests all run |
| Final builds/full automated tests | PASS | 216 installed backend / 33 frontend, no skips; TypeScript/Vite and three builds; installed source hashes match |
| Actual agent → grader retry E2E | PASS | Batch `86852f6990cd4cc3936dbc87924a549b`, run `8cb9a92cccf042c69b4a271301e0f817`, actual official 22-assertion report and patch hash |
| Replace existing port-18327 services | NOT TESTED | Explicit task boundary forbids replacement without authorization; existing containers/images unchanged |
| Classify original fifteen errors retrospectively | BLOCKED | Historical handler and 867 retained worker log lines did not retain status/code/timeout phase; no speculative transient classification |
| Paid provider / native x86 / all-20 readiness | NOT TESTED | Outside authorized reliability scope; catalogue remains 500 imported, 20 selected, 13 READY / 7 ineligible |

## Error classification matrix

| Error | Policy |
|---|---|
| 408, 500, 502, 503, 504 | Potential transient; bounded safe buffered replay |
| Temporary 429 | Respect largest valid bounded Retry-After / wait hint, durable endpoint cooldown |
| insufficient_quota, quota_guard_request_too_large, eligible=0 without recovery time | Permanent quota; no retry/recovery |
| 400,401,403,404,405,413,422 | Fail once; no capability/model/auth fallback |
| Temporary DNS EAI_AGAIN, reset/refused, known transport outage, connect/read timeout | Potential transient; possible billing ambiguity |
| Permanent DNS, certificate verification, invalid URL/SSRF policy, malformed/oversized/unsupported stream, unknown error | Fail fast |
| Revoked/disabled credentials or provider/model | Stop before next dispatch; zero-dispatch failures report zero HTTP attempts |
| Repair/assertion failure, candidate error, user cancellation, whole evaluation timeout, batch deadline | Never automatic full-run recovery |

## Runtime ledger

- **Final request retry:** `8cb9a92cccf042c69b4a271301e0f817`: one logical request, three actual HTTP attempts, two retries, one real source-edit action, 22 official assertions / 21 passed / unresolved. API success did not become a fabricated repair success. Token/cost total remained unknown after ambiguous failed transmissions.
- **Linked recovery:** parent `e7095c2a6db0445a84e81dda7908dbb9` failed after three HTTP attempts; child `c27a4661ce54423b86e7da145007810f` completed real official grading with two HTTP requests. One scheduled attempt remains one; benchmark Pass@1 = 0, operational HTTP count = 5. Child copied original snapshot exactly.
- **Deferred restart:** child `a88608938ab54a9788c93770c7aa6149` retained its original next_eligible_at and configuration across actual API/worker restart; exactly one child persisted. Parent metrics/error unchanged.
- **Clean state:** parent `19fc3cb8abe64f56a0caaa3a931286a1` executed a source modification before exhausting later requests. Child `948681ed52c2427bb05ca93da158c5fa` asserted the marker was absent in its new Docker checkout, made its own patch, and executed the real 22-assertion official grader. No partial source reuse.
- **Permanent quota:** actual HTTP429 insufficient_quota made one request and no recovery child.
- **Provider disabled:** `2aedd24f881e4c56bd2f090515f9d977` failed safely before transport; zero HTTP attempts / zero API error transmissions. Provider was re-enabled with a new revision; historical binding remained intact.
- **SQLite/deployment:** named volume `swe-api-retry-acceptance_retry-data`; schema3 + explicit retry marker1; online backup/integrity/foreign keys PASS. No macOS host-bind SQLite used.
- **Confidentiality:** 42 ordinary payloads plus browser assets/worker logs/CSV/JSON scanned for dummy credential/admin/master canaries; none exposed. Credential ciphertext verified in database.
- **Current health:** worker ready, queue empty, no active job, zero unexpected automatic restarts or remaining candidate containers. Existing console container IDs/images/restart counters and original failures unchanged.

## Regression evidence and reproduction

```sh
python3 data/api-retry-20261022T083434Z/build_images.py
python3 data/api-retry-20261022T083434Z/run_installed_tests.py
python3 data/api-retry-20261022T083434Z/run_frontend.py
/tmp/swe-p27-local-host-browser/bin/python data/api-retry-20261022T083434Z/run_browser.py
python3 data/api-retry-20261022T083434Z/runtime_recovery.py
python3 data/api-retry-20261022T083434Z/dirty_recovery.py
python3 data/api-retry-20261022T083434Z/disabled_dispatch.py
/tmp/swe-p27-local-host-browser/bin/python data/api-retry-20261022T083434Z/browser_history.py
python3 data/api-retry-20261022T083434Z/final_checks.py
```

These are retained stateful fixtures. Repeated creation runners require fresh unique model/idempotency IDs or a separately initialized test project; do not reset retained databases, regenerate keys, or replay scripts against the existing port-18327 deployment. Build/test commands are repeatable; data-creating commands are documented exact executed procedures.

Final suite: **216 tests in 127.909 seconds, OK, zero skips**; frontend **33 PASS**, TypeScript/Vite PASS. Tests in test_retries cover the requested request classifications/retry budgets, actual transport timeout/reset, no unsafe streaming replay, runtime disable, recovery transaction rollback/duplicate prevention, genuine unresolved/timeout exclusion, manual retry, cancellation/deadline, stale owner, immutable configuration, deferred restart and Pass@1. Real worker tests add clean-workspace and actual restart evidence. Synthetic stubs do not establish model intelligence. Earlier failed backoff/backup experiments remain preserved and are explained in the implementation report.

**Deployment recommendation:** ready for an explicitly authorized local-console rollout using the guide. Keep the tested isolated stack available. Historical failure diagnosis remains limited by missing old telemetry; no historical outcome was upgraded or replayed.

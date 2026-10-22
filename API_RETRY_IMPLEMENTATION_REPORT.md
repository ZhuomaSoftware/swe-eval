# Reliable API retries — implementation report

Implemented and verified in the main working tree, with an independent Docker acceptance deployment. Existing console/services were not replaced. Evidence: `data/api-retry-20261022T083434Z/`. Baseline HEAD remains `6bcf4340fc5e47901bdb1bc41852cf6908d567b8` plus preserved local changes; exact final implementation is identified by source-manifest.json and final-images.json, not a fabricated new Git revision.

## Root cause before behavior changes

The original batch `43d1f94ad2c244dab834b6e1e845f851` contained 15 API failures with one logical request/API error each, plus one whole-evaluation timeout. The original transport discarded HTTP status/body fields, and the official engine persisted only `model_api_error` / `official_environment_or_evaluation_error`. All sixteen retained run/log records were captured and later compared unchanged. None of the fifteen can be positively categorized as transient from retained evidence. The retained historical worker stdout window was also scanned: 867 lines, with no retained HTTP-status or quota-code occurrences. No paid/external probe or historical retry was performed. See `ROOT_CAUSE.md` and original-failures.json in the evidence.

`OpenAICompatibleProvider.complete` formerly made one transport call and immediately propagated ProviderError through MiniModel/mini-SWE-agent to terminal finalization. Two numbered benchmark attempts were independent attempts, never retries. The manual retry endpoint remains linked and uses current enabled configuration as before.

## Actual source changes

- `provider_errors.py`: secret-free structured failure categories, HTTP status, safe allowlisted provider code, retryability, retry timing and billing ambiguity.
- `retries.py`: validated request/recovery policy models; structured HTTP/quota/transport classification; bounded timing hints; lease/credential checks; durable provider cooldown; transactional unique-parent recovery and admission decisions.
- `providers.py`, `outbound.py`: buffered non-streaming request retries, jitter/backoff/deadlines, actual HTTP accounting, bounded error-body parsing, preserved SSRF/DNS pinning/TLS/no-proxy/no-redirect controls, safe timeout/reset classification. Permanent DNS/certificate/unknown errors fail fast.
- `schema.py`: logical/physical request counters, retry/backoff/cooldown/timestamps/outcome, safe final error, exhaustion/recovery eligibility and billing uncertainty; separate known usage/cost subtotals.
- `center_schema.py`, `center.py`, `management_api.py`: explicit immutable batch policies, preview/reservation for optional recovery, total-run/queue/request caps and retry-aware experimental fingerprints. Omitted optional fields retain old idempotency hashes. New WebUI batches explicitly select retry policy; older omitted-policy clients/admitted runs retain prior behavior. API clients can submit a single-item batch with `api_retry` to configure retries.
- `storage.py`, `service.py`, `worker.py`: atomic parent verdict + child/decision insertion, current-lease enforcement, durable deferred FIFO eligibility, batch membership/cancellation/deadline accounting separate from independent attempts, restart-safe scanning. An interrupted worker cannot reopen a terminal batch through saved pre-commit eligibility.
- `engine.py`, `official_engine.py`: use immutable policies, remaining absolute batch deadline, trusted runtime hooks; preserve grading/handoff/clean sandbox architecture.
- `analytics.py`, `api.py`: benchmark denominators exclude automatic children, while operational recovery/HTTP/known-cost metrics are separate in JSON/CSV. Unknown/mixed-currency costs stay unknown; reasoning tokens are not added twice. Zero-dispatch provider failures do not invent HTTP requests.
- `cli.py`, `migrations/004_retries.sql`: explicit additive `migrate-retries`; core schema remains 3, feature marker is `api_retry_schema=1`.
- `frontend/src/RetryControls.tsx`, `BatchWizard.tsx`, `main.tsx`: Chinese retry controls, original/recovery/HTTP limits, billing warnings, remaining-time policy, recovery categories, parent/child history, cooldown/timing/error/exhaustion labels and pending-recovery cancellation access.
- Permanent regressions: `tests/test_retries.py` (51 new tests), `RetryControls.test.tsx`, additional recovery-reservation BatchWizard regression. Existing tests were retained.

## Runtime corrections caught independently

The first real browser evaluation exposed a negative-sleep race: a database/credential check outlasted the remaining backoff. It failed after two HTTP calls. That failed run/artifacts remain under browser-first-failed and `*-first-failed.json`; the loop now rechecks remaining time before sleeping, and a real-clock regression reproduces the case. No failed record was rewritten. A review also closed the worker-interrupted pre-commit eligibility window and separated zero-dispatch rejection from physical HTTP errors.

The initial read-only mount attempt to back up the live WAL database failed with SQLite unable-to-open. The supported recovery was an online backup inside the existing API container, then migration of its independent copy. Original database rows/services were not migrated/restarted. The copied database preserved 84 runs, 1,006 logs, five encrypted credentials, eleven model revisions and five subset revisions; integrity/foreign keys and migration idempotency passed.

## Verification and limits

Final installed backend: **216/216, zero failures/errors/skips**. Frontend: **33/33**, TypeScript/Vite PASS. Three Docker images built; 46 Python/SQL source files match API, worker and installed-test package. Real Chromium batch `86852f6990cd4cc3936dbc87924a549b` / run `8cb9a92cccf042c69b4a271301e0f817` received 502, 502, 200, captured a source patch, and the real official grader executed 22 assertions (21 passed), correctly unresolved. This is infrastructure evidence, not model capability.

Actual linked recovery, deferred API/worker restart, permanent quota fail-fast, partial-source discard, zero-dispatch disable, response/export/asset credential scans and original-record preservation passed. No production/sub2api/gpt-auto changes, no paid requests and no retry of the historical batch. Existing port 18327 continues on its previous images; final test stack is `http://127.0.0.1:18328`.

Whole-run timeout/crash recovery and streaming inference remain intentionally unsupported. Long cooldown can cause work to wait until its original deadline or be declined. Usage ambiguity can stop further logical calls under a total-token budget, even after a request retry eventually returns a valid action. The old fifteen HTTP codes cannot be reconstructed. Rollout to the existing console requires separate authorization and an explicit online backup/migration.

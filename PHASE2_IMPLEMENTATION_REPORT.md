# Current implementation status — Phase 2.5

The historical Phase 2 account below is retained for context. Phase 2.5 corrects
all eight independent-audit findings in diagnostics, batch finality, trusted
eligibility, freshness, configuration identity, CSV cells, cost presentation and
worker observations. `PHASE2_FINAL_FIX.patch` was reviewed, not blindly applied;
its eligible-completion timestamp correction is incorporated with separate
activity/success/export timestamps. It remains an unchanged historical patch.

See `PHASE2_REMEDIATION_REPORT.md` for changes and
`PHASE2_REACCEPTANCE_REPORT.md` for final runtime scope/evidence. Live sub2api and
gpt-auto consumer acceptance remain blocked; local contracts are not federation
or consumer proof. No Phase 3 functionality was added.

---

# Phase 2 implementation report

Version 0.2.0. This report covers the tested working tree, not a pushed commit or
hosted CI deployment. Prior Phase 1 audit/re-acceptance artifacts are preserved. A late-discovered
source-mounted auto-reloader also reached the existing SWE development API and
initialized schema 2; this unintended operational failure is disclosed in the
acceptance report. It prevents an unqualified claim that existing SWE services
were unaffected. No sub2api service was targeted.

## Implemented capabilities

- Same-origin React/TypeScript/Vite administration dashboard, Simplified Chinese,
  responsive layout and dark/light themes. Actual overview, run filters/history,
  detail logs/diff/metadata, batch form/progress/cancellation, model comparison,
  tasks, server-owned model profiles, health and integration settings.
- Separate console password and durable HttpOnly/SameSite session, CSRF/origin
  validation, login throttling, CSP and frame denial. No API key/token in browser
  assets, URL parameters or localStorage. Existing bearer API remains compatible.
- Versioned additive migration 2; immutable run provenance snapshots and explicit
  batch attempt identities. Atomic idempotent submission and capacity checks,
  full request reservation, bounded Cartesian expansion, deadline cancellation,
  restart-safe derived progress and existing single-worker lease/queue.
- Version-aware analytics with matched task subsets, separate valid/E2E
  denominators, first-independent-attempt Pass@1, interpolated latency percentiles,
  known/unknown token and cost semantics, CSV/JSON exports, task/run drilldown.
  Historical marker/unattributed and patch-verification data cannot score models.
- Read-only sub2api metadata adapter based on inspected source, server-owned
  profile/group mapping, GET-only whitelisted metadata, schema-safe atomic import.
  No account credentials, direct database reads, gateway file changes or routing
  writes. Concrete upstream attribution is never inferred from group identity.
- Authenticated versioned gpt-auto informational export with origin/protocol/
  outcome/upstream/benchmark eligibility. No capability weights or routing APIs.
- Worker/queue/cleanup/HTTP error observations and separate API/worker/Docker/
  upstream readiness semantics. Docker is a last-successful-probe indication.
- Embedded dashboard in wheel and API image; pinned npm graph and Node build
  image; deployment/reverse-proxy configuration, CI frontend build/test gates.

## Files changed or added for Phase 2

Relative to `data/phase2-20261021/baseline.json` (not Git HEAD, which also contains
pre-existing Phase 1.5 changes):

| Area | Files |
| --- | --- |
| Dashboard | `frontend/package*.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/style.css`, `src/api.ts`, `src/i18n.ts`, component/browser tests and configs |
| API/auth | `src/swe_eval/api.py`, `sessions.py`, `center_schema.py`, `config.py` |
| Orchestration | `center.py`, `storage.py`, `service.py`, `worker.py` |
| Engine integration | `engine.py`: load server-validated snapshot limits/reasoning after original configuration check; no grader/agent/provider replacement |
| Analytics/export | `analytics.py` |
| Gateway boundary | `integrations.py`, `config/sub2api.example.json` |
| Persistence | `migrations.py`, `migrations/002_center.sql`, offline `.down.sql` |
| Regression | `tests/test_center.py`; all prior tests retained |
| Packaging | `pyproject.toml`, `__init__.py`, `MANIFEST.in`, `tools/package_release.py`, `tools/center_smoke.py`, `tests/support/model_stub.py`, both CI workflows |
| Deployment | `docker/service.Dockerfile`, `docker/browser-tests.Dockerfile`, `compose.center.yaml`, `deploy/nginx-center.conf`, `.env.example`, ignore files |
| Documentation | Four Phase 2 reports/guides; README links |

## New/extended API surface

All administrator endpoints accept the existing bearer or protected browser
session; shadow token has no mutation authority.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/`, `/console`, `/assets/*` | Static independent dashboard, no sensitive initial data |
| POST/GET/DELETE | `/api/v1/session` | Login, session/CSRF retrieval, logout |
| GET | `/api/v1/overview` | Actual counts, trusted metrics and operations |
| GET | `/api/v1/system` | Worker lease/readiness, queue and operational events |
| POST/GET | `/api/v1/batches` | Atomic submission / paginated listing |
| GET | `/api/v1/batches/{id}` | Explicit attempts and persistent progress |
| POST | `/api/v1/batches/{id}/cancel` | Stop queued/active batch work |
| GET | `/api/v1/comparison` | Matched, versioned grouped analytics |
| GET | `/api/v1/comparison/export` | CSV or JSON with methodology/provenance |
| GET | `/api/v1/shadow/results` | Read-only gpt-auto-swe-v1 results |
| GET | `/api/v1/integrations/sub2api` | Sanitized cached metadata and integration status |
| POST | `/api/v1/integrations/sub2api/sync` | Server-only GET metadata fetch; no gateway mutation |
| GET (extended) | `/api/v1/runs` | Profile/upstream/benchmark/state/date/protocol/batch filters and total count |
| GET (extended) | `/api/v1/models` | Safe endpoint fingerprint, provenance configuration |

## Known limits and integration dependencies

Actual sub2api management sync and session federation are BLOCKED pending an
authorized compatible staging endpoint and admin metadata credential. Local HTTP
contract tests are explicitly not live integration proof. The unsafe JWT-in-iframe
URL helper is not used. No sub2api source/config/service was changed.
No fresh paid/external inference was requested. Existing live-agent evidence is
prior evidence; new executions use explicitly labeled local HTTP model stubs.
There is one real local benchmark, no official SWE-bench adapter or public ranking.
Monetary caps are unavailable; requests/steps/time have independent bounds.
Operational event counters are bounded retained observations, not exact host
restart telemetry. Worker Docker authority requires a disposable VM. Native
macOS worker supervision remains unverified. See the acceptance report for
executed results and remaining deployment limitations.


Final source boundary: the new `FreshnessIntegrityTests` exposed an export timestamp
bug after the 96-test built-image run. `PHASE2_FINAL_FIX.patch` is a minimal,
fully tested correction (97 tests pass in an isolated source copy). It remains
unapplied pending approval to stop the existing source-mounted development
containers; current-root full acceptance is therefore not claimed. This patch
and the live sub2api dependency are remaining work, not completed features.

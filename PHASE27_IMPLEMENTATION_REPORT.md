# Phase 2.7 implementation report

Status: implemented and runtime-verified for the standalone Linux-volume deployment. Final decision and exclusions are in `PHASE27_ACCEPTANCE_REPORT.md`.

## Baseline and promotion gate

Phase 2.6 was promoted into the main repository before Phase 2.7 began. The accepted checkpoint is `618ff61795c2c672e5976375b17a376d1837630b`, tag `phase26-main-accepted-20261021T171252Z`. Its 97 source-manifest files matched the accepted isolated source; 29 Phase 2.6 paths were merged, with 129 backend tests, nine frontend tests and an actual four-attempt official browser batch passing in MAIN. See `PHASE26_PROMOTION_REPORT.md`.

Phase 2.7 was developed directly under `/Users/user/Program/swe-eval`. There is no long-lived Phase 2.7 source copy. The `data/phase27-dynamic-20261021T172902Z/` directory contains test deployment state, runners, logs and restricted evidence only. Unrelated `.env.example`, `.gitignore` and `VALIDATION.md` changes remain byte-for-byte equal to their pre-promotion copies. Existing development container IDs/images/start times and the active database were preserved; no sub2api service was changed.

Final source checkpoint: `phase27-main-verified-20261021T183759Z`. The exact commit is recorded in the evidence `source-checkpoint.json` after checkpoint creation. Source hashes identify the tested implementation independently of Git metadata.

## Actual changes

- **Versioned providers:** create/edit/enable/disable/archive, bounded non-inference connection testing, recent error history, associated profiles, credential replacement and explicit revocation. Provider revisions and model revisions are append-only, with expected-revision checks.
- **Secret storage:** AES-256-GCM, random nonce, database/provider/credential-version AAD, externally supplied master key. Stored plaintext and ciphertext are absent from ordinary responses. Rotation preserves admitted bindings; explicit revocation fails closed. Missing/wrong master material never falls back to plaintext.
- **Outbound transport:** HTTP(S) URL validation, exact server-owned private-origin exceptions, all-answer DNS checks, literal-address connection pinning, original-host TLS validation, no redirects/proxy inheritance, bounded DNS/request/body handling. A real slow HTTP/1.0 regression verifies the whole-request deadline.
- **Dynamic models:** database-backed profile creation/edit/archive/disable, provider/model/upstream identities, reasoning capabilities, time/token/step/request budgets, finite pricing and USD/CNY/EUR currency. New admissions read current enabled revisions; workers resolve immutable model/provider/credential versions from SQLite without service restart. Existing file profiles remain read-only fallback and retain their original snapshot hash shape.
- **Historical idempotency:** absent optional subset fields do not change old Phase 2.6 request hashes. Exact request replay returns its original batch even when the profile is subsequently disabled. Changed request content under the same key rejects with 409; replay creates no attempts.
- **Datasets:** reuse the official Phase 2.6 importer and private catalogue, pinned metadata jobs, revision browsing/archive/restore, search and pagination, real readiness counts and persistent validation observations. Metadata synchronization never prepares images.
- **Subsets:** create, duplicate, archive and revise immutable task membership. Batch snapshots bind ID/revision/fingerprint; comparisons keep that coverage separate. Historical membership does not change after editing.
- **Administrative execution:** durable SQLite queue under the existing single worker lease. Explicit validation IDs, maximum five tasks, sequential execution, bounded test and wall time, progress, interruption recovery, cancellation and container cleanup. FastAPI never runs repository installation scripts.
- **WebUI:** grouped Chinese navigation, providers/datasets/subsets/audit pages, editable model forms, four-stage batch review, actual counts/limits/pricing uncertainty, compact overview and improved resource metrics. Existing dark-green styling remains. Known small costs retain meaningful precision; mixed-currency totals remain unknown instead of summing incompatible units.
- **Exports/observability:** CSV retains formula protection and adds currency/mixed-currency metadata. JSON retains configuration/subset provenance. System responses include administrative jobs; dataset management displays their progress and classifications.

## Dependencies, persistence and trust

Added `cryptography==50.0.2`, `cffi==2.1.1`, `pycparser==3.11` in the locked core environment. Official SWE-bench stays at 5.0.2 / `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`; mini-SWE-agent stays 2.4.6 in its existing separate dependency arrangement. No UI framework or scheduler was added.

Explicit migration `003_management.sql` creates provider/model revision and credential tables, subset revisions, dataset archival state, administrative jobs, connection events and non-secret audit records. Startup supports schema 2/3 but does not auto-apply migration 3. `swe-eval migrate-admin` is the explicit operator action. A copied accepted database preserved all six runs and 71 logs; migration idempotency, rollback on failure and foreign-key/integrity checks passed. No active/production database was migrated.

Local grading-v2, official test-log grading, legacy results, gold validation and deterministic-provider experiments retain separate meanings. Official results continue to have `trusted_evidence=false` relative to local-v2 trust semantics. No sub2api/gpt-auto integration, routing, billing, public ranking or paid inference was added.

## Runtime issues found and addressed

Real Chromium testing caught wrapped-select label ambiguity, unavailable `crypto.randomUUID` on approved HTTP origins, and modern HTML pattern `/v` incompatibility. Explicit accessible labels, `getRandomValues` IDs and compatible patterns fixed these; permanent regressions and final real-browser assertions remain.

Two isolated host-bind SQLite worker exits were observed (135, `OOMKilled=false`); the diagnostic run showed `Fatal Python error: Bus error` at `storage.py:59`, `connection.commit()` during heartbeat. Recovery preserved completed results and marked the interrupted run `worker_interrupted`, without silent re-execution. The precise Docker Desktop/filesystem cause remains unproven. Final acceptance uses a native Linux named volume, including a new successful evaluation after restart and a live worker process check. The committed staging template uses that storage boundary; macOS bind-mounted SQLite is excluded.

## Verification and exact reproduction

- Final installed image: **157/157**, zero failures/errors/skips, 107.186 seconds. Includes exact original F-01 grading forgery, controller/output isolation, recovery/stale writes, confidentiality, batch finality, analytics and actual official gold/negative/timeout checks.
- Frontend: **20/20**, TypeScript/Vite build PASS.
- Chromium: complete management workflow PASS, four genuine agent-to-official-harness evaluations, one real gold/negative validation, running cancellation, post-restart execution, persistence, provider disable, export and response-confidentiality checks. Independent overview/history/theme browser test PASS.
- Supplemental actual HTTP management: **14 checks PASS**, including rotation/revocation, archive/restore, duplicate aliases, immutable subset revisions, completed replay after disable and real administrative wall timeout.
- Independent HTTP/SQLite checks: **60 PASS**. Actual pinned synchronization: **500 records, zero inserts, zero image preparation**.
- All three image packages match each other (50 files) and 47 source/data files match main source.

```sh
python3 data/phase27-dynamic-20261021T172902Z/build_final_images.py
python3 data/phase27-dynamic-20261021T172902Z/run_installed_tests.py
python3 data/phase27-dynamic-20261021T172902Z/run_browser.py
python3 data/phase27-dynamic-20261021T172902Z/run_readonly_browser.py
python3 data/phase27-dynamic-20261021T172902Z/run_supplemental.py
```

Use the retained isolated fixture or a fresh independent Linux-volume copy. Browser creation IDs are persistent; preserve previous state/evidence before resetting an isolated fixture. Do not regenerate the retained master key, point these runners at an active database, or reuse the older bind-mounted Compose snapshot for deployment. See the deployment guide for safe bootstrap and rollback.

## Exact owned files (43)

- `PHASE27_ACCEPTANCE_REPORT.md`
- `PHASE27_ARCHITECTURE.md`
- `PHASE27_DEPLOYMENT_GUIDE.md`
- `PHASE27_IMPLEMENTATION_REPORT.md`
- `README.md`
- `compose.management.yaml`
- `config/models.managed.json`
- `frontend/e2e/management.spec.ts`
- `frontend/e2e/swebench.spec.ts`
- `frontend/src/App.test.tsx`
- `frontend/src/BatchWizard.tsx`
- `frontend/src/Management.test.tsx`
- `frontend/src/Management.tsx`
- `frontend/src/api.ts`
- `frontend/src/i18n.ts`
- `frontend/src/main.tsx`
- `frontend/src/style.css`
- `pyproject.toml`
- `requirements-core.lock`
- `src/swe_eval/administration_jobs.py`
- `src/swe_eval/analytics.py`
- `src/swe_eval/api.py`
- `src/swe_eval/center.py`
- `src/swe_eval/center_schema.py`
- `src/swe_eval/cli.py`
- `src/swe_eval/config.py`
- `src/swe_eval/dataset_validation.py`
- `src/swe_eval/engine.py`
- `src/swe_eval/management.py`
- `src/swe_eval/management_api.py`
- `src/swe_eval/management_schema.py`
- `src/swe_eval/migrations.py`
- `src/swe_eval/migrations/003_management.sql`
- `src/swe_eval/official_engine.py`
- `src/swe_eval/outbound.py`
- `src/swe_eval/providers.py`
- `src/swe_eval/schema.py`
- `src/swe_eval/secret_store.py`
- `src/swe_eval/security.py`
- `src/swe_eval/service.py`
- `src/swe_eval/storage.py`
- `src/swe_eval/worker.py`
- `tests/test_management.py`

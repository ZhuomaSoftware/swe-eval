# Phase 2.6 SWE-bench acceptance report

## Decision and tested scope

**CONDITIONALLY ACCEPTED for isolated staging with 13 genuinely verified official instances.** Full 20-instance readiness remains **BLOCKED**. This is an implementation/infrastructure acceptance, not an official full SWE-bench score or live model capability evaluation. Production rollout/source promotion has not been performed.

Criterion counts: **22 PASS, 0 FAIL, 1 BLOCKED, 3 NOT TESTED** across the explicitly scoped 26-row matrix below. The 7 per-instance blockers are a separate task-readiness count, not seven extra matrix criteria. No unresolved demonstrated P0/P1 defect was found within this tested limited scope; the documented official test-log trust boundary is a material limitation, not a claim of local-v2 adversarial assurance.

Baseline HEAD: `ccf38665e142a93e62fb761908bd7bb248d7cb4c` plus preserved changes. Tested source is **`data/phase26-swebench-20261021T135404Z/project/`**, identified by `final-source.json`; there is no new Git commit. Evidence root **`data/phase26-swebench-20261021T135404Z/`**. Existing Phase 2.5 source/services remain unchanged. Tested Docker Desktop Linux ARM64: Engine 29.9.1, Compose 5.6.0, 10 CPUs, 8,319,504,384 bytes RAM, official linux/amd64 images through actual emulation. Preflight observed over 300 GB free data storage and separately checked daemon capacity; concurrency one.

## Actual acceptance matrix

Evidence references below are relative to the evidence root, usually `output/`; tests and source are under `project/`.

| ID | Criterion | Status | Evidence / method | Limits |
|---|---|---|---|---|
| P26-01 | Accepted Phase 2.5 baseline and preservation | PASS | baseline.json; output/baseline-installed-suite.log; shared-checkout-preservation.json | 109 baseline tests; no source promotion |
| P26-02 | Actual upstream CLI/version and dependency isolation | PASS | official-*-help.txt; reproducible-tools-build.log; project/src/swe_eval/swebench_upstream.json | Pinned 5.0.2 shim; upgrades require compatibility review |
| P26-03 | Official 500-instance metadata import | PASS | metadata-import-retry.log; cli-dataset-list.json; catalogue-final.sqlite3 | Metadata import does not prepare images |
| P26-04 | Immutable revisions, idempotency and recovery | PASS | test_official.DatasetTests; DatasetTransactionTests | Source-content conflicts abort; older revisions retained |
| P26-05 | Reference/test confidentiality on ordinary surfaces | PASS | confidentiality-checks.json; browser-confidentiality.log; final-http-acceptance.json | Raw trusted artifacts intentionally remain operator-only |
| P26-06 | Deterministic internal 20-instance manifest | PASS | final-dataset-manifest.json; project/config/swebench-curated-20-v1.json | Four repositories; no representativeness claim |
| P26-07 | Stage A real official gold and negative | PASS | stage-a-results.json; final-installed-complete-suite.log | Sympy 20590: gold 22/22; unmodified 21/22 |
| P26-08 | Stage B five genuine environments and gold checks | PASS | stage-b-selected.json; stage-b-results.json | Five tasks across four repositories, gold and negative |
| P26-09 | Stage C all twenty executable and verified | BLOCKED | final-dataset-manifest.json; stage-c-expanded.log; subset-preparation-retry.log | 13 ready, 7 blocked; failures remain visible |
| P26-10 | Negative/error/timeout/missing-result classifications | PASS | test_official.OfficialDockerRuntimeTests; negative-operations.json | Empty predictions skipped, not claimed as executed tests |
| P26-11 | Real coding-agent patch to official report and DB | PASS | agent-smoke-final.json; browser-final-artifact/; stub-trace/model-requests.jsonl | Deterministic local provider; no live model-quality claim |
| P26-12 | Patch/configuration identity and cache collision prevention | PASS | test_official.HarnessContractTests; private safe-result.json artifacts | Distinct patches/replays get distinct harness identities |
| P26-13 | Restricted candidate execution and cleanup | PASS | grading-container-isolation.json; recovery-checks-v2.json; original v2 Docker attacks | 48 actual grader probes; official parser trust differs from local v2 |
| P26-14 | Existing durable batches and terminal invariants | PASS | test_official.OfficialAPITests; recovery-checks-v2.json | Two tasks x two profiles executed; SQLite 8-attempt expansion also checked |
| P26-15 | API restart, worker interruption and lease recovery | PASS | recovery-checks-v2.json; recovery-batch-final-v2.json | Normal 90-second lease; interrupted attempt failed, queued attempt completed once |
| P26-16 | Versioned analytics, usage, unknown costs and exports | PASS | independent-statistics.json; final-http-acceptance.json; browser-export.csv/json | 28 independent arithmetic checks; local/stub/official evidence kept separate |
| P26-17 | Real administration browser workflow | PASS | browser-final-artifact/run.log; browser-checks.json; screenshots | No mocked HTTP; no page errors or failed network requests |
| P26-18 | Administrative CLI and bounded resumable validation | PASS | cli-dataset-list.json; cli-dataset-status.json; cli-validation-dry-run.log; cli-validation-resume.json | Concurrency one; image preparation explicit |
| P26-19 | Explicit database changes and accepted-data copy | PASS | migration-copy.json; migration-copy-final.log | Runs schema stays 2; separate catalogue schema 1; four copied runs and 39 logs preserved |
| P26-20 | Phase 1.5/2.5 integrity regressions | PASS | final-installed-complete-suite.log | Original grading forgery, hidden isolation, stale writes, terminal states, auth, CSV, freshness retained |
| P26-21 | Final installed suite and build artifacts | PASS | final-installed-complete-suite.log; final-image-identities.json; final-installed-source-equality.json | 129 tests, zero failures/errors/skips; final worker/test use documented offline build path |
| P26-22 | Native Linux x86_64 deployment | NOT TESTED | ARM64 resource observations and amd64 image execution only | No native x86_64 host available; reproducible path in deployment guide |
| P26-23 | Official task-repository source image build | NOT TESTED | Inspected task repo/CLI and source; registry image preparation used | Avoided additional bulk builds; no claim that source build was exercised |
| P26-24 | Live paid-model capability evaluation | NOT TESTED | Local provider trace only | No authorization for paid inference; deliberately excluded |
| P26-25 | License/source attribution review | PASS | license-review.json; architecture attribution | No public/commercial redistribution; dataset/task licensing needs review before publication |
| P26-26 | Operator documentation and reproducible evidence | PASS | Five PHASE26 documents; helper scripts; final-source.json; SHA256SUMS.json | Isolated workspace and artifacts retained; existing services untouched |

## Dataset and staged official grading

| Observation | Count |
|---|---:|
| Pinned official metadata imported | 500 |
| Deterministically selected instances | 20 |
| Independent repositories | 4 |
| Actually prepared images | 16 |
| Genuine gold patches resolved | 13 |
| Genuine unmodified negatives unresolved | 13 |
| Executable and verified ready | 13 |
| Blocked selected instances | 7 |

Dataset revision `78f471bf655a3137b2e8a75af1501690ec009ec3`; subset `curated-20-v1`, SHA-256 `bca369a9dc0d61df6398a72ea0042b6f89c7f23a66758c8fd444e84574accf89`. Full instances, repositories, base commits, image/report hashes and timestamps: `PHASE26_SWEBENCH_DATASET_MANIFEST.md` and `output/final-dataset-manifest.json`. Selection does not imply statistical representativeness.

Stage A actually exercised `sympy__sympy-20590`: gold 22/22 expected assertions passed, unmodified 21/22 with unresolved official report. Empty prediction was accurately reported upstream-skipped, not executed. Invalid/incorrect patch and timeout cases were also exercised. Stage B verified Sympy 20590/11618, Requests 1142, Pytest 10051 and Sphinx 10323 across four repositories. Stage C proceeded sequentially toward all 20, retaining failures and completing independent tasks.

| Blocked instance | Preparation | Actual limitation |
|---|---|---|
| pytest-dev__pytest-10081 | blocked | Official registry image preparation failed (EOF/DNS); bounded retry failed or was safely interrupted. No successful environment validation. |
| pytest-dev__pytest-10356 | blocked | Official registry image preparation failed (EOF/DNS); bounded retry failed or was safely interrupted. No successful environment validation. |
| sphinx-doc__sphinx-10435 | image prepared | Actual test-output environment failure with candidate network disabled; instance remains unready. |
| psf__requests-1724 | image prepared | Actual test-output environment failure with candidate network disabled; instance remains unready. |
| psf__requests-1766 | image prepared | Actual test-output environment failure with candidate network disabled; instance remains unready. |
| psf__requests-1921 | blocked | Official registry image preparation failed (EOF/DNS); bounded retry failed or was safely interrupted. No successful environment validation. |
| psf__requests-2317 | blocked | Official registry image preparation failed (EOF/DNS); bounded retry failed or was safely interrupted. No successful environment validation. |

The four unprepared tasks need reliable registry access/retry; three prepared images have network-dependent gold environments under network none. These are environment blockers, not model repair failures. `requests-2317` had an unsuccessful registry preparation followed by an interrupted retry; interruption is not validation success. No replacement handcrafted tasks were substituted.

## Final automated and built-image evidence

* Accepted baseline: 109/109 installed tests before changes (`baseline-installed-suite.log`).
* Final installed suite: **129 tests in 109.004 seconds, OK; zero failures, errors or skips** (`final-installed-complete-suite.log`). Docker integration and official runtime flags were enabled. This includes genuine gold/negative/invalid/timeout, original local grading forgery/hidden isolation, stale writes, worker recovery, terminal invariants, auth/CSRF, CSV safety, freshness and legacy isolation tests.
* Frontend: 9/9 tests, TypeScript and production Vite build passed (`frontend-tests-build.log`).
* Final installed API/worker/test package manifests match, including static assets (`final-installed-source-equality.json`). Official virtualenv pip check and accepted lean-agent compatibility gate passed.
* 48 actual grader configuration probes passed; 13 actual HTTP recovery checks passed; 28 independent statistics checks passed; 27 final HTTP checks passed. These checks overlap some acceptance coverage; they are not added to the 129-test total.
* Missing environment and missing harness-result checks returned safe evaluation errors, not resolved results (`negative-operations.json`). Official task-repo Docker source-build failure behavior was not separately exercised; normal service build DNS failures are not substituted as proof of that case.

Final immutable build identities (tags are local staging tags):

| Artifact | Image ID | Architecture |
|---|---|---|
| `swe-p26-api:20261021` | `sha256:210c26097bb5c52d7736da4131454369d63fa9f196255396d67ca95c80b797bf` | linux/arm64 |
| `swe-p26-worker-offline:20261021` | `sha256:ddae5dbb0868838b626cb2c036d625624c0f5222c853582b0d603be72b1374e5` | linux/arm64 |
| `swe-p26-development-offline:20261021` | `sha256:9f07ef70148161525d25bb941ed7ed3aa69e8ac33f57cbde37e7aebcf3679225` | linux/arm64 |
| `swe-eval-swebench-tools:5.0.2-02e7a74` | `sha256:a7613db2bc745ddfe61d9319adf94252462b1db0e1e609bf6e8412d642de2dff` | linux/arm64 |

Normal service build paths are documented and earlier exercised, but final worker/test artifacts use the accepted-runtime offline path after actual Debian/registry network failures. Only the final IDs above are final acceptance artifacts. Earlier similarly named tags/logs are retained and are not substituted for these IDs.

## Real API, coding-agent and browser workflow

Final Playwright batch **`84348c6e694a4602aa2e12460cc63391`**, detail run **`c3c223edee9e41cc83577206ee9843ca`**. Two official instances (Sympy 20590 and Pytest 10051), two isolated deterministic profiles, one attempt each: **four durable attempts**. The path was real FastAPI -> SQLite queue -> leased worker -> mini-SWE-agent 2.4.6 -> Docker coding repository -> actual Git patch -> official evaluator/parser -> SQLite -> browser. No harness reports or HTTP responses were mocked.

The comment-only provider produced an actual harmless source diff; both official tests ran and reported unresolved. The empty provider produced upstream-skipped empty predictions; both remained completed attempts with zero valid test evaluations. This verifies infrastructure/handoff, not successful AI repair. Separate standalone run `1618b27236ee4a59abd6555c4bf6ee73` also persisted the comment patch and genuine official unresolved report.

Browser assertions cover unauthenticated login, protected catalogue/filtering, 390px responsive layout, batch creation/progress/final status, run metadata, safe logs, actual patch, model comparison, JSON/CSV exports and system health. Final browser result: **PASS**, `page_errors=[]`, `failed_requests=[]`, about 1.1 minutes. Actual screenshots and browser results are under `output/browser-final-artifact/`; historical unsafe-log browser test also passed (`browser-confidentiality.log`, `phase26-historical-confidentiality.png`).

Example screenshots: `phase26-dashboard.png`, `phase26-catalogue.png`, `phase26-batch-configuration.png`, `phase26-batch-progress.png`, `phase26-run-detail.png`, `phase26-run-logs.png`, `phase26-run-patch.png`, `phase26-comparison.png`, `phase26-health.png`, `phase26-task-mobile.png`, `phase26-unauthorized.png`, all from real state.

## Statistical reference validation

`independent-statistics.json` calculates expected values directly from persisted SQLite rows for corrected batch `c4cecbc259674c5f9bcea3363cf8fc34`; all **28** comparisons matched. The final browser batch was separately checked through HTTP and CSV with the same two-task/two-profile reference counts (`final-http-acceptance.json`).

| Profile | Attempts | Distinct versioned tasks | Valid evaluations | Resolved | Repair rate | Pass@1 | Unknown-cost attempts |
|---|---:|---:|---:|---:|---|---|---:|
| official-comment | 2 | 2 | 2 | 0 | 0/2 = 0 | 0/2 = 0 | 2 |
| official-empty | 2 | 2 | 0 | 0 | unknown (0 valid) | 0/2 = 0 | 2 |

Valid-evaluation repair rate uses resolved/valid completed authoritative evaluations. End-to-end attempt success rate uses resolved/all included attempts; both profiles are 0/2. Pass@1 uses the earliest independent attempt numbered one for each complete task/version/configuration identity; retry children/later attempts cannot inflate coverage. Empty predictions are failures to repair for attempt/Pass@1 denominators but have no executed valid tests. Profile/upstream/endpoint/reasoning/runtime/dataset/harness/agent/subset identities remain distinct. Match coverage uses actual task fingerprints within compatible cohorts.

For that SQLite reference batch, comment token sums were input 40, output 20, total 60; empty sums 20/10/30. Mean durations independently computed as 27.8908s and 2.4547s respectively; these timings describe that retained batch, not all hardware/models. Unknown costs remain null with two unknown attempts per profile; CSV unknown cells are empty. No zero-cost inference is claimed. Percentiles retain documented linear interpolation at (n-1)*p. Gold validation never appears as model-score runs, and synthetic/official/legacy data cannot influence local-v2 trusted latest success or existing shadow scores. Final export metadata identifies the actual official grading protocol, including its shared methodology label.

## Security and integrity evidence

Real API/log/detail/export checks and historical unsafe-row canaries passed. Actual browser-rendered logs and provider request traces contain no gold/test patch or private expectations. Anonymous protected APIs return 401; session/CSRF and credential-redaction regressions pass. No admin/model credential is compiled into new frontend assets. Embedding is denied by frame-ancestors CSP; ordinary API startup cannot create a dataset migration. Raw private artifacts remain intentionally available only to filesystem administrators, under the protected evidence/data root.

Coding containers get legitimate issue/repository/base context, no hidden records, credentials, Docker socket or production database. Actual grading containers have the restricted policy described in the architecture document; 48 probes observed it. Candidate code and imported setup/eval scripts never execute directly in FastAPI or the host Python process.

The original local-v2 independent controller and forgery defenses remain tested. **The official test-log report is a different trust boundary**: tests and candidate source coexist in a grading environment, and upstream status parsing is not an independent controller proof against every malicious candidate. Official groups explicitly advertise this limitation and never set trusted_evidence=true. This report does not claim official-protocol resistance to all grading-output forgery or a complete container-escape audit.

## Persistence, cancellation and operations

Thirteen live HTTP recovery assertions passed: API restart preserved snapshots, completed batch remained completed across deadline/repeated cancel, queued/active cancellation stayed consistent, SIGKILL occurred during actual official grading, normal lease expiry recovery retained exactly two attempts, interrupted work became failed while queued work completed once, batch failed rather than falsely completed, labelled containers were absent and heartbeat/lease recovered. Recovery batch: `18b5dcaaa456482f9dd917c010cf1808`.

Migration test uses a **copy** of accepted Phase2.5 data: four existing runs and 39 logs preserved with no trust upgrade; main schema 2, separate catalogue schema 1, repeated initialization/integrity checks passed. Frozen SQLite backups are `output/runs-final.sqlite3` and `catalogue-final.sqlite3`; do not copy live WAL main files as backups.

Current/recovered worker events are recorded without inventing reasons for historical service restarts. Existing Phase2.5 API/worker container IDs, image IDs and start times were compared before/after isolated testing. No shared/prod sub2api service was modified. Temporary audit containers are removed only after evidence backup; final `cleanup-and-preservation.json` records their removal and existing-service preservation.

## Reproduction commands

From `/Users/user/Program/swe-eval`, while the disposable deployment is intentionally running:

```bash
python3 data/phase26-swebench-20261021T135404Z/final_suite_runner.py
python3 data/phase26-swebench-20261021T135404Z/browser_final_runner.py
python3 data/phase26-swebench-20261021T135404Z/final_runtime_checks.py
python3 data/phase26-swebench-20261021T135404Z/recovery_acceptance_v2.py
```

These are bounded local audit reproducers, not production operations; the recovery script intentionally restarts/kills **only** the isolated API/worker. Final-suite flags/mounts are explicit in its source. Browser runner mounts the delivered Playwright spec and uses real isolated HTTP. Helper reruns generate new IDs/evidence and can change the disposable dataset/run state; preserve the frozen original evidence first.

Build/import/validation/staging/rollback commands are in `PHASE26_SWEBENCH_DEPLOYMENT_GUIDE.md`. For the audit-specific existing bind data, start only `docker compose --env-file /dev/null -f data/phase26-swebench-20261021T135404Z/compose.json up -d`. Its browser origin is `http://api:8000` inside the isolated network; it is not a ready host-browser login configuration. For a new host-accessible staging console use the delivered fresh Compose template and fresh credentials as documented. Do not repoint the existing shared console at this data/source without deployment authorization.

## Remaining blockers and deployment recommendation

1. **Full twenty-instance readiness BLOCKED:** retry four image preparations with reliable registry access; reproduce/fix three network-dependent gold environments through trusted preparation or specifically constrained infrastructure. Keep candidate network restrictions; rerun both gold and unmodified checks before readiness.
2. **Native x86_64/source builds NOT TESTED:** execute the documented staging path on a dedicated supported worker before broader deployment. No need to prepare all 500 environments.
3. **Trust/publication limits:** official log-parser evidence has the stated weaker adversarial boundary; private dataset/task licensing is not a commercial redistribution approval. No automatic/public ranking, full-score claim, live paid inference or external integration is accepted.

Recommendation: **Ready for isolated staging with the 13 validated instances only.** Keep seven unready tasks blocked at submission. No production rollout or source promotion is included. The existing local console remains Phase2.5. Sub2api/gpt-auto work was explicitly out of scope; prior blocked real-consumer integration statuses are not upgraded by these local tests.

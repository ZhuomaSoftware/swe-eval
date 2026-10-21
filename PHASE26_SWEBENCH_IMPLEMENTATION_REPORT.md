# Phase 2.6 SWE-bench implementation report

## Delivery and baseline

Implemented in **`data/phase26-swebench-20261021T135404Z/project/`**, starting from the accepted Phase 2.5 source. Shared HEAD is `ccf38665e142a93e62fb761908bd7bb248d7cb4c` plus its preserved pre-existing changes; HEAD alone does not identify this delivery. `baseline.json`, `final-source.json`, `PHASE26_IMPLEMENTATION.patch` and the final image manifest identify the actual code. The required Phase 2.5 reports were read and its promoted application matched the accepted source with zero differences. All 109 baseline installed tests passed before implementation. Existing Phase 1/1.5/2/2.5 reports, forensic files, shared source and services were preserved.

No source promotion, production database migration, production service restart, paid inference, routing/billing change, or new sub2api/gpt-auto integration was performed. Root-level Phase26 documents are convenience copies of the bundle documents.

## Implemented changes

| Area | Actual implementation |
|---|---|
| Dataset adapter | `src/swe_eval/benchmarks/official.py`: private catalogue, strict public task model, pinned immutable source records, atomic idempotent import, revision history, repository/instance/status filters, immutable subset membership and append-only validation evidence. TaskRegistry combines existing local and official tasks. |
| Import and operations | `official_harness.py`, `dataset_validation.py`, `cli.py`: official revision-pinned metadata import, filters/dry-run, preflight, explicit image preparation, sequential gold plus unmodified validation, resume/interruption evidence, structured status. |
| Official bridge | `swebench_bridge.py`, `swebench_upstream.json`: separate interpreter, exact upstream 5.0.2 module hashes, real run_instance/patch/eval/parser/report operations, restricted Docker transport and allowlisted result summary. |
| Evaluation engine | `official_engine.py`, `engine.py`, `agent.py`: dispatch by benchmark without changing local v2 grading; existing mini-agent/provider, real patch capture and source policy, official prediction/report persistence. |
| Candidate sandbox | `benchmarks/official_sandbox.py`, `sandbox.py`: hidden-free pinned image, pristine base commit, unprivileged coding process, clean source-only patch precheck, confirmed resource cleanup. |
| Existing API/batches | `api.py`, `service.py`, `center.py`: task filters, `/api/v1/datasets`, readiness gate, durable original queue/lifecycle, full versioned task/model/upstream snapshots. No arbitrary dataset/script HTTP import endpoint. |
| Persistence and diagnostics | `storage.py`, `diagnostics.py`: narrow official skipped-empty terminal representation, safe official summaries and historical filtering. Existing main schema remains 2; explicit private catalogue schema 1 is separate. |
| Analytics | `analytics.py`: distinct dataset/revision/subset/harness/agent/configuration/origin groups, official report eligibility, unknown costs, first-attempt semantics. Export methodology now identifies the actual group protocol; mixed protocols have no single protocol label. Local trusted-success and old shadow eligibility remain v2-only. |
| Console | `frontend/src/main.tsx`, `style.css`, `App.test.tsx`: dataset/instance/repository/readiness/subset controls, unready selection disabled, official result metadata and internal-subset warning, safe counts/costs. |
| Build/deployment | Official tools Dockerfile and dependency lock; isolated official-worker/development targets; documented accepted-runtime offline fallback; fresh staging Compose template. |
| Tests | Twenty permanent backend tests in `tests/test_official.py`, frontend assertions and opt-in `frontend/e2e/swebench.spec.ts`; original security regressions retained. |

## Dependency and provenance contract

Official harness **5.0.2**, Git `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`; inspected task definitions `3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`; dataset `SWE-bench/SWE-bench_Verified` at `78f471bf655a3137b2e8a75af1501690ec009ec3`. Installed CLI help confirms dataset check, eval --gold/-p/-i/--run-id/-j/--task-repo and report. The official virtualenv `/opt/swebench` passes pip check independently; mini-SWE-agent remains 2.4.6 in its accepted lean environment. The lean worker's documented optional dependency exclusions remain; raw global pip check is not claimed clean.

The adapter uses the actual upstream Python evaluator with a small **version-pinned callback shim**, because its default Docker privileges/resource policy do not meet this platform's execution boundary. Upgrades must re-audit the shim and hashes. No large upstream harness copy was introduced. Official registry images are pinned by observed digest after explicit preparation. Changed digest after validation fails closed.

Every attempt retains run/instance IDs, dataset revision, repository/base commit, subset, actual patch SHA-256, model/profile/upstream/endpoint and reasoning identity, official harness run ID/version/commit, adapter/runtime/configuration hashes, mini-agent version, environment digest and report hash. A nonce plus full attempt/patch/configuration identity prevents stale harness cache reuse.

## Real implementation failures found and corrected

The original failure artifacts are retained, rather than rewritten as successes.

| Before observation | Root cause and change | After evidence |
|---|---|---|
| Official image archive/root filesystem setup failed | Avoided host extraction; bounded safe archive transfer into isolated tmpfs. Read-only root kept, writable execution areas explicit. | Stage A real gold and negative; restricted container probes |
| Initial agent patch rejected generated packaging files | Official image setup left generated egg-info in the repository. Coding setup now resets, cleans and verifies pristine base_commit before the agent. | `agent-initial-patch-rejected.json` versus `agent-smoke-final.json`; permanent pristine-repository test |
| Empty agent prediction could not complete under local-v2 terminal rules | Upstream skips empty predictions. Added narrowly validated official skipped-empty representation, without relaxing local controller assertions. | Initial browser failure retained; final actual empty attempts completed with test_result=not_run and zero valid evaluations |
| Successful test execution misclassified from an earlier pip network warning | Classifier previously scanned all setup output. It now uses actual test-output markers and execution evidence. | Original logs preserved; runtime subset rechecks and dedicated regression |
| Concurrent cleanup reported failure after another process had already removed the container | Failed remove alone was ambiguous. A new successful labelled Docker query must prove absence; daemon failure/present container still fails. | `worker-cleanup-race.log`; final real cancellation/recovery; permanent race test |
| Offline image retained stale old static files | Copying over the old package did not delete removed assets. Offline build now removes the old package before copying the complete new API package. | `offline-stale-assets-before.json` and final installed-source equality |
| Common export methodology still named local-v2 for official groups | Inherited global metadata label did not reflect the actual group. Export now derives protocol(s) from included groups. | Permanent official-report assertion and final rebuilt installed suite/HTTP export |

A final evidence-helper CSP assertion also initially used a case-sensitive header lookup. The application supplied CSP; the helper was corrected to compare headers case-insensitively. Its initial failure log is preserved separately. Registry/Debian DNS/EOF failures were external; they were not bypassed or reported as passing builds.

## Security boundary

Private gold/test patches, expected test IDs, source scripts and full imported records are absent from ordinary task/run JSON, agent requests, API logs, browser state and comparison exports. Server-owned private catalogue/evaluation artifacts and backups use a 0700 parent and restricted files; raw reports are never static assets. Both persistence and response summary boundaries allowlist safe fields, including old unsafe records.

Only trusted orchestration receives daemon access. Actual grading container checks observed network none, read-only root, no host binds, no API keys/socket, ALL capabilities dropped, no-new-privileges, 1 CPU, 2 GiB memory/no extra swap and 256 PIDs. Coding runs at UID10001; grading remains root for official compatibility within the restricted container. Repository/output/tmpfs limits and outer timeouts bound execution. Image preparation is explicit and distinct from candidate execution.

**Official trust limitation:** private tests execute in the grading environment containing candidate source, and upstream reports depend on its test-log parser. This is not the malicious-candidate forgery guarantee of the independent local v2 controller. Official results are `swebench-official-v5`, `evidence_authority=official_test_log_report`, `trusted_evidence=false`; they cannot become local-v2 trusted/shadow successes. Do not advertise stronger adversarial assurance. This phase does not prove Docker escape resistance or every malicious upstream dependency case.

## Verification and remaining work

Final installed artifacts: **129/129 tests passed in 109.004 seconds, zero failures/errors/skips**. Frontend: **9/9**, TypeScript/Vite build pass. Real browser and HTTP acceptance, four-attempt actual agent/harness batches, 13 recovery checks, 28 independent arithmetic checks, 27 final HTTP checks, historical log confidentiality and 48 container isolation observations passed. See the acceptance report for exact IDs, counts and limitations.

Imported 500 metadata records; selected 20 across four repositories; prepared 16 images; **13 gold-resolved plus 13 genuine unmodified-negative results; 13 ready, seven blocked**. Full per-instance identity, timestamps, gold/negative results and evidence paths are in the dataset manifest. Gold checks are not model runs; local stubs are infrastructure tests.

Remaining priorities: finish four image preparations on a reliable registry/network; resolve three task environments requiring network during evaluation without broadly enabling candidate network; then rerun gold and negative for all seven. Validate native x86_64 staging and source-based task-image builds separately. No full 500-environment preparation, live paid scoring, publication or external integration is claimed.

Build, start, import, validate, backup and rollback commands are in `PHASE26_SWEBENCH_DEPLOYMENT_GUIDE.md`. Exact audit reproducers are listed in the acceptance report. The tested delivery remains an isolated bundle; promoting it or restarting the shared console is a separate deployment action.

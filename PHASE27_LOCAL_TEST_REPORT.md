# Phase 2.7 local end-to-end test report

**PASS for the requested isolated local deployment and the retained 13 READY task scope.** All 17 local gates pass. Seven original environments remain BLOCKED; no 20/20, paid-model quality or production acceptance is claimed. Generated 2026-10-22T03:30:33.089347+00:00; source HEAD `6bcf4340fc5e47901bdb1bc41852cf6908d567b8`, accepted tag `phase27-main-verified-20261021T183759Z`. Evidence `data/phase27-local-20261022T023632Z/`.

## Final local acceptance matrix

| Gate | Criterion | Status | Actual evidence/method |
|---|---|---|---|
| 01 | WebUI accessible from native macOS Chrome | PASS | Native Chrome 155.0.8059.85 directly opened localhost; login and 12 sections |
| 02 | API and worker operational | PASS | Three services running; active lease, actual executions and Docker cleanup |
| 03 | Linux named-volume SQLite | PASS | docker inspect: API/worker share swe-p27-local_management-data at /data; no host DB bind |
| 04 | Explicit migration and database integrity | PASS | init-db schema 2 → migrate-admin schema 3; WAL, FK enforcement/integrity and idempotency |
| 05 | Provider creation and encrypted credentials | PASS | Real UI creation; AES-GCM ciphertext, actual GET /models, rotation and revocation |
| 06 | Dynamic configuration without restart | PASS | Model v1 used, then v2 used before any service restart |
| 07 | Historical configuration immutability | PASS | First two model/provider revisions 1/1; later model v2 and provider v2; four original SQLite rows unchanged after crash |
| 08 | Official catalogue accessible | PASS | 500 metadata, immutable revision/source hashes and all 13 READY image digests checked |
| 09 | Custom subsets persist | PASS | GUI two-task subset, reopen, duplicate/revise/archive; original 20 subset saved with 13/7 readiness |
| 10 | Real agent to official harness | PASS | Five completed actual Docker/mini-agent/official-harness attempts; one deliberate interruption |
| 11 | Official gold and negative results | PASS | Administrative job 2647904829a74efa91e626ba7c53c6d4: resolved / unresolved, real official reports |
| 12 | Persisted results visible in UI | PASS | Actual details, logs, patch, comparison and CSV/JSON screenshots/exports |
| 13 | Restart and recreation persistence | PASS | Force recreation during GUI workflow; later explicit restart; online backup restored into a separate volume |
| 14 | Worker crash recovery and cleanup | PASS | Real SIGKILL 137, natural lease expiry, worker_interrupted; queued attempt completed; no duplicates/orphans |
| 15 | Critical security regressions | PASS | Original F-01, confidentiality, SSRF, CSRF, lease/finality, legacy/protocol isolation and CSV regressions |
| 16 | Full automated suites | PASS | 157 backend / zero skips; 20 frontend; TypeScript/Vite; pinned JS Playwright and additional native browser |
| 17 | No unexplained critical runtime errors | PASS | No SIGBUS/135, OOM, DB locked or WAL failure observed; intentional SIGKILL and favicon warning explicitly classified |

## Automated tests and builds

| Check | Status | Exact command / outcome |
|---|---|---|
| Final installed backend suite | PASS | `python3 data/phase27-local-20261022T023632Z/run_installed_tests.py`; exit 0; **157 tests, 0 failures/errors/skips**, 108.459s; real Docker and official runtime flags enabled |
| Frontend tests/typecheck/build | PASS | `python3 data/phase27-local-20261022T023632Z/run_frontend.py`; exit 0; **20 tests**; `npm test -- --run` and `npm run build` (`tsc --noEmit && vite build`) |
| API/official-worker/official-development builds | PASS | `python3 data/phase27-local-20261022T023632Z/build_final_images.py`; each exit 0 |
| Project sandbox/grader builds | PASS | Existing Dockerfiles, fresh project tags and SANDBOX_IMAGE build argument; both exit 0 |
| Container Chromium operator test | PASS | `python3 data/phase27-local-20261022T023632Z/run_browser.py`; JS Playwright 1.64.1, one full actual operator scenario, 3 minutes, 141 ordinary-response scans, no unexpected console/page/network errors |
| Native macOS Chrome | PASS with cosmetic warning | `/tmp/swe-p27-local-host-browser/bin/python data/phase27-local-20261022T023632Z/host_browser.py`; Python Playwright 1.64.0, Chrome 155.0.8059.85, all 12 sections, refresh/login, light/dark/mobile; favicon 404 retained |
| Independent API/SQLite/statistics | PASS | 60 checks in acceptance-checks.json |
| Additional management HTTP | PASS | 14 checks in supplemental-http.json |
| Actual crash/recovery | PASS | 11 final assertions plus recorded SIGKILL/expired-health/candidate observations |
| Backup/restore/restart/security | PASS | 10 checks in backup-persistence.json |
| Final secret/artifact/storage/preservation audit | PASS | 59 checks in final-checks.json |
| Local benchmark correct/incorrect patches | PASS | Separate temporary DB; `verify-fixture --case both`; actual trusted grader, true/false as expected |

The first complete backend run also passed 157/157 in 114.751s. The final rerun specifically uses the new deployment sandbox/grader tags, rather than the historical accepted test tags. No integration test was skipped; Docker and SWE-bench integration environments were enabled. Logs retain exact unittest test names including `test_original_f01_exploit`.

## Browser and real operator workflow

Both actual macOS host HTTP checks and native headless Chrome directly reached http://127.0.0.1:18327. Native Chrome used an independent temporary profile, not the user's browser profile. The container Playwright scenario preserved the same localhost URL/Host/Origin through a transparent TCP relay to Docker Desktop host's published port; it did not mock any HTTP response. All 12 implemented Chinese navigation sections loaded. Screenshots are real interface state: `output/browser/` and `output/host-browser/` (authentication, providers/models, dataset/tasks, subset, batch review/progress, run details/log/patch, comparison, validation, health, audit, light/dark/mobile).

GUI provider/model creation and non-inference GET model-list worked. New configurations were available without restart; model revision 2 executed before the first recreation. The same public model alias under another provider stayed distinct. Genuine wrong-key errors were retained safely; rotation, revocation, disable/archive and history checks used actual HTTP. New submissions under the disabled provider returned 422; historical results remained accessible. The provider was later re-enabled for a usable final stack. Six permanent provider-key/configuration/run bindings remain unchanged by later edits. No plaintext credential was returned.

Saved two-task subset `browser-quick-2` persisted across refresh/recreation/restart. Duplicate/revision/archive tests preserved historical membership. The unchanged original twenty-member subset remains explicitly 13 READY / 7 ineligible. A blocked-task run was rejected with 422 before creating work. A metadata-service SSRF provider URL was rejected with 422.

## Actual agent/harness execution

Initial GUI batch **`15352f49fa244ba980817b88b19acd90`** selected SymPy 20590 and Pytest 10051. The worker made real authenticated stub requests, mini-SWE-agent 2.4.6 ran actual commands inside the restricted Docker coding environment, generated nonempty patches, and handed them to official SWE-bench 5.0.2. Five completed attempts across the full workflow have actual patch/report SHA-256 values independently checked against their stored bytes. Eleven actual inference requests comprise ten across the five completed attempts plus one interrupted call. No paid endpoint was used.

| Run | Official instance | State | Model/provider/credential revision | Outcome |
|---|---|---|---|---|
| `605458d06c7d4caf9771148100e1c9e8` | sympy__sympy-20590 | completed | 1/1/1 | official unresolved |
| `d9d0f83de35e4730a5838ae5f112fef5` | pytest-dev__pytest-10051 | completed | 1/1/1 | official unresolved |
| `575c7d0866e3410797598191bb400df5` | pytest-dev__pytest-10051 | completed | 2/1/1 | official unresolved |
| `3f2e8340323c4489a5bbb2baa8ae1fd6` | pytest-dev__pytest-10051 | completed | 2/2/2 | official unresolved |
| `c3a7736f303f40c38967fd89f458db91` | sympy__sympy-20590 | failed | 1/4/2 | worker_interrupted |
| `3d464c0b27a242da8ebbee673ab65274` | sympy__sympy-20590 | completed | 2/4/2 | official unresolved |

Comment-only patches were genuinely **unresolved**. This is valid infrastructure acceptance, not evidence of model intelligence or repair capability. Official output keeps `swebench-official-v5` and `trusted_evidence=false` relative to local-v2 trust. Gold validation is an administrative dataset check, excluded from model scores. Unknown costs are never converted to zero; synthetic configured prices in this test are accounting inputs, not charges.

Actual administrative validation job **`2647904829a74efa91e626ba7c53c6d4`** ran the pinned official gold patch and unmodified-source negative for `sympy__sympy-20590`, yielding **resolved / unresolved**, digest `sha256:3a282752833ce34730ee0621e22033501c993f45742775ca57f04c9ff27178a0`. It was not merely patch application. Separate final installed tests also genuinely executed gold/negative/invalid/timeout official evaluations. Private reports are retained in the restricted archive; ordinary responses contain only safe counts/classifications/hashes.

## Independent statistics

Reference batch: two distinct versioned tasks, one complete experimental configuration, one first attempt each; both valid official reports unresolved. Valid repair rate = 0/2; end-to-end attempt success = 0/2; Pass@1 = 0/2 task/configuration pairs. Four stub requests declare 40 input and 20 output tokens total. Synthetic USD 1/M input and 2/M output produce 0.00008 USD total and 0.00004 average. Cost/resolved is unknown because zero repairs resolved.

| Metric | Independently expected | Actual HTTP API |
|---|---|---|
| attempts | 2 | 2 |
| valid_evaluations | 2 | 2 |
| resolved | 0 | 0 |
| pass_at_1_tasks | 2 | 2 |
| pass_at_1 | 0.0 | 0.0 |
| resolved_rate | 0.0 | 0.0 |
| attempt_success_rate | 0.0 | 0.0 |
| model_requests | 4 | 4 |
| input_tokens | 40 | 40 |
| output_tokens | 20 | 20 |
| total_tokens | 60 | 60 |
| total_cost | 8e-05 | 8e-05 |
| average_task_cost | 4e-05 | 4e-05 |
| average_seconds | 28.866 | 28.866 |
| p50_seconds | 28.866 | 28.866 |
| p95_seconds | 29.80965 | 29.80965 |
| currency | USD | USD |

For sorted durations a,b: P50=(a+b)/2 and P95=a+0.95(b−a). CSV bytes were parsed with Python csv.DictReader. Configuration/subset identities, dataset version, harness version, currency and diagnostic origins remain separate. Rotation legitimately introduced a third cohort after the earlier two model revisions; the independent runner expectation was updated to three rather than merging configurations. The final recovery run adds its separate provider/subset cohort; no capability leaderboard promotion occurred. Local-v2 trusted dashboard results remain zero because these runs are local_stub official diagnostics.

## Persistence, recovery and security

API/worker were force-recreated with unchanged named volume during the browser scenario, then explicitly restarted again after recovery. Sessions, providers/models, version histories, subsets, batch states and records persisted; new genuine official execution completed after recreation. Encrypted credentials remained usable with the original external key. Online backup and an actual restore into `swe-p27-local_restore-check` passed; missing/wrong master material failed closed.

Recovery batch **`15bb091412a745ab89567098faa564dd`** had one active `sleep 120` candidate and one durably queued run. Only the new worker was SIGKILLed: exit 137, not OOM or SIGBUS. Restart policy was temporarily disabled for that controlled test; the actual 90-second lease expired naturally without SQL timestamp manipulation. API/database remained ready while worker health became expired/not ready. The replacement worker marked `c3a7736f303f40c38967fd89f458db91` failed/worker_interrupted with resolved=null, cleaned the orphan container and completed queued `3d464c0b27a242da8ebbee673ab65274` exactly once. Six total records and two recovery attempts remained; four prior run rows were byte-for-byte unchanged against the pre-crash online backup. Partial experiment counts expose one failed and one completed attempt; terminal batch state does not imply all attempts repaired. Completed original batch cancellation was an idempotent no-op. Final restart policy is restored and automatic restart counts are zero.

Candidate inspection verified no network, no host bind/socket/credentials, read-only root, dropped capabilities, 2 GiB memory, one CPU and PID limit 256. Official grading isolation/provenance stayed separate from local grading-v2. Original Phase 1.5 forgery/controller-output/isolation tests, Phase 2.5 hidden-log filtering/finality/freshness/Pass@1/CSV tests, lease/stale-write/recovery tests and Phase 2.7 credential/AAD/URL/CSRF/configuration tests all passed in the final installed suite. Actual HTTP checked missing authorization, missing/cross-origin CSRF, logout, private-path denial and credential redaction. Both dummy keys plus actual admin/master/password canaries were absent from ordinary responses/assets/exports/logs and plaintext DB dumps. The stored external secret files and restricted private artifacts are intentionally outside ordinary/public surfaces.

## Observed failures and retained limits

- **Resolved deployment defect:** unquoted tmpfs flow-list mount options caused Docker to reject the staging template. Only quoting was corrected; actual subsequent startup/mount inspection passed.
- **Resolved image selection defect:** old default grader contents differ from accepted source. New project-specific builds/manifests avoid it without changing existing image tags/services.
- **Known cosmetic P2:** native Chrome automatically requests `/favicon.ico`, which returns 404 and creates one console warning. Its exact console location is recorded; no page exception, failed application request or application/API asset failure occurred. It was not hidden or counted as a zero-error browser run.
- **Test-runner corrections, not product fixes:** recovery runner first used the wrong attempt/log field names; its resumed historical count included its own two already-submitted jobs. The same durable batch was resumed without duplicates; final checks compare the genuine four-row pre-test backup. Raw failed runner logs are retained. Terminal cancel's documented 202 was corrected in the test driver. Python Playwright 1.64.1 was unavailable on the package index, so the additional native-only driver used 1.64.0; the full container workflow retained pinned JavaScript 1.64.1. Official CLI has no --version flag; version was verified through `swebench.__version__`. Native CUA transport was inactive; real host Chrome verification succeeded through the explicit Playwright fallback.
- **BLOCKED:** seven unchanged environment-ineligible official instances. Metadata/image presence alone did not promote them; their list/digests/evidence are in readiness-final.json.
- **NOT TESTED:** native Linux x86_64, paid model inference, full twenty-task revalidation, long production soak, external sub2api/gpt-auto. None is represented as a local success.

The tested local stack is available and usable. The remaining cosmetic warning does not compromise the seventeen local acceptance gates. Production rollout and 20/20 subset readiness remain outside this PASS.

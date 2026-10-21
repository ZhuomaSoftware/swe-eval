# Phase 2.7 acceptance report

## Decision and tested scope

**CONDITIONALLY ACCEPTED — standalone administration on native Linux Docker volume storage. Ready for isolated staging only.**

All **15 standalone gates PASS**, with no unresolved critical scoring/security defect observed in that qualified deployment. This is not an acceptance of macOS host-bind SQLite storage, all 20 official task environments, live paid model quality, or external sub2api/gpt-auto integration.

Tested baseline: Phase 2.6 main commit `618ff61795c2c672e5976375b17a376d1837630b`; final Phase 2.7 source tag `phase27-main-verified-20261021T183759Z`. Exact source hashes, local checkpoint commit and final image IDs are in the timestamped evidence. Evidence: `data/phase27-dynamic-20261021T172902Z/`. Report generated 2026-10-21T18:46:47.643478+00:00.

Environment: macOS ARM64 host, Linux ARM64 Docker worker; accepted official amd64 images run through existing verified emulation. FastAPI, SQLite schema 3, React/TypeScript, mini-SWE-agent 2.4.6, official SWE-bench 5.0.2. Final SQLite and WAL reside on `swe-main-p27-acceptance_native-data`, not a host directory bind. No native x86_64 result is claimed.

Final verification: **157 backend tests PASS, zero errors/failures/skips; 20 frontend tests PASS; TypeScript/Vite PASS; three Docker target builds PASS; two real Chromium tests PASS; 60 independent runtime checks PASS; 14 additional real HTTP management checks PASS.** The full browser run captured zero unexpected page errors, console errors or failed requests. Expected unauthenticated 401 responses and the intentional restart interval were tracked separately.

## Acceptance matrix

| ID | Criterion | Status | Evidence/method |
|---|---|---|---|
| P27-01 | Phase 2.6 promotion gate | PASS | Promotion report, accepted tag, MAIN 129/9 tests and genuine official browser batch |
| P27-02 | Provider management and encrypted credentials | PASS | Real Chromium creation/connection; actual HTTP rotation/revocation/archive/error persistence; AES/AAD/tamper regressions |
| P27-03 | Outbound safety and non-inference testing | PASS | All-DNS-answer/metadata/redirect/proxy tests; real HTTP/1.0 deadline; actual local authenticated GET model-list |
| P27-04 | Dynamic models, identities and history | PASS | GUI creation/edit; duplicate alias under another provider; HTTP archive/history; immutable revisions |
| P27-05 | No-restart configuration and queued binding | PASS | New provider/model used without restart; old runs stay revision 1, new runs revision 2; SQLite credential rotation/binding tests |
| P27-06 | Dataset management and metadata synchronization | PASS | 500-record real pinned sync through HTTP/queue/worker; zero image preparation; actual archive/restore admission checks |
| P27-07 | Safe task catalogue and readiness | PASS | 500 metadata, original 20 selection; 13 READY; real filtering/search/mobile UI; private grading fields excluded |
| P27-08 | Versioned custom subsets | PASS | GUI save/reopen; actual duplicate/revise/archive; immutable historical membership and batch coverage fingerprint |
| P27-09 | Bounded durable administrative jobs | PASS | Real gold/negative validation, running cancellation, actual 1-second wall timeout; lease/recovery/stale-write tests |
| P27-10 | Reviewed batch workflow and lifecycle | PASS | Actual two-task batch via four-step UI; bounded reservations; historical replay compatibility; existing finality/limits regressions |
| P27-11 | Analytics, currency and exports | PASS | Independent two-task reference calculations; real CSV parser; unknown/mixed-currency handling; diagnostic isolation |
| P27-12 | Authentication, secrecy and integrity | PASS | 60 runtime checks, 132 captured response scans, exact Phase 1.5/2.5/2.6 security regressions |
| P27-13 | Final builds and automated suites | PASS | 157 installed backend tests; 20 frontend tests; TypeScript/Vite; all three Docker targets and package equality |
| P27-14 | Persistence, recovery and Linux-volume operations | PASS | Actual post-restart fourth evaluation; stored configurations/results/subsets; live worker after browser; no orphan candidate containers |
| P27-15 | Documentation, provenance and preservation | PASS | Four Phase 2.7 reports, explicit migration/rollback guide, source/image hashes, restricted backups, unchanged existing services/user changes |

## Explicit exclusions and failures

| Boundary | Status | Observation / limitation |
|---|---|---|
| macOS host-bind SQLite deployment | FAIL | Two observed worker SIGBUS exits; one trace at SQLite commit. This deployment mode is excluded, not represented as repaired. Native-volume mitigation passed the complete workflow and actual post-restart execution. Exact underlying filesystem/runtime cause is not established. |
| Full curated 20 executable | BLOCKED | 13 READY, seven ineligible. No failed instance was replaced or promoted from metadata/image availability alone. |
| Live paid inference / model capability claims | NOT TESTED | Not authorized; deterministic local provider used. No official full-benchmark score or real model capability score is claimed. |
| sub2api / gpt-auto | NOT TESTED | Explicitly out of Phase 2.7 scope; no external integration or production routing change performed. |

The original catalogue stores six literal `blocked` statuses and one `interrupted` status among the seven ineligible instances. Their individual statuses remain unchanged. “Seven BLOCKED for execution” is the eligibility aggregate, not a rewrite of historical validation records.

## Actual operator workflow

Chromium authenticated, created `browser-stub` with an encrypted test credential, performed a non-inference connection test, created `browser-dynamic`, browsed 500 official records and the original subset, saved/reopened `browser-quick-2`, and submitted the reviewed two-task experiment. The existing worker called the exact-credential-checking local provider, executed mini-SWE-agent in real restricted Docker environments, captured real patches, invoked the pinned official harness and persisted reports.

- Batch: `2860ffddd95e46d4b8fa2f36a6093aca` — two actual attempts, terminal completed, both unresolved as expected for a comment-only patch.
- Runs: `db54c6b7afac49129086a2a49db583f1`, `e4fb02dba5ea4a838f19c7697ce526b9`, `06b71d8f888f49d4b62079342af4e211`, `d3659f7716644cdbb3330dde26e69bdd`.
- The first two runs retain model/provider revision 1. The third uses model revision 2 without restarting services. After the intentional API/worker restart, the fourth genuine evaluation also completed using revision 2. Historical configurations remained unchanged.
- Validation job `5c2658f0d81540c09bae97e53f29d6e2` actually produced gold **resolved** and original-code **unresolved** for `sympy__sympy-20590`. Its private official reports/hashes are retained.
- A running validation job was cancelled and repeated cancellation remained terminal. Supplemental HTTP testing genuinely reached an administrative wall timeout and cleaned up its child/container resources.
- Provider disable rejected new submissions; exact replay of the completed original experiment still returned the original batch and did not create attempts.
- Additional provider/model/subset archive/revision and dataset archive/restore operations were actually exercised through HTTP. Secondary provider rotation/revocation was verified against the real local HTTP stub; wrong-key errors were safely retained.
- Metadata job `7dda322287724d49826570f0435442ca` actually synchronized the pinned official source: 500 records, zero inserted, zero images prepared. Prior readiness remained intact.

These are deterministic-provider infrastructure checks. Gold validation is dataset integrity evidence. Neither is a real model ranking.

## Independent statistical validation

The controlled reference batch has two distinct versioned tasks, one configuration, one attempt each. Both genuine official reports are unresolved. Thus valid repair success = 0/2, end-to-end attempt success = 0/2, and Pass@1 = 0/2 task/configuration pairs. Each attempt made two stub requests; each response declared 10 input and 5 output tokens. Synthetic configured pricing was USD 1/M input and 2/M output. Total cost = (40×1 + 20×2)/1e6 = 0.00008 USD; average 0.00004. No money was paid. Cost per resolved task is unknown because no task resolved.

Durations were read from persisted records and recalculated independently. For sorted durations a,b, P50=(a+b)/2 and P95=a+0.95(b−a), matching the documented linear interpolation rule. Infrastructure failures never count as repairs; non-live official groups remain diagnostic and local-v2 trusted dashboard success remains zero.

| Metric | Independent expected | Actual API |
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
| average_seconds | 26.631 | 26.631 |
| p50_seconds | 26.631 | 26.631 |
| p95_seconds | 28.06245 | 28.06245 |
| currency | USD | USD |

Unknown pricing/usage remains unknown in permanent regressions. Mixed currencies are reported separately, not added. Known tiny values retain precision in detail/history; actual CSV bytes were parsed using Python's standards-compliant CSV parser and include currency metadata. Formula-prefix protection remains enforced.

## Dataset readiness and provenance

Dataset `SWE-bench/SWE-bench_Verified`, revision `78f471bf655a3137b2e8a75af1501690ec009ec3`; 500 imported records, original 20 selected instances, 16 recorded prepared image digests, **13 READY / 7 not eligible**. Fresh Phase 2.7 gold/negative validation covers one official instance; real agent attempts cover two official instances. Remaining READY eligibility is preserved accepted Phase 2.6 evidence, not a claim that all 13 were regraded anew in this phase. No Phase 2.6.1 experimental source was promoted.

| Ineligible instance | Retained catalogue status | Execution eligibility |
|---|---|---|
| psf__requests-1724 | blocked | BLOCKED for execution |
| psf__requests-1766 | blocked | BLOCKED for execution |
| psf__requests-1921 | blocked | BLOCKED for execution |
| psf__requests-2317 | interrupted | BLOCKED for execution |
| pytest-dev__pytest-10081 | blocked | BLOCKED for execution |
| pytest-dev__pytest-10356 | blocked | BLOCKED for execution |
| sphinx-doc__sphinx-10435 | blocked | BLOCKED for execution |

Per-instance source hashes, environment digests, validation timestamps and all 20 identities are in `output/readiness-matrix.json`. The original curated selection is unchanged. Existing Docker cache availability does not upgrade eligibility.

## Security, migration and operational evidence

The installed suite re-executed the original F-01 exploit and trusted-controller forgery attacks; correct/incorrect local patches, hidden assertion confidentiality, isolation, stale worker writes, recovery, terminal immutability, CSV safety, legacy exclusion, freshness and official protocol isolation passed. No regression was weakened.

Runtime response scans covered ordinary run details/logs/patches, provider/model histories, datasets/tasks, subsets, audit/jobs and exports. The encrypted credential canaries and actual master/admin credentials were absent from ordinary responses, built browser assets and SQLite plaintext snapshots. Real missing-auth requests returned 401, missing CSRF returned 403 and logout invalidated the session. The local stub verified the exact credential; it never logged header contents. No paid model call occurred.

Migration testing used the retained online backup of the accepted six-run database: schema 2→3 preserved six runs/71 logs byte-for-byte, passed integrity/foreign-key checks and repeated idempotently. A permanent injected-failure test verified rollback. Active existing databases were not migrated.

Observed bind-mode incident: exit 135, `OOMKilled=false`; `Fatal Python error: Bus error` at `storage.py:59` in commit during heartbeat. A separate interrupted run became failed with `worker_interrupted`; completed results were preserved. Historical restart causes are not inferred. Native-volume runs passed, including post-restart work and live-process checks. Fault diagnostics, old bind databases and native snapshots were retained; no WAL/durability/security mechanism was disabled.

Final image/package equality verified 50 package files and all 47 main source/data files. Image identities:

| Image | Identity |
|---|---|
| swe-main-p27-api:20261021 | `sha256:6f64127590f5822a32ef45f2a0f6913fff065b970058ac1cb44916acff20cb02` |
| swe-main-p27-worker:20261021 | `sha256:e4188ae727cb723a63305059c3d710bfa10a82294b92707aa40a7d826ff33330` |
| swe-main-p27-development:20261021 | `sha256:3ca31642edb7ed95350746bd14244c32d2c9a24ad05edd03362ce0b41c7c9eeb` |
| swe-eval-swebench-tools:5.0.2-02e7a74 | `sha256:a7613db2bc745ddfe61d9319adf94252462b1db0e1e609bf6e8412d642de2dff` |

## Evidence and reproduction

- `output/final-installed-regression-suite.log`, `frontend-final.log`, `build-*.log`, `build-results.json`.
- `output/browser/`: full workflow log, actual batch/run JSON, official validation summary, CSV/JSON exports and screenshots.
- `output/browser-readonly/`: real overview in both themes and persisted run-history screenshots, after CSS transitions settle.
- `output/acceptance-checks.json`, `supplemental-http.json`, `metadata-sync-result.json`, `migration-copy.json`, `readiness-matrix.json`.
- `output/worker-post-browser.json`, `runtime-observation-final.json`, `native-final-service.log`, `final-installed-source-equality.json`, `final-image-identities.json`.
- `worker-incident*`, `final-worker-diagnostic.log`, archived browser attempts and former bind state preserve failures.
- Restricted `native-private-evidence.tar`: online SQLite backups plus authoritative official reports/private grading artifacts. It is not served by the application. Master material stays outside this archive.

Exact build/test runners and bootstrap/rollback commands are in the implementation/deployment reports. The final isolated deployment uses its own volume, network and port 18372. Its browser origin is the internal test origin; the committed standalone staging template uses local port 18327 and the correct public-origin configuration. Existing port-8000 services were not replaced.

## Remaining blockers and deployment recommendation

1. **Production gate:** use native Linux storage and perform an authorized staging soak before rollout. macOS bind-mounted SQLite remains excluded; its underlying SIGBUS cause is unresolved.
2. **Benchmark scope:** validate the seven retained ineligible original instances on suitable infrastructure before claiming 20/20 readiness. No native x86_64/full-subset validation was performed here.
3. **External scope:** paid inference quality and sub2api/gpt-auto integrations were intentionally not executed or implemented.

**Ready for isolated staging only.** Main source promotion and dynamic standalone administration are complete and verified. No production deployment, production migration, sub2api restart, routing/billing change or remote Git push was performed.

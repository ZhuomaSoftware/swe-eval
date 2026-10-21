# Phase 2.6 main-repository promotion report

**Decision: PROMOTED.** The accepted Phase2.6 source is present and independently regression-tested in `/Users/user/Program/swe-eval`. Stage B may begin after the source checkpoint below is recorded. This is source promotion, not a production/service deployment. Existing port-8000 Phase2.5 services remain unchanged.

## Baseline and safety

Original main HEAD `ccf38665e142a93e62fb761908bd7bb248d7cb4c`, with the preserved dirty tree. Accepted source: `data/phase26-swebench-20261021T135404Z/project/`. All 97 accepted source hashes and 87 main baseline hashes matched. The five required reports were inspected. Unrelated existing changes were backed up and remain untouched.

Evidence: `data/phase26-promotion-20261021T171252Z/`. Private project/configuration backups, original index/HEAD and diff files are under `before/` (0700 protected parent; sensitive files 0600). The live database was backed up with SQLite's online backup API into a serialized independent database, not copied without its WAL. Backup integrity_check passed; six completed runs, no queued or active work. Main runs schema stayed 2.

The API and worker use immutable images. Their only source-directory binds are server-owned model/task configuration; no application source mount or auto-reload exists. No service stop/restart was required. IDs/images/start times and original configurations were recorded. After promotion, the existing two containers were still running with identical IDs/images/start times, and all six run rows, 71 log rows and evaluation snapshots were unchanged. No sub2api, routing, billing, model key or active database was modified.

## Exact changes and merge resolution

15 existing files updated, 14 new files added, all from the SHA-verified accepted implementation. No whole-directory overwrite, Git reset, audit database promotion or environment-file replacement occurred. Main source matches all 97 accepted manifest entries. There were no source conflicts.

The delivered historical `PHASE26_IMPLEMENTATION.patch` failed a dry check because adjacent hunks lacked end-of-file newline markers. It was preserved unchanged. `promotion-verified.patch` was regenerated from verified before/after bytes, passed `git apply --check`, then applied after rechecking each target's precondition hash. Final files match the accepted hashes exactly.

- `pyproject.toml`
- `docker/service.Dockerfile`
- `frontend/src/App.test.tsx`
- `frontend/src/main.tsx`
- `frontend/src/style.css`
- `src/swe_eval/agent.py`
- `src/swe_eval/analytics.py`
- `src/swe_eval/api.py`
- `src/swe_eval/center.py`
- `src/swe_eval/cli.py`
- `src/swe_eval/diagnostics.py`
- `src/swe_eval/engine.py`
- `src/swe_eval/sandbox.py`
- `src/swe_eval/service.py`
- `src/swe_eval/storage.py`
- `compose.swebench.yaml`
- `requirements-swebench.lock`
- `config/swebench-curated-20-v1.json`
- `docker/swebench.Dockerfile`
- `docker/worker-from-accepted.Dockerfile`
- `frontend/e2e/swebench.spec.ts`
- `src/swe_eval/dataset_validation.py`
- `src/swe_eval/official_engine.py`
- `src/swe_eval/official_harness.py`
- `src/swe_eval/swebench_bridge.py`
- `src/swe_eval/swebench_upstream.json`
- `src/swe_eval/benchmarks/official.py`
- `src/swe_eval/benchmarks/official_sandbox.py`
- `tests/test_official.py`

Phase2.6.1 experimental source, fixtures and evidence remain isolated and were explicitly excluded. Their partial validation is not substituted for the accepted baseline.

## Main-directory verification

| Check | Result | Evidence under promotion output/ |
|---|---|---|
| Main API image build | PASS | main-api-build.log |
| Main official-worker image build | PASS | main-worker-build.log |
| Main installed-test image build | PASS | main-development-build.log |
| Installed API/worker/test package equality and source correspondence | PASS | final-installed-source-equality.json; final-image-identities.json |
| Backend installed suite | PASS: 129/129, zero failures/errors/skips, 106.972s | final-installed-complete-suite.log |
| Exact original Phase1.5 grading forgery and v2 hidden isolation | PASS in installed Docker suite | test_remediation.GradingIntegrityTests and Docker regression logs |
| Phase2.5 confidentiality/terminal-state/freshness/CSV regressions | PASS | final-installed-complete-suite.log |
| Official genuine gold/negative/invalid/timeout regressions | PASS | test_official.OfficialDockerRuntimeTests |
| Frontend tests and TypeScript/Vite production build | PASS: 9/9 | main-frontend-tests-build.log |
| Current active-data copy compatibility | PASS: six runs/71 logs unchanged; idempotent initialization | migration-copy.json; main-migration-copy.log |
| Existing model file parsing | PASS: three profiles, no external requests | existing-model-configuration.log |
| Actual local good/bad fixture grading | PASS: true/false, ten expected assertions executed | local-benchmark-cli.log |
| Actual Chromium/operator/worker/harness workflow | PASS: four attempts, no page errors/failed requests | browser-final-artifact/ |
| Final HTTP/confidentiality/export/readiness checks | PASS: 27 checks | final-http-acceptance.json |
| Existing services/data/unrelated files preserved | PASS | protected-state-after-promotion.json |

Browser batch `2eb8fdcc18c74cefb00b101749bd569c`, detail run `a06f8596298e4bc8b13eff9fb3a17287`: two official instances, two deterministic profiles, actual mini-agent/Docker patch/harness reports and durable results, rendered in Chromium. Comment-only predictions were unresolved; empty predictions were accurately skipped upstream. These are infrastructure tests, not model capability scores. No paid inference occurred.

## Dataset readiness and deployment scope

Accepted pinned dataset revision `78f471bf655a3137b2e8a75af1501690ec009ec3`: **500 metadata rows, original 20-instance subset, 13 verified READY, seven BLOCKED**. The promotion test deployment uses an isolated copy of the accepted catalogue only; no temporary audit database was copied into the active service volume. Main code provides the importer/catalogue/worker integration; importing or validating into an active deployment is a separate controlled operational step.

The four formerly unprepared image identities and three network-dependent cases remain blocked in this accepted catalogue until genuine evidence is deliberately validated for that deployment. Mere image availability does not change readiness. Official reports remain separate from local grading-v2, with trusted_evidence=false. Native x86_64 and paid inference are NOT TESTED here; no external integration acceptance is upgraded.

## Checkpoint and rollback

Source checkpoint tag: **`phase26-main-accepted-20261021T171252Z`**. Exact commit and staged-path list are recorded in `output/source-checkpoint.json`. The checkpoint contains the complete accepted application manifest, including its necessary previously uncommitted Phase2.5 foundation; unrelated working-tree changes and secrets are excluded. The commit author is explicitly the Codex agent because this checkout has no configured Git identity. No remote push is performed.

Rollback procedure is in `ROLLBACK.md`: restore only promotion paths from private before/project backups after verifying current hashes, remove new paths only if unchanged, and preserve later edits. Do not reset the working tree. Existing services require no rollback because they were not changed. Never restore a database while live; any later data rollback needs a fresh online backup and an authorized controlled shutdown.

Exact reproducers: `main_suite_runner.py`, `main_browser_runner.py`, `main_runtime_checks.py`, `migration_copy.py` and image manifests under the evidence directory. Builds were run from the main root with docker/service.Dockerfile targets api, official-worker and official-development; tests mount the main tests directory read-only. Local verification used `swe-eval verify-fixture --case both` against a separate temporary database with verified local sandbox/grader images.

**Promotion acceptance gate passed.** Phase2.7 development may now use the main directory. Existing production/sub2api services remain outside the authorized deployment scope.

# Phase 1.5 Final Re-acceptance Report

Date: **2026-10-21, Asia/Shanghai**. Runtime evidence uses UTC. Tested working
tree starts from `ccf38665e142a93e62fb761908bd7bb248d7cb4c` plus the preserved
pre-existing edits and this remediation. No new commit or hosted CI run is claimed.

## Decision

**ACCEPTED for the verified Phase 1 Linux Docker deployment.** All ten mandatory
criteria and eight integrity gates pass with the evidence and limits below.
There are no remaining demonstrated P0/P1 findings in that deployment.
**AC-05 uses explicitly identified prior live-model evidence**, corroborated by
fresh installed-mini/local-HTTP integration; no fresh external inference occurred.
This acceptance does not extend to native macOS worker operation, arbitrary
external benchmarks, kernel escape resistance or production deployment hardening.

The original report and forensic artifacts are preserved. The companion
[remediation report](PHASE1_REMEDIATION_REPORT.md) describes the root causes,
changes and before/after regressions. New evidence is under
[`data/remediation-20261021/`](data/remediation-20261021/), separate from the
original rejected audit. The original 143 checks are not relabeled as if all had
been executed again.

## Mandatory acceptance matrix

| ID | Criterion | Status | Evidence and limits |
| --- | --- | --- | --- |
| AC-01 | API starts | **PASS** | Disposable API image served real HTTP; final API target recreated successfully. Actual startup logs in `output/linux-services.log`. |
| AC-02 | Health works | **PASS** | API-01 HTTP 200 with database ready; actual API restart. Health deliberately does not attest worker/model readiness. |
| AC-03 | Tasks discoverable | **PASS** | API-02; production `doctor` discovers intervals-001, pinned source and installed fixture. |
| AC-04 | OpenAI-compatible configuration | **PASS** | 18 isolated local profiles, same-alias/upstream identity, text/native actions, capabilities, pricing, usage and real HTTP error tests. No external live reasoning claim. |
| AC-05 | Real model-backed coding agent evidenced | **PASS — prior live evidence** | Original live run `99fd5433d0f44877b5c1a5a106f7e6b7`: gpt-6-astra, 4 actual requests, 2 commands, real source repair. Agent/provider files unchanged from that audited baseline; fresh actual mini 2.4.6 local-stub repairs passed both action formats and corrected grading. No new live-model claim. |
| AC-06 | Capture/apply patch in clean workspace | **PASS** | Actual mini repair patch and separate candidate evaluation; deterministic good/wrong/invalid/disallowed cases; final production queue repair. |
| AC-07 | Hidden tests execute independently | **PASS** | Separate controller container; nine preserved regressions / ten assertions; actual policy probes of all three roles; no candidate imports or mounts in controller. |
| AC-08 | Correct, incorrect and malicious classification | **PASS** | A–E deterministic tests; twelve negative integrity candidates never resolved; correct repair and hidden-access probe pass genuine controller assertions. Exact original F-01 exploit fails on final installed image. |
| AC-09 | Persist/retrieve results, logs, patches | **PASS** | Real API restart equality, authenticated artifacts, queue DB backups and integrity ok; recovered failure has null resolution; stale writes rejected. |
| AC-10 | Tests and deployability | **PASS** | 70/70 final installed-image tests, no skips; final production worker queue/CLI/doctor; API/worker/candidate/controller builds; wheel/sdist/deployment validation; Compose validation. Explicit allowed option-B dependency exception applies. |

## Additional integrity gates

| ID | Gate | Status | Evidence |
| --- | --- | --- | --- |
| IG-01 | Exact original F-01 exploit blocked | **PASS** | Before-fix test fails; final image `test_original_f01_exploit` passes; persisted forensic record shows failed/null, zero passed assertions. |
| IG-02 | Candidate stdout cannot authorize pass | **PASS** | Old/invented markers and a complete forged v2 controller verdict fail; controller independently compares JSON operation values against hidden expectations. |
| IG-03 | Hidden logic inaccessible to candidate | **PASS** | Coding/evaluation images contain no /opt/hidden, including /proc/1/root path; actual mount/PID/IPC/network probes; correct function with access-denied probe still passes all ten assertions. |
| IG-04 | Recovery cannot leave failed/resolved=true | **PASS** | Exact F-02, all synthetic crash windows, transaction rollback/race and actual crash/lease recovery produce consistent terminal states. |
| IG-05 | Infrastructure/interruption/timeout not successful | **PASS** | Terminal normalization makes resolved null; real HTTP errors, timeout, cancellation, interrupted worker; completed failed assertions false. No aggregator is implemented; consumers must still select completed agent attempts. |
| IG-06 | Validation omits credential values | **PASS** | Dummy API keys/password/bearer/auth header tests, malformed JSON, invalid auth; final response/log evidence scans find no dummy values. |
| IG-07 | Pagination overflow cannot cause 500 | **PASS** | Both actual HTTP overflow checks now 422; automated boundary matrix includes signed SQLite maximum, oversized/negative/fractional/noninteger values. |
| IG-08 | New regressions automated | **PASS** | 15 new permanent test methods with malicious subcases; original 55 retained; final image runs 70 tests with zero skips. |

**Gate totals: 18 PASS, 0 FAIL, 0 BLOCKED, 0 NOT TESTED.** One gate explicitly
relies on prior live evidence as allowed by the task. These are gate counts,
not a claim that every optional platform/security check was executed.

## Runtime and automated evidence

| Verification | Actual outcome | Evidence under new root |
| --- | --- | --- |
| Original failure reproduction | 5 methods, 8 failed assertions/subtests on unchanged code | `before/failing-regressions.log` |
| Initial core run | 66 tests, 8 explicitly skipped Docker methods | `output/unit-tests.log`; not used as Docker PASS |
| First source + actual Docker suite | 66 tests, zero skips, 48.808 s | `output/full-tests-source.log` |
| Installed wheel suite | 68 tests, zero skips, 52.611 s | `output/full-tests-installed.log` |
| Final installed Linux worker image | **70 tests, zero failures/skips, 29.163 s** | `output/full-tests-final-image.log` |
| Real HTTP REST acceptance | **48/48 PASS** | `output/api-checks.json`, `linux-api-probe.log` |
| Provider real local HTTP | **19/19 PASS** | `output/provider-checks.json`, `linux-provider-probe.log` |
| Deterministic pipeline/security/recovery | **11/11 PASS** | `output/engine-checks.json`, `linux-engine-probe.log` |
| Worker HTTP/queue/crash probe | **24/25 PASS at initial sampling**; one instantaneous cleanup check FAIL retained; completion of cleanup independently verified | `output/worker-checks.json`, `linux-worker-probe.log`, `recovery-cleanup-followup.json` |
| Per-candidate final image integrity | 13 persisted scenarios: 12 negative non-resolved, one correct hidden-access probe resolved | `output/integrity-matrix.json`, `integrity-final-image.log` |
| Three-container isolation | Coding, evaluation and controller policy probes all PASS | `output/isolation.json`, `isolation-probe.log` |
| Exact production worker target | Real queued mini repair: completed, resolved, ten assertions passed | `output/production-worker-run.json` |
| No-inference CLI | Good true / unchanged false, both matched | `output/linux-cli-fixture.log`, `production-cli-fixture.log` |
| Production worker readiness | Python 3.11.12, mini 2.4.6, one task, 18 local stub profiles, Docker 29.9.1 | `output/production-doctor.json` |
| Packaging | Wheel, sdist, deployment bundle validated; final wheel and production installed source match 23 files | `output/package-validation-final.log`, `artifact-provenance.json` |
| Dependencies | API raw pip check clean; worker raw pip check fails exactly expected nine omissions; selected lean gate succeeds | `output/pip-check-api-image.log`, `dependency-gate-image.log`, `before/pip-check.log` |
| Static checks | 26 Python files AST-parse; git diff --check clean | `output/source-provenance.json`; command below |
| SQLite | WAL-backed queue, integrity ok, backup retained | `output/database-final-check.log`, `linux-runs-final.sqlite3` |
| Credential hygiene | No tested dummy values in final service logs, responses and startup/production artifacts | `output/secret-scan.json`; automated tests |
| Existing services / cleanup | Original container IDs unchanged; API start time unchanged; one original-worker automatic restart observed at final verification; audit resources removed | `output/existing-services-unchanged.txt`, `cleanup.log` |

The Docker host is ARM64 Docker Desktop 29.9.1; tested worker Python is 3.11.12,
mini 2.4.6, FastAPI 0.115.12. The independent local virtualenv uses Python 3.12.
Fresh pinned dependencies were installed there. Docker builds used normal layer
caching and fetched the missing install layers; bit-for-bit reproducibility of
base images, apt inputs or artifacts is not claimed. Package versions are pinned;
artifact hash locking and architecture-wide CI are not implemented.

### Actual positive/negative grading results

| Candidate/scenario | Observed result |
| --- | --- |
| Known correct patch | completed; applied; ten assertions passed; resolved=true |
| Original buggy repository | completed; ten assertions compared; regression failures; resolved=false |
| Syntactically valid incorrect patch | applied; trusted assertions fail; resolved=false |
| Invalid patch | safely rejected; not_run; resolved=false |
| Empty patch | original bug detected; resolved=false |
| Exact original grader-file/marker exploit | hidden file inaccessible; operation errors; failed; resolved=null |
| Previous success marker only | no valid operation results; never resolved |
| Invented new marker only | no valid operation results; never resolved |
| os._exit(0), no function | missing JSON result; never resolved |
| SystemExit during import | missing JSON result; never resolved |
| SIGKILL during import | bounded failed operation; never resolved |
| Exception during import | diagnostic retained; never resolved |
| Hidden-file access probe + real correct function | access denied; no socket/proc-root hidden file; ten genuine assertions pass |
| Forged test output / full v2 verdict JSON | not accepted as operation result or authority; never resolved |
| Function returning incorrect values | actual trusted comparisons fail; unresolved |
| Function returning malformed object | operation serialization fails; never resolved |

The exact original exploit is stored literally in the permanent test suite and
in both original and new forensic artifacts. It was not replaced with an easier
attack. The corrected controller does not use a new marker; the invented-marker
case deliberately demonstrates that printing success-like text has no authority.

### Worker crash observation: original FAIL preserved

The disposable worker was killed during a real sleeping sandbox action. The run
remained active, one orphan was observed, and the probe waited **94 seconds** for
the actual default **90-second lease**. Restart recovery committed
`failed/worker_interrupted/resolved=null`, preserving 15 observed tokens.

The original helper queried Docker immediately after it saw that failed DB row.
It recorded one orphan and marked the composite check FAIL. This was not silently
erased or relabeled. Recovery commits its DB change before `Worker.acquire`
performs external Docker cleanup. After acquisition returned, the next queued
repair completed successfully; a follow-up Docker inventory confirmed zero
orphans. Acquisition cannot claim that next run until cleanup succeeds.

Thus the requested eventual recovery and cleanup behavior is verified; an atomic
transaction spanning SQLite and Docker cleanup is neither implemented nor
claimed. The original raw failed sample remains visible next to the follow-up
PASS. No source change or weakened regression expectation was used to hide it.

### Native macOS observation

The earlier trusted-host worker probe passed its queue and provider cases but
hit `PermissionError: Operation not permitted` in `os.killpg` while supervising a
timeout in this managed macOS session. It did not finish the remaining native
checks. Its logs and partial matrix are preserved as `native-*`,
`runtime-probe.log`, and `worker-runtime.log`. It is **not a PASS** and is not
presented as proof of native macOS support. The actual Linux Docker worker then
executed timeout, cancellation, restart and crash/lease tests successfully.
Use the Docker worker for this accepted deployment; unrestricted native macOS
signal behavior remains unverified.

## Scope, isolation and unresolved limits

No new external model call was made. Prior live evidence is at
`data/acceptance-audit-20261021/output/live-result.json`, `live-repair.patch`,
`live-execution.json`, and `live-http-retrieval.json`. That run used 2971 input
and 523 output tokens (3494 total), 31.4119 seconds. Its old grader verdict alone
is not reused to establish new grading integrity. The patch and model-agent
execution evidence are reused only where relevant, and the patch's correctness
is independently corroborated by the corrected deterministic fixture runs.
Agent/provider hashes remain unchanged, as recorded in `source-provenance.json`.

Remaining limits / NOT TESTED (not hidden PASS): hosted Actions, AMD64/other
platform matrix, live optional reasoning variants, CVE/advisory scanning,
destructive kernel escapes, stress saturation/OOM/fork attacks, shared-daemon
outage and git-bundle execution were not newly tested. Streaming is unsupported.
No configured linter/typechecker exists; AST parsing is not a typecheck. The
native worker limitation is described above. The worker's Docker authority
requires an isolated disposable VM; kernel isolation is not a formal proof.

No unresolved original P0/P1 finding remains. F-05 is resolved through the
explicitly allowed option B policy and gate; **raw worker pip check remains an
expected failure**, not a misleading PASS. Finite functional tests cannot rule
out every unseen behavioral error, hardcoded behavior equivalent on test inputs,
or kernel/side-channel attacks. Hidden expected answers and authoritative state
are excluded from candidate containers, and none of the tested stdout/exit
forgeries can suppress or impersonate the trusted assertions.

Old marker-era results and existing services were not targeted for writes,
upgrades or restarts by audit commands. Acceptance applies to the corrected build. Historical
comparisons must select new `swe-eval-grading-v2` records; legacy success labels
are not retroactively certified by this report. All disposable audit containers,
processes, network and volume were removed; corrected image tags and evidence
are retained locally for review/reproduction.

## Commands executed and reproduction

The following local audit command forms were actually used. Private keys were
not involved; `audit.env` contains only non-production test values.

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH" # macOS Docker CLI
R=data/remediation-20261021
.venv/bin/python -m venv "$R/venv"
"$R/venv/bin/python" -m pip install --no-deps \
  -r requirements-core.lock -r requirements-agent.lock \
  -r requirements-test.lock -r requirements-build.lock

# Isolated tags; do not replace tags consumed by the existing service.
docker build -t swe-eval-remediation-sandbox:20261021 -f docker/sandbox.Dockerfile .
docker build --build-arg SANDBOX_IMAGE=swe-eval-remediation-sandbox:20261021 \
  -t swe-eval-remediation-grader:20261021 -f docker/grader.Dockerfile .
docker build --target development -t swe-eval-remediation-worker:20261021 -f docker/service.Dockerfile .
docker build --target worker -t swe-eval-remediation-production-worker:20261021 -f docker/service.Dockerfile .
docker build --target api -t swe-eval-remediation-api:20261021 -f docker/service.Dockerfile .

# Trusted test container alone gets daemon access; candidates never get it.
docker run --rm --network none --user 10001:10001 --read-only --group-add 0 \
  --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:size=128m \
  -e SWE_DOCKER_TESTS=1 -e MSWEA_GLOBAL_CONFIG_DIR=/tmp/mini \
  -e SWE_TEST_AGENT_IMAGE=swe-eval-remediation-sandbox:20261021 \
  -e SWE_TEST_GRADER_IMAGE=swe-eval-remediation-grader:20261021 \
  -e PYTHONPATH=/audit-tests \
  -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD/tests:/audit-tests:ro" \
  swe-eval-remediation-worker:20261021 python -m unittest discover -s /audit-tests -v

# To run only the exact original exploit, replace the final command above with:
# python -m unittest test_remediation.GradingIntegrityTests.test_original_f01_exploit -v

"$R/venv/bin/python" -m build --no-isolation --outdir "$R/dist"
"$R/venv/bin/python" tools/package_release.py --dist-dir "$R/dist"
PYTHONPATH=src "$R/venv/bin/python" -m swe_eval.dependency_check --lean-agent
git diff --check
```

On Linux, replace `--group-add 0` with the socket's group ID when necessary.
Docker Desktop's CLI path export is not needed on Linux. Before re-running the
retained audit helpers, use a **fresh evidence directory and database**: empty-DB
API checks and their output filenames intentionally assume a new run.

The actual isolated deployment and probes used:

```bash
cd data/remediation-20261021
docker compose --env-file audit.env -f compose.remediation.json config --quiet
# API/stub first, to test empty DB and queued HTTP responses before worker starts:
docker compose --env-file audit.env -f compose.remediation.json up -d --no-build api stub
python3 api_probe.py
docker compose --env-file audit.env -f compose.remediation.json up -d --no-build worker
python3 -u worker_probe.py
# These helpers run trusted orchestration in worker; candidates use separate boxes:
docker compose --env-file audit.env -f compose.remediation.json run --rm --no-deps worker python /audit/linux_engine_probe.py
docker compose --env-file audit.env -f compose.remediation.json exec -T worker python /audit/linux_provider_probe.py
```

### Start a normal fresh development deployment

Run on a disposable Docker development/worker host; these commands are provided
for deployment and were **not** applied to the pre-existing service during audit.
Configure `.env` from `.env.example` without overwriting an existing secret file,
and edit `config/models.json` for the actual base URL/model/key reference.
Use a fresh directory/host port if another service is already bound to port 8000.

```bash
# Fresh checkout only:
cp .env.example .env
# Set a fresh SWE_ADMIN_TOKEN; set GATEWAY_API_KEY server-side; edit config/models.json.
docker build -t swe-eval-sandbox:phase1 -f docker/sandbox.Dockerfile .
docker build -t swe-eval-grader:phase1 -f docker/grader.Dockerfile .
docker compose --profile local-worker build api worker
# Run before starting the persistent worker (single-worker lease):
docker compose --profile local-worker run --rm --no-deps worker swe-eval verify-fixture --case both
docker compose --profile local-worker up -d api worker
curl --fail http://127.0.0.1:8000/health
docker compose --profile local-worker exec -T worker swe-eval doctor
docker compose --profile local-worker ps
```

For a configured live evaluation, explicitly launch it when authorized:

```bash
curl --fail http://127.0.0.1:8000/api/v1/runs \
  -H "Authorization: Bearer $SWE_ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"task_id":"intervals-001","model_profile_id":"gateway-primary"}'
# Poll /api/v1/runs/{id}; inspect /logs and /patch with the same auth header.
```

`.env` values are read by Compose; export the admin token securely in the calling
shell for curl. Model keys stay server-side. These live commands were not run in
this remediation. Direct CLI inference (`swe-eval run --task intervals-001
--model gateway-primary`) must use a dedicated worker environment and cannot
share its lease with an already-running worker.

## Next development proposal — Phase 2 only, not implemented

1. Independent administrator dashboard for authenticated runs, patches and logs.
2. Bounded batch evaluations with explicit attempt identities and versioned tasks.
3. Compare model/profile/upstream/reasoning configurations using corrected runs.
4. Read-only import/synchronization of sub2api model and upstream configuration;
   keep secrets server-side and preserve endpoint identity.
5. Integrate the independent service into the sub2api admin dashboard through an
   authenticated API boundary without sharing its database.
6. Report resolved rate, first-attempt metrics, known/unknown cost and latency
   with explicit denominators and infrastructure-error handling.
7. Read-only export to the existing gpt-auto shadow router; no routing-weight or
   production routing changes as part of that first integration.

Version/commit the accepted tree and retain this evidence before comparisons.
Phase 2 can proceed from the corrected Docker foundation; it has not begun here.

## Final operational observation

A final read-only inspection at approximately 22:07 UTC observed that the original
`swe-eval-worker-1` container (same ID `65957bd07b6f...`) had restart count **1**
and start time **2026-10-20T21:46:14.988520667Z**. Earlier captured evidence had
start time 16:27:07 UTC. The original API retained its same ID and 16:24:45 UTC
start time. Current worker state reported running, OOMKilled=false and no current
state error; this does not prove the reason for its earlier exit. The bounded
Docker lifecycle-event query returned no retained events. Cause is **NOT TESTED /
undetermined**. No restart, kill, update, upgrade or compose mutation command in
this remediation targeted the original worker. This observation must not be
reported as unchanged worker uptime or attributed to a specific cause without
additional evidence. It does not change the corrected-build grading test results.
See `output/existing-services-unchanged.txt` for the earlier snapshot,
`original-worker-events.txt` and `existing-services-final.json` for final evidence.

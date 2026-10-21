# Phase 2.5 Remediation Report

Date: 2026-10-21. Runtime timestamps UTC. Evidence: `data/phase25-remediation-20261021T114531Z/`.

**Local promotion completed at the user’s explicit request on 2026-10-21.**
All 17 verified changes are now applied to the shared checkout. The local SWE API
and worker have been restarted using the verified immutable Phase 2.5 images;
source bind mounts and automatic reload are no longer used by these services.
The existing temporary console password still works at http://127.0.0.1:8000/.

Fresh promotion evidence is under `data/phase25-promotion-20261021T133012Z/`:
13/13 deployment checks and a real Chromium login/health/run-log/patch workflow
passed. The four existing run rows and all 39 historical log rows were preserved
byte-for-byte; two explicit no-inference v2 patch-verification runs were added.
Schema remains 2. The original Phase 2/2.5 audit evidence is unchanged. No paid
inference or sub2api/routing/billing change occurred. Rollback source and a SQLite
backup are retained in the private promotion evidence directory.

The default local sandbox/grader image tags were discovered to be obsolete.
They were preserved for rollback; `compose.phase25.local.yaml` selects the
verified API/worker images and a server-owned copy of the original fixture with
verified sandbox/grader image references. Source and hidden assertions are
unchanged; new run snapshots identify the effective runtime. See
`PHASE25_LOCAL_DEPLOYMENT.md` for the exact start/restart commands.

## Baseline and reproduction

HEAD remains `ccf38665e142a93e62fb761908bd7bb248d7cb4c` plus substantial preserved
pre-existing changes. `baseline.json` freezes94 selected files; HEAD alone is
insufficient provenance. All five requested documents were read. The previous
independent audit's249 hashed evidence files are byte-identical (`preservation.json`).
No Git index/reset/checkout operation was used. Existing `.env`/model keys were
not read or copied. Work took place in a separate selected-source copy.

The unchanged installed image reproduced97 tests:96 pass, one freshness failure,
zero skips. New backend cases reproduced eight failures plus one error (the
mixed-origin freshness fixture yielded no export), one pass. New frontend cases
reproduced three failures while the original five passed. These original outputs
are retained under `before/`; no baseline was silently repaired.

`PHASE2_FINAL_FIX.patch` was reviewed and retained unchanged. Its maximum finish
time over eligible scored runs is correct for shadow freshness. Applying just
that hunk would leave comparison freshness, origins, activity/success/export
semantics unresolved. The correction was implemented with shared predicates and
separate timestamps rather than applying the patch blindly.

## Defects and code changes

| Finding | Root cause / actual change | Before / verified after |
|---|---|---|
| F-01 P1 hidden disclosure | `engine.py` no longer logs raw verdict or candidate test stdout/stderr. New `diagnostics.py` allowlists assertion counts/errors/classification, suppresses historical test_output, filters trusted_assertions; `storage.py` applies it before SQLite/Python logging and on reads; `api.py` filters again; `service.py` allowlists public execution metadata. | Before: hidden expected/observed/input values in ordinary logs. After: actual real-grader logs expose counts/status only; injected historical private canary absent from API and Chromium, retained in private DB. |
| F-02 P1 terminal batch corruption | `storage.py` deadline/cancel UPDATE requires unresolved attempts within the SQLite write transaction. Derived state gives all-completed immutable work completed priority; stopped work cancelled; other terminal infrastructure failures failed. Terminal cancel is documented HTTP202 idempotent no-op. | Before: completed→cancelled. After: natural deadline, repeated cancel, failed terminal, API reopen and six SQLite completion races preserve state and attempts. |
| F-03 P1 legacy success | `analytics.py` shared eligible_attempt/trusted_attempt/valid/trusted_success predicates enforce snapshot/protocol/mode/origin/accounting. Overview and operations reuse them. Non-live experiments are diagnostic with separate origin grouping/trusted_evidence=false. | Before: legacy-only latest_success nonnull. After: zero trusted successes and null indicator; only genuine valid v2 live-origin fixture determines timestamp. No legacy record promoted. |
| F-04 P2 freshness | Comparison evaluated_at from valid completed live evidence; separate last_attempted_at and last_trusted_success_at. Shadow sets evaluated_at from eligible scored finish times; generated_at stays export time. | Before: pending300 refreshed completed110. After: evaluated_at110; incomplete retained in reliability, no quality refresh. Original failing test retained/pass. |
| F-05 P2 Pass@1 merging | Full first-attempt identity includes versioned task, protocol/harness, profile/upstream/endpoint, configuration/runtime/effective settings and origin; explicit retry children and numbered>1 excluded. Group keys also separate effective configuration/origin. | Before: reference n4/.75. After: diagnostic n10/.8. Trusted live-only excludes synthetic config: n9,7/9. No general ranking implied. |
| F-06 P2 CSV formula prefix | New `exports.csv_cell` centralizes text protection after whitespace/Unicode control/format/BOM prefixes; csv.writer preserves quoting/newlines and non-string metrics. | Before: tab= string untouched. After: apostrophe precedes dangerous text including control prefix. Actual CSV bytes/parser confirm nine prefixes and numeric attempts1 unchanged. Formula execution not performed. |
| F-07 P2 cost omitted | Run summary displays formatted known total and actual currency (or currency unknown); unknown total has explicit unavailable message. History uses actual currency rather than forced dollar symbol. Existing aggregate cost calculations preserved. | Before: persisted cost2 absent from drawer. After: actual synthetic reference drawer2.0000 USD; unknown stub cost remains unknown, never zero. No optional breakdown exists in current schema. |
| F-08 P2 health gaps | Successful worker acquisition/renewal stores actual heartbeat in existing metadata table. Operations exposes lease state, last completed ID/time,10 recent failed/timeout run observations, queue/active and observed cleanup state. Worker records cleanup start/completion. UI distinguishes API/database/worker/Docker/upstream and renders those fields. | Before: missing dedicated fields. After: actual expired heartbeat→unready, API/database remain ready, restart renews heartbeat/cleanup. No invented upstream probe/orphan count. New event wrapping fixes a discovered390px overflow. |

No new schema version or dependency was needed. Agent/provider/sandbox/candidate
runner/hidden controller/accepted benchmark source are unchanged. The trusted
controller still compares all ten assertions in a separate hidden-only process;
candidates never receive expected answers. New verdict detail is memory-only.
Existing private forensic logs/backups are not destructively rewritten or exposed
through ordinary routes. Evidence root is0700, new backup files0600; deployment
instructions describe protecting old forensic data outside the web root.

## Permanent regressions and preserved security assertions

`tests/test_phase25.py` adds12 methods: new/historical confidentiality, terminal
completion/deadline/cancel/reopen, partial active stop, six transaction races,
legacy/synthetic/invalid-accounting success, freshness/origins, independent ten
configurations/retries, CSV parser cases, heartbeat/lease/error/recovery and
failed-terminal stability. `App.test.tsx` adds known/unknown cost and health
rendering (eight frontend cases total). Permanent Chromium checks add public-log
confidentiality, cost field and health observations and retain mobile overflow.

The original hidden-access test expected HIDDEN_ACCESS_DENIED in public raw test
logs, conflicting with the required confidentiality fix. It now observes the
same marker in private in-memory Docker grading operations, still requires ten
genuine assertions to pass, and additionally asserts that the marker/raw hidden
input echo is absent from ordinary logs. The exact original forgery attack text
is unchanged. No security assertion or expected grading outcome was weakened.

Final installed suite109/109,zero skips; frontend8/8; permanent browser3/3.
Intermediate raw-log expectation failures, local missing-FastAPI invocation,
startup probe race, CLI exclusive-lease conflict and pre-fix mobile overflow
remain in evidence. CLI was rerun correctly with only the audit worker stopped:
good true/bad false,both matched. These preliminary failures are not relabeled.

## Remaining blockers and scope

Source promotion is complete. Remaining external blockers:

1. Actual sub2api administration/synchronization requires an authorized staging
   instance and management metadata key. Sibling revision and13 local contracts
   do not establish runtime integration.
2. Actual gpt-auto consumer is unavailable. Read-only export passes locally;
   real consumer ingestion and no-write behavior remain externally BLOCKED.

Updated architecture, implementation and deployment/staging instructions are in
the corrected project copy. The companion re-acceptance report records full
matrices, commands, IDs, statistical calculations and precise deployment scope.

# Implementation validation

Latest completed application acceptance: **216 installed-image backend tests, zero skips; 33 frontend tests; TypeScript/Vite build; real Chromium and Docker/official-grader retry workflows PASS**. See [API_RETRY_ACCEPTANCE_REPORT.md](API_RETRY_ACCEPTANCE_REPORT.md). The backend source still matches that accepted manifest. All local SWE test stacks were subsequently stopped at the user’s request; see [SWE_TEST_DOCKER_SHUTDOWN_REPORT.md](SWE_TEST_DOCKER_SHUTDOWN_REPORT.md). No Docker services were restarted for this source checkpoint.

Earlier local validation: **2026-10-21**, macOS ARM64, Docker Desktop 29.9.1.
The earlier host-only checks lacked Docker and API dependencies. The Docker
checks below supersede those initial limitations.

## Local Docker development

- Built native ARM64 sandbox, hidden grader, API, and development worker images.
  The worker runs Python **3.11.12**, pinned runtime dependencies, and actual
  mini-SWE-agent **2.4.6**. Its doctor command reports Docker **29.9.1**, one
  trusted task, and two example model profiles.
- Validated the merged `compose.yaml` / `compose.dev.yaml` configuration. The
  API receives no inference credentials or Docker socket. Source/configuration
  mounts are read-only; service processes run as UID 10001.
- Created ignored `.env` and `models.local.json` files with mode 0600. The
  administrator token is generated randomly and was not printed or committed.
- Started the API on **127.0.0.1:8000** and verified `/health`, authenticated
  task/model discovery, and HTTP 401 for unauthenticated task access. Verified
  source auto-reload and successful application startup after the reload.
- Ran the full suite inside the development worker:

  ```bash
  docker compose run --rm -e SWE_DOCKER_TESTS=1 worker \
    python -m unittest discover -s /app/tests -v
  ```

  **55 tests passed, zero skips or failures.** This includes API authentication,
  storage/recovery/redaction, provider budgets/usage, actual installed-mini
  protocols, and five real Docker integration tests. The agent integration test
  uses explicitly scripted inference responses and real inspect/edit commands;
  it does not establish a live model's coding ability.
- Ran `docker compose run --rm worker swe-eval verify-fixture` before starting
  the background worker. The known repair applied to the clean grader workspace
  and passed **9/9 hidden regressions**, test exit 0, `resolved=true`. Unchanged
  source actually executed the regressions and failed, test exit 1,
  `resolved=false`. Both cases matched their expected outcomes.
- Retrieved both persisted `mode=patch_verification` runs, details, logs, and
  patches through the authenticated HTTP API. The known repair patch is 451
  bytes; the unchanged patch is empty. Both have zero model requests and unknown
  token usage/cost. These results are excluded from model scores.
- Started the independent background worker and verified its installed mini and
  Docker dependencies. SQLite results reside in the `swe-eval_swe-data` named
  volume, shared with the API.
- Built a wheel and source distribution using the available host build backend,
  then ran `tools/package_release.py` against them. Fixture/deployment validation
  passed, including the new development Compose override. Local secrets and
  runtime files remain excluded from the distributions.
- No benchmark repository Python code was executed on the macOS host. Candidate
  and hidden test execution occurred inside isolated Docker containers.

HTTP Debian mirrors intermittently returned 502 during initial worker builds.
The service Dockerfile now uses HTTPS mirrors with bounded download retries;
the resulting build succeeded. Nested host bytecode and egg-info directories
are excluded from Docker build contexts.

## GitHub CI and packaged worker

Commit `ccf38665e142a93e62fb761908bd7bb248d7cb4c` passed both workflows:

- [Tests](https://github.com/ZhuomaSoftware/swe-eval/actions/runs/39444040781):
  installed dependency/API/mini checks, real Docker integration tests, and the
  no-inference fixture demonstration.
- [Build and package](https://github.com/ZhuomaSoftware/swe-eval/actions/runs/39444040738):
  Python distributions, deployment archive validation, installed-wheel API/task
  smoke checks, AMD64 image builds, and actual good/bad repair execution using
  the packaged worker before image artifact upload.

Pip's automatic bytecode compilation initially contaminated the immutable
fixture snapshot. The service package installation and installed-wheel CI check
now use `--no-compile`. The fixture's pinned base remains
`180a5be07e3c5fb60d5759748a32a77e80566e85`.

## Live gateway evaluation

On 2026-10-21, configured profile `zhuoma-astra`, upstream `zhuomatech-api`, and
model ID `gpt-6-astra` using user-supplied temporary credentials. Credentials are
stored only in ignored `.env` and the worker environment. The gateway's
`/v1/models` returned HTTP 200 and advertised that model. Actual Chat Completions
requests accepted `max_completion_tokens`, text actions, and no requested
reasoning effort. No inference traffic used the scripted test transport.

Both evaluations were submitted through the authenticated REST API and executed
by the background worker with real mini-SWE-agent 2.4.6 and isolated Docker
workspaces. Limits were 12 agent commands, 15 model requests, 4096 output tokens
per response, 60,000 reported total tokens, and 600 seconds.

| Run | State / result | Model requests | Agent commands | Input / output tokens | Wall time |
| --- | --- | --- | --- | --- | --- |
| `9e965a25e27449ad8e987896080f0ce9` | completed / unresolved; patch rejected, hidden tests not run | 4 | 2 | 3508 / 516 | 32.1724 s |
| `a460fb694df5495081c69f910876bab4` | completed / resolved; hidden tests passed | 3 | 2 | 2429 / 467 | 24.4771 s |

The first attempt fixed the source but also added tests to `test_public.py`.
The task permits only `intervals.py`, so the grader correctly rejected the full
patch. Investigation found that the agent prompt omitted the task's allowed
patch paths. Updated the adapter to communicate that existing policy, added
regression assertions to the real-mini Docker test, and reran all **55 tests**
successfully with no skips. The task manifest, grading rules, and hidden tests
were not relaxed or changed.

Submitted the second run through the retry endpoint, preserving `parent_id`
linkage to the original. The model inspected files, changed `<` to `<=` in
`intervals.py`, ran public and additional ephemeral checks, and submitted a
source-only patch. The engine captured the 451-byte Git patch, applied it to a
fresh clean evaluator, and actually executed **9/9 hidden regressions**, exit
code 0 with the trusted completion marker. `patch_applied=true`,
`resolved=true`, zero API errors, and 2896 total tokens were persisted.

Both original and retry remain in SQLite and are retrievable through run,
logs, and patch endpoints. Exported results/logs/patches under ignored
`data/live-runs/<run-id>/` after verifying they contain no configured secrets.
The retry is not a first-attempt pass, and one small fixture does not establish
an aggregate resolved rate or Pass@1. Model identity is the identifier requested
from the gateway; upstream implementation identity is not independently
attested. Reasoning tokens were not supplied. No pricing was configured, so
cost remains unknown rather than estimated.

The two untouched example gateway profiles still contain placeholder URLs.
Only `zhuoma-astra` was used for the live check. Temporary credentials will need
replacement after their stated expiry for additional live requests.

Pinned Python dependencies are not hash-locked. Base-image tags and Debian
packages are not pinned to immutable digests/snapshots. The Docker worker's
host-level authority and remaining isolation limitations are documented in
README; these checks do not establish adversarial sandbox security.

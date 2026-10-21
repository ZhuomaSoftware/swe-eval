# SWE Evaluation Center — Phase 2.7

The current application includes a Chinese administration console for encrypted
API providers, versioned model profiles, official dataset metadata, immutable
benchmark subsets and reviewed batch experiments. New managed configurations are
available without restarting the API or worker. Use the empty managed-profile
fallback in `compose.management.yaml`; model JSON editing is not required.

The qualified standalone deployment uses a native Linux Docker data volume and
an explicit schema-3 migration. The official catalogue contains 500 records and
the original 20-instance subset retains **13 READY / 7 ineligible**. This internal
subset is not a full official SWE-bench score. Phase 2.7 verification used local
deterministic providers and genuine grading infrastructure, without paid inference.

Start with the [deployment guide](PHASE27_DEPLOYMENT_GUIDE.md),
[architecture](PHASE27_ARCHITECTURE.md),
[implementation report](PHASE27_IMPLEMENTATION_REPORT.md) and
[acceptance report](PHASE27_ACCEPTANCE_REPORT.md).
The [Phase 2.6 promotion report](PHASE26_PROMOTION_REPORT.md) records the source
promotion and preservation of existing services/data.

## Historical Phase 1 material

The instructions and observations below are retained for historical compatibility.
Their test counts and earlier live-run statements are not the current acceptance
result. Legacy marker-based grading records are not trusted evaluation evidence.
Use the current reports for grading-v2, official-harness trust boundaries,
confidentiality, migrations and deployment readiness.

A standalone FastAPI API and durable single-worker SWE evaluation backend. It
does not import or change sub2api. Model requests go to administrator-configured
OpenAI-compatible gateways. Candidate repository code runs exclusively in Docker.

Source repository: [ZhuomaSoftware/swe-eval](https://github.com/ZhuomaSoftware/swe-eval).

An evaluation captures a real Git diff, applies it to a second clean repository,
and executes hidden regression tests. Model text, an HTTP 200, and an agent's
`SUBMIT` response cannot establish resolution.

**Validation status:** all 55 tests pass in the local ARM64 Docker development
environment, including installed-mini/API tests and real sandbox execution.
The known repair passes all nine hidden tests; unchanged code fails. GitHub CI
also validated the packaged worker on AMD64. A live `gpt-6-astra` run through a
user-configured gateway repaired the fixture and passed all nine hidden tests
after a prompt-policy correction; the original rejected attempt is preserved.
See [VALIDATION.md](VALIDATION.md) for both results. This validates one fixture's
workflow and does not establish an aggregate model benchmark score.

## Quick start with Docker Compose

Requirements: Docker Engine/Desktop with Compose v2, access to the Python and
Debian image/package registries, and an OpenAI-compatible Chat Completions endpoint
for live inference. Linux workers must use a Docker daemon with the default
seccomp profile and resource-limit support. Use a disposable VM for the worker.

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Put the generated value in `.env` as `SWE_ADMIN_TOKEN`. Edit
`config/models.json`: replace the example base URL/model ID and select the
capabilities your gateway supports. Set `GATEWAY_API_KEY` in `.env` only when
performing live inference. The API never receives the inference keys in Compose.
The example administrator placeholder is rejected at startup.

Build the two **different** execution images before running the worker:

```bash
docker build -t swe-eval-sandbox:phase1 -f docker/sandbox.Dockerfile .
docker build -t swe-eval-grader:phase1 -f docker/grader.Dockerfile .
docker compose --profile local-worker build
```

On Linux export the Docker socket's group before Compose commands:

```bash
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
```

First run the deterministic, no-inference demonstration, with no background
worker running:

```bash
docker compose --profile local-worker run --rm worker swe-eval verify-fixture
```

It runs the same supervisor, clean preparation, patch application, and hidden
grader as model runs. It requires `good → resolved=true` and
`unchanged → resolved=false`, with actual test exit codes. Both results and logs
are stored as `mode=patch_verification`; they are **not model evaluations**.
No API key is needed for this command.

Start the API and worker:

```bash
docker compose --profile local-worker up -d api worker
curl --fail http://127.0.0.1:8000/health
```

The API is bound to loopback and has no Docker socket. The worker has no exposed
port. SQLite schema initialization happens automatically on startup; the named
`swe-data` volume retains results across restarts. Do not delete the volume to
restart the service.

Load the administrator token into your shell for the following API examples
(this also loads any local gateway credentials; use a dedicated shell):

```bash
set -a
. ./.env
set +a
curl --fail -H "Authorization: Bearer $SWE_ADMIN_TOKEN" http://127.0.0.1:8000/api/v1/tasks
curl --fail -H "Authorization: Bearer $SWE_ADMIN_TOKEN" http://127.0.0.1:8000/api/v1/models
curl --fail -X POST http://127.0.0.1:8000/api/v1/runs \
  -H "Authorization: Bearer $SWE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"intervals-001","model_profile_id":"gateway-primary"}'
```

Copy `id` from the 202 response, then poll and retrieve artifacts:

```bash
RUN_ID=replace-with-returned-id
curl --fail -H "Authorization: Bearer $SWE_ADMIN_TOKEN" "http://127.0.0.1:8000/api/v1/runs/$RUN_ID"
curl --fail -H "Authorization: Bearer $SWE_ADMIN_TOKEN" "http://127.0.0.1:8000/api/v1/runs/$RUN_ID/logs?after=0&limit=200"
curl --fail -H "Authorization: Bearer $SWE_ADMIN_TOKEN" "http://127.0.0.1:8000/api/v1/runs/$RUN_ID/patch" -o repair.patch
```

`completed` means grading finished; inspect `metrics.resolved` and
`metrics.test_result` for the result. A failed regression suite is a completed,
unresolved run. Infrastructure failure is `failed`; no verdict is invented.

## Full local Docker development

Docker Desktop can run the API, worker, database, and all tests without a host
Python virtualenv. On macOS, if `docker` is missing from your terminal PATH:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Create `.env` and its administrator token as described above. Copy the model
examples into the ignored local configuration:

```bash
cp config/models.json models.local.json
```

Set these values in `.env` to enable the development override and local worker:

```dotenv
SWE_MODELS_FILE=./models.local.json
COMPOSE_FILE=compose.yaml:compose.dev.yaml
COMPOSE_PROFILES=local-worker
```

Then build and start everything:

```bash
docker build -t swe-eval-sandbox:phase1 -f docker/sandbox.Dockerfile .
docker build -t swe-eval-grader:phase1 -f docker/grader.Dockerfile .
docker compose build
# Verification takes the single-worker lease; stop an existing worker first.
docker compose stop worker
docker compose run --rm worker swe-eval verify-fixture
docker compose up -d
curl --fail http://127.0.0.1:8000/health
docker compose exec worker swe-eval doctor
```

[`compose.dev.yaml`](compose.dev.yaml) mounts service source read-only and reloads
the API when Python source changes. Worker changes take effect with
`docker compose restart worker` after active runs finish. The development worker
also includes the pinned API test dependencies and Git for the temporary Git
unit tests. Run the complete suite, including actual Docker execution:

```bash
docker compose run --rm -e SWE_DOCKER_TESTS=1 worker \
  python -m unittest discover -s /app/tests -v
```

Use `docker compose logs -f api worker` for logs and `docker compose down` to stop
the environment. Results remain in the named volume; `down -v` deletes them.
Neither model credentials nor a frontend are required for the fixture check.

For a live evaluation, edit `models.local.json` with your actual base URL/model
and put the referenced API key in `.env`. If the gateway runs on this Mac, use
`host.docker.internal` instead of `localhost` in its URL; plain HTTP additionally
requires `"allow_http": true` in that model profile. Recreate both services after
configuration changes with `docker compose up -d --force-recreate`, then submit
the authenticated API request shown above. Keep this configuration local; only
the dedicated worker receives the gateway keys and Docker socket.

## Local Python development and CLI

Use Python 3.11 or newer, with Docker running. The Python service itself does not
need Git installed; Git operations for runs execute inside sandboxes. A host Git
binary is needed by the offline baseline/patch unit test.

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps -r requirements-core.lock -r requirements-agent.lock -r requirements-test.lock
python -m pip install --no-deps --no-build-isolation -e .
cp .env.example .env
# Edit .env and config/models.json, then:
set -a
. ./.env
set +a
swe-eval init-db
swe-eval doctor
swe-eval serve --host 127.0.0.1 --port 8000
```

In another terminal with the same virtualenv and environment:

```bash
swe-eval worker
```

Or, with the background worker stopped, run a single model evaluation directly:

```bash
swe-eval run --task intervals-001 --model gateway-primary
```

This blocks until completion, prints the persisted result, and exits 0 only for
a resolved task, 1 for an unresolved run, or 2 for startup/configuration errors.
It uses the same single-worker lease as the background worker. A direct CLI run
cannot execute concurrently with a worker. Older queued runs remain queued.

The no-inference demonstration is also available directly:

```bash
swe-eval verify-fixture --case both
```

The `requirements-*.lock` files pin the supported lean import closure. The
documented `--no-deps` install deliberately installs mini's `DefaultAgent` and its
imports without its unrelated LiteLLM, dataset, and interactive CLI stack. Our
own provider and sandbox implement mini's protocols. Mini's unused tools are
unsupported in this lean environment, and `pip check` will report its unused
declared dependencies. Conventional `pip install '.[agent,test]'` installs that
larger upstream dependency graph instead, without a transitive lock.

The supported release uses **option B: an audited reduced import closure**.
Exactly these upstream requirements are omitted: `datasets`, `litellm`, `openai`,
`prompt-toolkit`, `pyyaml`, `requests`, `tenacity`, `textual`, and `typer`.
Only `DefaultAgent` plus this service's model/environment adapters are supported;
upstream mini CLIs, UI, dataset loading, LiteLLM/OpenAI adapters, retry utilities,
and their configuration loaders are unsupported. Installing the complete graph
would bring unrelated dataset, provider and interactive stacks into the
worker. Keeping the existing bounded service path avoids that overhead.

```bash
python -m pip check  # Expected exit 1: those nine missing requirements
python -m swe_eval.dependency_check --lean-agent
# Exit 0 only for the exact exception AND the supported installed mini API.
# Output explicitly says pip_check=FAILED_EXPECTED; any drift fails the gate.
```

Docker builds and both CI workflows enforce this exception gate. Tests also run
the actual installed DefaultAgent with both action formats. The lean
pins and Docker builds are exercised in CI; they are not hash-locked. Base-image
tags and Debian apt inputs are not immutable
digest/snapshot pins; record and pin their digests before a production release.

## Build and package workflow

[`.github/workflows/build-package.yml`](.github/workflows/build-package.yml) adds a
**Build and package** workflow. It runs on pushes to `main`/`master`, `v*` tags,
pull requests, and manual dispatch. Tagged builds must match the version in
`pyproject.toml` (for example `v0.1.0`). Pull requests build Python packages only;
manual runs can also disable image builds using the `build_images` input.

The Python job runs backend/API/installed-mini contract tests, builds a wheel and
source distribution, validates their benchmark/deployment contents, assembles a
deployment archive, installs the wheel, and smoke-tests `/health` and task
discovery from outside the source checkout. Docker tests remain in the existing
`test.yml` workflow. The image job also runs the good/bad fixture demonstration
using the actual built worker before packaging its images.

Open the workflow run's **Artifacts** section or its summary links to download:

| Artifact | Contents | Retention |
| --- | --- | --- |
| `swe-eval-python-<version>-<commit>` | Wheel, sdist, deployment source archive, build metadata, SHA-256 checksums | 14 days |
| `swe-eval-images-<version>-linux-amd64-<commit>` | Compressed Docker image bundle, image IDs/build metadata, SHA-256 checksums | 7 days |

The Python wheel is platform independent. The Docker bundle targets
**Linux AMD64** and contains `swe-eval-api:<version>`,
`swe-eval-worker:<version>`, `swe-eval-sandbox:<version>`, and
`swe-eval-grader:<version>`, plus the `phase1` sandbox/grader aliases expected by
the fixture manifest. ARM hosts require emulation or local native image builds.
Artifacts are stored on workflow runs using
[GitHub's artifact mechanism](https://docs.github.com/en/actions/tutorials/store-and-share-data).
The workflow needs only `contents: read` and no gateway credentials, PyPI token,
or registry credentials. It does not create a release or publish registry images.

Local Python packaging, using the supported virtualenv:

```bash
python -m pip install --no-deps -r requirements-core.lock -r requirements-build.lock
python -m build --no-isolation
python tools/package_release.py
```

Install a built wheel with `python -m pip install --no-compile <wheel-file>`.
The fixture's Python files are immutable benchmark data. Pip's default bytecode
compilation adds `__pycache__` files inside that snapshot, which correctly causes
its base-commit check to fail. The service images and installed-wheel CI check
use `--no-compile`; `PYTHONDONTWRITEBYTECODE=1` alone does not disable pip's explicit
compilation. The installed-wheel smoke test also validates the source archive
before checking the API.

Build into a clean `dist/` directory: the validator expects one wheel for the
current version. [`MANIFEST.in`](MANIFEST.in) includes deployment requirements in
the sdist. The deployment archive uses an explicit file allowlist and bundled
service source, excluding runtime databases, `.env`, virtualenvs, Git metadata,
and local model configuration. Only `.env.example` and the example
`config/models.json` are shipped. Metadata records the version, source repository,
commit when available, and build timestamp. `SOURCE_DATE_EPOCH` is taken from the
checked-out commit in CI.

To deploy the downloaded archives, unzip the Python artifact into `python/` and
the Docker artifact into `images/`, preserving their separate checksum files.
The following example uses version `0.1.0`; substitute the downloaded version:

```bash
(cd python && sha256sum --check SHA256SUMS)
(cd images && sha256sum --check SHA256SUMS)
docker image load --input images/swe-eval-images-0.1.0-linux-amd64.tar.gz
tar -xzf python/swe-eval-0.1.0-deploy.tar.gz
cd swe-eval-0.1.0
cp .env.example .env
# Set a fresh administrator token, gateway configuration, and worker keys.
export SWE_IMAGE_TAG=0.1.0
# Linux only: export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
docker compose -f compose.yaml -f compose.packaged.yaml --profile local-worker \
  up -d --no-build --pull never api worker
```

`docker image load` restores the saved images and tags
([Docker documentation](https://docs.docker.com/reference/cli/docker/image/load/)).
The [`compose.packaged.yaml`](compose.packaged.yaml) override selects loaded
versioned images. The dedicated worker still needs its isolated Docker daemon/VM
as described in the security section. The API container has no Docker socket.

To configure the source repository as a local remote, initialize Git if needed
and add the requested remote:

```bash
git init -b main
git remote add upstream-repo https://github.com/ZhuomaSoftware/swe-eval.git
```

If that remote already exists, use `git remote set-url upstream-repo` with the
same URL instead. Commit and push the workflow through your normal repository
workflow before expecting it to appear in GitHub Actions.

## Model profiles and compatibility

See [`config/models.json`](config/models.json). `id` is the evaluation profile
identity; `upstream_id` identifies the endpoint/channel. `model_id` is sent
verbatim to the upstream. Two profiles may use the same `model_id`, with different
URLs, credential references, budgets, or channels. Names such as `5.6-luna`,
`5.6-sol`, `6-luna`, and `6.1-sol` need no provider-specific implementation.

| Setting | Meaning |
| --- | --- |
| `base_url` | OpenAI-compatible base, for example `https://gateway.example/v1`; `/chat/completions` is appended |
| `api_key_env` / `api_key_file` | Exactly one server-side secret reference; never put the key in JSON |
| `allow_no_api_key` | Explicit opt-in for a trusted endpoint requiring no credential |
| `allow_http` | Explicit opt-in for unencrypted local/private endpoints; HTTPS is the default |
| `capabilities.action_format` | `text` (one bash block) or `native_tools` (bash/submit functions) |
| `capabilities.reasoning_effort` | Whether to send the optional profile `reasoning_effort` |
| `capabilities.output_token_parameter` | `max_tokens` or `max_completion_tokens` |
| `request_timeout` | Per-request socket timeout; worker also enforces absolute run duration |
| `max_output_tokens` | Per-response output cap |
| `max_agent_steps` | Maximum executed agent shell commands |
| `max_model_calls` | Maximum inference requests, including formatting errors |
| `max_evaluation_duration` | Whole run wall-clock budget, including preparation and grading |
| `max_total_tokens` | Optional stop threshold using upstream reported token usage |
| `max_context_chars` | Hard pre-request serialized context size bound |
| `pricing` | Optional `{ "input_per_million": 2, "output_per_million": 8, "currency": "USD" }` |

There are no automatic capability downgrades or hidden inference retries.
Incompatible HTTP 400/404/405/422 responses generate a compatibility error naming
the settings to check. Text actions work without native tool calling. Responses
API, provider-specific authentication, streaming, image input, and arbitrary tool
schemas are not implemented. If usage is absent, token/cost fields remain `null`.

The total-token threshold is checked between requests; prompt tokens are not
known in advance, so a request can exceed the remaining threshold. Output tokens
are capped by the remaining budget, but this is not a hard total billing ceiling.
If a total-token budget is configured and usage is missing, inference stops after
that response. Reasoning tokens, when reported, are a subset of completion tokens
and are not added to cost twice. The price estimate assumes uncached input/output
rates; it does not model gateway discounts or cache tiers.

Profiles and tasks are snapshotted when queued. A configuration fingerprint
includes the URL and secret reference, never the secret value. Changed task or
profile configuration fails an existing queued run and requires a new submission.
Restart API and worker after editing configuration. API responses omit URLs,
credential references, hidden test commands, and success markers.

## Pipeline and project structure

```text
src/swe_eval/
  api.py                 authenticated REST API; no execution worker in HTTP
  worker.py              durable claim, lease, subprocess supervision, cleanup
  engine.py              prepare → agent → capture → clean apply → hidden tests
  agent.py               mini-SWE-agent DefaultAgent adapter and installed API check
  providers.py           bounded Chat Completions provider and usage accounting
  sandbox.py             Docker CLI boundary; no host execution fallback
  storage.py             RunRepository protocol and SQLite implementation
  schema.py              validated task, model, result, and state schemas
  benchmarks/local.py    trusted local snapshot/git-bundle adapter
  benchmarks/data/       versioned fixture, known repair, separate hidden grader
docker/                  API/worker, agent sandbox, and grader images
tests/                   offline, API, and opt-in real Docker integration tests
```

1. API stores a trusted task/profile snapshot as `queued`.
2. An independent worker atomically claims it as `preparing`.
3. Worker copies only the task's source archive into a restricted container,
   initializes/clones Git, and checks out the exact base commit.
4. `running`: a bounded tracked-file listing and README provide initial repository
   context alongside the issue. Actual mini `DefaultAgent` queries our provider, executes bash
   actions, observes command results, and edits the repository. No local mini
   environment or upstream agent execution facade is used.
5. Worker captures a binary-capable Git patch, including new files, and destroys
   the coding container. Step/call/format budgets can leave a partial patch, which
   is still independently graded; an agent submission is not itself a verdict.
6. `evaluating`: a new **candidate** container, using the coding image without
   hidden files, prepares the original base, checks/applies the patch, and
   validates changed paths and file modes. Invalid patches remain unresolved.
7. A third, trusted **controller** container receives no candidate source or
   workspace. It supplies nine operation inputs through the trusted worker;
   isolated candidate Python returns untrusted JSON operation values. The
   controller checks all nine original regressions (ten assertions including
   input preservation), counts actual assertions, and returns its verdict.
   Expected answers, hidden files, and controller state never enter a candidate
   container. Candidate stdout, exit codes, exceptions, signals and fake markers
   cannot authorize success. Missing/malformed operations are execution errors;
   valid operations with incorrect values fail assertions. The test deadline
   covers all operations together. The old `success_marker` field is retained
   for manifest compatibility and is **never used to determine a verdict**.
8. Worker stores test results, metrics, safe logs, patch, image digests, and final
   state. No raw provider request/response headers or key-bearing trajectories
   are persisted.

mini is pinned to **2.4.6**. `verify_mini_api()` inspects the installed version,
constructor, configuration fields, and methods before execution and refuses an
unsupported installation. The adapter follows the tagged upstream
[DefaultAgent](https://github.com/SWE-agent/mini-swe-agent/blob/v2.4.6/src/minisweagent/agents/default.py)
and [model/environment protocols](https://github.com/SWE-agent/mini-swe-agent/blob/v2.4.6/src/minisweagent/__init__.py).
The installed API contract check passes in local Docker development and CI.

## Task format and fixture

[`task.json`](src/swe_eval/benchmarks/data/intervals/task.json) defines:
task ID, benchmark/version, repository source, exact base commit, issue,
trusted controller command argv, `isolated_operations_v2` grading protocol, permitted patch paths,
runtime/image requirements, resource limits, and timeouts. Only administrator
installed manifests are loaded; there is no API to accept repositories, patches,
test commands, images, or URLs from clients.

The local adapter supports:

- **snapshot**: regular files beneath the task directory. The canonical baseline
  commit uses fixed identity, timestamp, file modes, and message. The source hash
  is checked before execution, and real Git verifies the commit inside Docker.
- **git_bundle**: an administrator-created `git bundle` inside the task directory,
  cloned offline inside the sandbox and checked out at `base_commit`. Symlinks,
  special archive entries, `.git` directories, escaping source paths, and source
  archives over 32 MiB are rejected.

The `intervals-001` repository has a real endpoint-overlap bug in `merge_ranges`.
The coding container receives only `repository/` with buggy source, README, and
two public smoke tests. The separate controller image includes nine regressions
with ten assertions; candidate execution cannot read it.
`known_good.patch` changes `<` to `<=`; unchanged source fails touching-endpoint
and related cases. The known repair and hidden files are never copied to the
agent container.

To add a private local task, install a manifest/source beneath `SWE_TASK_DIR`,
build its candidate/controller images and implement the isolated operation
protocol for that task, then set the manifest image names. The current operation
runner supports only this interval fixture; arbitrary test commands and external
benchmark harnesses are not claimed compatible. Keep
hidden files out of the agent build context layers. The `BenchmarkAdapter`
protocol is the extension point; **SWE-bench Verified and SWE-bench Pro adapters
are not implemented or claimed compatible**.

## API and run recovery

All `/api/v1/*` endpoints require `Authorization: Bearer <SWE_ADMIN_TOKEN>`.
Only `GET /health` is public. Interactive documentation/OpenAPI endpoints are
disabled. Put TLS, access restrictions, and request-size/rate limits in a reverse
proxy before exposing an administration API beyond loopback.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | API/database readiness; does not imply a worker is running |
| GET | `/api/v1/tasks` | Trusted task discovery |
| GET | `/api/v1/models` | Safe model-profile discovery |
| POST | `/api/v1/runs` | Queue a task/profile pair; HTTP 202 |
| GET | `/api/v1/runs?limit=50&offset=0` | Persisted runs |
| GET | `/api/v1/runs/{id}` | State, result metrics, snapshots |
| GET | `/api/v1/runs/{id}/logs?after=0&limit=200` | Persisted logs with sequence cursor |
| GET | `/api/v1/runs/{id}/patch` | Plain text patch attachment |
| POST | `/api/v1/runs/{id}/cancel` | Cancel queued run or request active cancellation |
| POST | `/api/v1/runs/{id}/retry` | Explicitly queue a new terminal agent-run attempt |

States: `queued`, `preparing`, `running`, `evaluating`, `completed`, `failed`,
`timeout`, `cancelled`. SQLite uses WAL, short transactions, atomic claims, and
a 90-second renewable worker lease. After a crash, restart waits for any previous
lease to expire. The next owner marks interrupted active jobs `failed` with
`worker_interrupted` and cleans up containers by service/run labels. Queued jobs
remain durable. Completed results are preserved. Interrupted paid evaluations
are never automatically retried. Retry creates a new ID with `parent_id`.

The parent supervises each run in a spawned Python process and enforces an
absolute wall-clock deadline even if inference or an agent command hangs.
Cancellation is observed approximately every 0.2 seconds, then the child is
terminated and all run containers are forcibly removed. Cleanup may take additional
seconds; a failing/unreachable Docker daemon is an operator incident and stops
further worker scheduling. Stopping the worker cancels an active run.

## Metrics and interpretation

Each result records `resolved`, `patch_applied`, test status/exit codes, agent
commands, model requests, input/output/reasoning/total tokens, API errors,
agent-command errors, test infrastructure errors, cost/currency, wall time,
model/profile/upstream IDs, requested reasoning effort, mini version, benchmark
version, runtime policy, base commit, and actual container image digests.
Nonzero agent commands count as agent execution errors even when the agent later
recovers. Assertion failures are test failures, not infrastructure errors.

`null` means unavailable or no trustworthy verdict. Unknown usage never becomes
zero. A partially known usage total is reported as unknown; estimated cost is
unknown unless all input/output usage and pricing are available. Zero model
requests on a patch-verification run does not make it a free model evaluation.

For future aggregates, filter to `mode=agent`, group by task/dataset version and
model profile/upstream, identify first attempts using `parent_id`, and separately
count infrastructure failures/timeouts/cancellations. Pass@1 and cost per resolved
task need a declared denominator and unknown-cost policy; no aggregate benchmark
score, leaderboard, or router modification is implemented in Phase 1.

## Security boundaries and remaining limits

- No candidate code runs in API/worker host Python. Git and all repository
  commands run in sandboxes; offline tests use host Git only on trusted fixture
  bytes, without importing/executing fixture Python.
- Sandboxes use non-root UID/GID 10001, read-only root filesystems, no privileges
  or Linux capabilities, no-new-privileges, Docker's default seccomp, private IPC,
  process/CPU/memory/no-swap/file-descriptor limits, bounded tmpfs workspaces,
  bounded captured output, command timeouts, and `--network=none`.
- Sandboxes have no host bind mounts, named volumes, Docker socket, host home,
  service database, `.env`, provider key, or production credential. Repository
  source is streamed through stdin. Images must be prebuilt (`--pull=never`).
- Hidden tests are root-owned in a separate controller image. Neither coding
  nor evaluation candidates use that image. The controller has its own PID/IPC,
  mount and network namespaces, no mounts, and no candidate workspace. All three
  containers are discarded; no coding process survives into evaluation.
- Provider calls happen in the trusted worker. HTTPS is verified; redirects and
  implicit environment proxies are disabled. Exceptions omit HTTP bodies/headers.
  Known configured secrets and credential patterns are redacted from logs.
  Patches containing such material are rejected rather than silently rewritten.
  Restrict the worker's network egress to the configured gateway in deployment.
- The Compose `local-worker` profile deliberately mounts the host Docker socket
  **only into the dedicated worker**. Socket access is effectively host-root
  authority, including when its Unix mount is marked read-only. Run this profile
  only on a disposable development/worker VM without production credentials or
  other workloads. Never add the socket to an exposed API container. For
  production, place the worker and its daemon on a separate disposable VM and
  restrict administration/network access; this Compose file is a development
  topology, not strong host isolation.
- Docker shares the host kernel and does not guarantee protection from container
  escapes, all side channels, or malicious kernel exploits. CPU timeouts are not
  a substitute for a hardened daemon/host. A daemon outage can prevent cleanup.
- The trusted controller evaluates untrusted JSON primitives from candidate
  operations, not candidate-generated verdicts. It never imports candidate code.
  Like any finite functional suite it cannot prove correctness for unseen inputs
  or distinguish an equivalent operation implementation from hardcoded correct
  behavior. Kernel escapes and side channels remain outside the tested boundary.
  The service remains restricted to trusted, predefined tasks.
- Stored patches/logs may contain private benchmark source; protect the SQLite
  directory and backups. There is no artifact retention quota/automatic deletion,
  multi-tenant authorization, public signup, or arbitrary repository execution.

## Tests and release gates

```bash
python -m unittest discover -s tests -v
SWE_DOCKER_TESTS=1 python -m unittest discover -s tests -v
swe-eval verify-fixture
```

Install the pinned core, agent, and test dependencies before running the suite;
the remediation tests require them and fail explicitly if they are missing.
The second command enables real Docker
tests (both images must exist): hidden-test separation, valid/unchanged repairs,
disallowed patches, rejection of a zero exit without tests, and an actual installed mini agent inspecting/editing the
container using scripted inference responses. Scripted responses are a test
transport only and are never a production provider or benchmark score.

CI in [`.github/workflows/test.yml`](.github/workflows/test.yml) installs the lean
pins, builds images, enables Docker tests, and runs the fixture demonstration.
Hosted CI has not been triggered for this remediation. Before release, run those gates and then
one real gateway evaluation; inspect patch, hidden-test output, usage, endpoint
identity, and restart persistence. A live model test additionally needs valid
gateway credentials. Do not replace blocked Docker checks with host execution.

Next: pin image/package artifacts by digest/hash, then add a real external benchmark
adapter and PostgreSQL repository when needed. Sub2api dashboard integration,
model synchronization, gpt-auto routing changes, distributed scheduling, and
public leaderboards remain outside this phase.

## Phase 1.5 grading integrity and recovery checks

```bash
# After the pinned virtualenv install and both sandbox/controller builds:
SWE_DOCKER_TESTS=1 python -m unittest discover -s tests -p test_remediation.py -v
# Exact original F-01 attack (requires tests on the import path):
PYTHONPATH=tests SWE_DOCKER_TESTS=1 python -m unittest \
  test_remediation.GradingIntegrityTests.test_original_f01_exploit -v
```

Terminal state and verdict are committed atomically. A completed successful
repair is true, a completed failed assertion or rejected patch is false, and
failed/interrupted/timed-out/cancelled runs have null resolution. Recovery keeps
usage and observed test diagnostics while removing incomplete verdict authority.
Terminal results are immutable; expired leases and stale metric/patch/state
writes are rejected. Retries create new child identities. Legacy stored results
are not regraded or silently rewritten: results produced by the old marker-based
grader must not be treated as integrity-verified. Use fresh corrected runs.

## Phase 2 SWE Evaluation Center

Version 0.2.0 adds an independent Chinese administration dashboard, durable
bounded batch experiments, provenance-aware comparisons, server-side read-only
sub2api metadata mapping and an authenticated informational shadow-router export.
The accepted grading-v2 candidate/controller boundary remains in place.

Start with [Phase 2 deployment](PHASE2_DEPLOYMENT_GUIDE.md),
[architecture](PHASE2_ARCHITECTURE.md), [implementation](PHASE2_IMPLEMENTATION_REPORT.md)
and [acceptance evidence](PHASE2_ACCEPTANCE_REPORT.md). The frontend uses React,
TypeScript and Vite: `cd frontend && npm ci && npm test && npm run build`.
Docker service builds include assets automatically. Use a separate console
password hash; the browser never needs the API administrator bearer token.

Do not edit a checkout bind-mounted into an existing auto-reloading service while
expecting deployment isolation. Inspect mounts and reload configuration first;
use a separate checkout/build context. The Phase 2 audit records an unintended
reload/schema initialization in the pre-existing development service caused by
missing that baseline check. No sub2api service or routing configuration was
changed. Live sub2api federation/metadata integration remains explicitly blocked
pending an authorized compatible staging environment.

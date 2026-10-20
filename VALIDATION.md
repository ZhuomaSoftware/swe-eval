# Implementation validation

Validation performed on 2026-10-20 in the provided macOS workspace.

## Executed

- Located bundled Python **3.12.14**; system `python3` is 3.9.6 and is unsuitable.
- Created an isolated development virtualenv with access to bundled packages.
  The available Pydantic is **2.14.1**, not the pinned deployment version 2.11.7.
- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`:
  **55 discovered, 44 passed, 11 explicitly skipped**, no failures after fixing a
  log-pagination test assertion. Five skips require FastAPI/HTTPX; five require
  Docker and prebuilt images; one is the installed-mini API contract check.
- Offline checks cover model validation/capabilities/identity, usage and budgets,
  pricing, unknown usage, atomic claims, state transitions, cancellation intent,
  interrupted-worker recovery, log/patch persistence and redaction, source archive
  isolation, sandbox policy arguments, output/time bounds, and trusted baseline
  hashing. A real temporary Git repository confirmed the exact fixture commit
  `180a5be07e3c5fb60d5759748a32a77e80566e85` and application of the known repair.
  Fixture Python and hidden tests were **not executed on the host**.
- Compiled service Python modules successfully.
- Parsed Compose and CI YAML successfully with the system YAML parser after
  fixing quoting of the Compose security option. Docker Compose's semantic
  configuration validation is still blocked by the missing Docker CLI.
- Built `independent_swe_eval-0.1.0-py3-none-any.whl` using
  `python -m pip wheel --no-build-isolation --no-deps .`; inspected its members to
  confirm source fixture, task manifest, known repair, and hidden grader were
  packaged.
- `PYTHONPATH=src .venv/bin/python -m swe_eval.cli init-db`: initialized schema 1.
- `... swe_eval.cli doctor`: found two configured model profiles, one local task;
  reported mini and Docker unavailable, exited nonzero.
- `... swe_eval.cli verify-fixture`: refused to start because Docker is absent;
  no repository code ran and no fixture verdict was fabricated.

## Blocked checks — not a full end-to-end validation

- The shell cannot resolve/access PyPI. Installing FastAPI, Uvicorn, HTTPX, and
  mini-SWE-agent failed. Their deployment pins/import closure could not be tested.
- Docker CLI/daemon is absent. Image builds, known-good/unchanged hidden test
  execution, real sandbox limits, cleanup/recovery against a daemon, and the
  installed mini agent's Docker workflow remain unverified.
- Tagged upstream mini 2.4.6 source was inspected through the web. The code checks
  the **actual installed** package signature/config/version at runtime. That
  runtime check has not succeeded here because mini is not installed.
- `... swe_eval.cli serve --host 127.0.0.1 --port 8000` failed with
  `ModuleNotFoundError` because Uvicorn is absent. API startup, `/health`, and
  HTTP API tests remain unverified without the API packages.
- No model API credentials were supplied/available in the environment. Live
  gateway inference, usage compatibility, and a real model's repair remain
  unverified. No live model score is reported.

## Reproduce remaining checks

Use the installation and image-build commands in README, then run:

```bash
SWE_DOCKER_TESTS=1 python -m unittest discover -s tests -v
swe-eval verify-fixture
swe-eval doctor
swe-eval serve --host 127.0.0.1 --port 8000
```

With a worker in a separate terminal, submit the documented API evaluation.
Alternatively stop the worker and use:

```bash
swe-eval run --task intervals-001 --model gateway-primary
```

A release should require all installed-dependency/API/Docker checks without
skips, the deterministic good/bad demonstration, and a separately recorded
live-model run. Source implementation is complete enough for those checks;
this environment does **not** establish that all acceptance criteria have passed.

## Build/package workflow validation

- Added `build-package.yml`, Python build-tool pins, an explicit sdist manifest,
  the deployment archive validator/assembler, and a Compose override for packaged
  images. Added the requested GitHub repository URL to Python project metadata.
- Parsed the workflow YAML; checked trigger/permission configuration, all 13
  inline shell blocks with `bash -n`, embedded Python with AST parsing, and the
  packaging script. Verified the selected Actions v7 inputs against official
  action definitions.
- Built a real wheel and sdist offline through the available
  `setuptools.build_meta` backend (84.0.0); the network-blocked environment cannot
  install the pinned `build` frontend or deployment backend 80.9.0.
- Ran `python tools/package_release.py`: archive metadata/required fixture and
  deployment contents passed; assembled the deployment tarball and verified all
  SHA-256 checksums. Checked that Git metadata, virtualenvs, runtime data, `.env`,
  and local model configuration are excluded.
- Installed the wheel into a temporary virtualenv and, outside the checkout,
  verified package import, bundled task discovery, repository metadata, and the
  installed `swe-eval init-db` entry point.
- Re-ran the existing suite: 44 passed, 11 skipped with the same missing-dependency
  and Docker limitations described above. No benchmark repository code executed
  on the host.
- Docker image builds and the GitHub-hosted workflow were not run here. The new
  workflow's installed API smoke test and Docker fixture gate remain unverified.
- `git init -b main` was denied (`.git: Operation not permitted`). The workspace
  remains without Git metadata, so the `upstream-repo` remote could not be written
  and the workflow has not been committed or pushed. README includes the exact
  remote configuration commands for a terminal with write access.

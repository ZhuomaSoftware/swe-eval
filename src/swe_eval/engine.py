from __future__ import annotations

import os
import time

from .agent import MiniSWEAgent, verify_mini_api
from .benchmarks.local import LocalBenchmark
from .config import Settings, load_models, resolve_key
from .providers import OpenAICompatibleProvider, ProviderError
from .sandbox import Cancelled, DockerSandbox, ExecutionTimeout, SandboxError
from .schema import Metrics, RunState
from .security import configure_logging
from .service import model_snapshot, repository


class EvaluationEngine:
    def __init__(self, repo, benchmark, profiles, settings, *, sandbox_factory=DockerSandbox,
                 agent=None, provider_factory=OpenAICompatibleProvider):
        self.repo, self.benchmark, self.profiles, self.settings = repo, benchmark, profiles, settings
        self.sandbox_factory, self.agent, self.provider_factory = sandbox_factory, agent or MiniSWEAgent(), provider_factory

    def execute(self, run_id, *, supplied_patch: str | None = None):
        record = self.repo.get(run_id)
        if not record or record["state"] != RunState.PREPARING:
            raise ValueError("only a claimed preparing run can execute")
        started = time.monotonic()
        metrics = Metrics.model_validate(record["metrics"])
        agent_sandbox = evaluator = None
        task = self.benchmark.get_task(record["task"]["id"])
        profile = self.profiles[record["model"]["id"]]
        duration = min(task.time_limit, profile.max_evaluation_duration)

        def remaining():
            current = self.repo.get(run_id)
            if current["cancel_requested"]:
                raise Cancelled("evaluation cancelled")
            seconds = duration - (time.monotonic() - started)
            if seconds <= 0:
                raise ExecutionTimeout("evaluation duration exceeded")
            return seconds

        def persist():
            metrics.wall_seconds = round(time.monotonic() - started, 4)
            self.repo.save_metrics(run_id, metrics)

        def log(event, message):
            self.repo.log(run_id, event, message)

        def create(*, grading=False):
            return self.sandbox_factory(self.settings.docker_bin, self.repo.service_id, run_id, task,
                                        evaluator=grading, remaining=remaining, check=lambda: remaining())

        try:
            if task.model_dump(mode="json") != record["task"]:
                raise ValueError("task configuration changed after submission; enqueue a new run")
            if model_snapshot(profile) != record["model"]:
                raise ValueError("model configuration changed after submission; enqueue a new run")
            if record["mode"] == "agent" and supplied_patch is not None:
                raise ValueError("agent runs cannot accept supplied patches")
            if record["mode"] != "agent" and supplied_patch is None:
                raise ValueError("patch verification requires an explicit patch")
            source = self.benchmark.source_archive(task)
            metrics.execution_metadata = {"network": "none", "uid": 10001, "runtime": task.runtime.model_dump(),
                                          "base_commit": task.base_commit, "mode": record["mode"]}
            if supplied_patch is None:
                _, _, _, version = verify_mini_api()
                metrics.agent_version = version
                key = resolve_key(profile)
                agent_sandbox = create()
                metrics.execution_metadata["agent_image_digest"] = agent_sandbox.image_digest
                agent_sandbox.prepare(source, task)
                self.repo.transition(run_id, RunState.RUNNING)
                persist()
                provider = self.provider_factory(profile, key, metrics, remaining=remaining, persist=persist)
                status = self.agent.run(task, agent_sandbox, provider, profile, metrics, persist, log, remaining)
                if status == "TimeExceeded":
                    raise ExecutionTimeout("agent duration exceeded")
                patch = agent_sandbox.capture_patch(task.base_commit)
                self.repo.save_patch(run_id, patch)
                agent_sandbox.close()
                agent_sandbox = None
            else:
                patch = supplied_patch
                self.repo.save_patch(run_id, patch)
                log("patch_verification", "Administrator-supplied patch; no model inference; exclude from model scores")
            remaining()
            self.repo.transition(run_id, RunState.EVALUATING)
            evaluator = create(grading=True)
            metrics.execution_metadata["evaluator_image_digest"] = evaluator.image_digest
            evaluator.prepare(source, task)
            metrics.patch_applied = evaluator.apply_patch(patch, task)
            persist()
            if not metrics.patch_applied:
                metrics.resolved = False
                log("patch_rejected", "Patch did not apply cleanly or changed disallowed paths/file modes")
            else:
                log("tests_started", "Executing hidden regression commands in a fresh evaluator container")
                try:
                    results = evaluator.tests(task)
                    metrics.test_exit_codes = [result.returncode for result in results]
                    for result in results:
                        log("test_output", result.output + ("\n[truncated]" if result.truncated else ""))
                    complete = len(results) == len(task.test_commands)
                    marker = any(task.success_marker in result.output for result in results)
                    passed = complete and marker and all(not r.returncode and not r.truncated for r in results)
                    malformed = not results or any(r.truncated for r in results) or (
                        all(not r.returncode for r in results) and not marker) or any(
                            r.returncode in {125, 126, 127} for r in results)
                    metrics.test_result = "passed" if passed else "error" if malformed else "failed"
                    metrics.resolved = passed
                    if malformed:
                        raise SandboxError("hidden test harness did not complete verified execution")
                except ExecutionTimeout:
                    metrics.test_result = "timeout"
                    metrics.test_execution_errors += 1
                    metrics.resolved = False
                    raise
                except SandboxError:
                    metrics.test_result = "error"
                    metrics.test_execution_errors += 1
                    raise
            remaining()
            persist()
            self.repo.transition(run_id, RunState.COMPLETED)
        except Cancelled:
            metrics.resolved = None
            self.repo.transition(run_id, RunState.CANCELLED, "evaluation_cancelled")
        except ExecutionTimeout:
            metrics.resolved = False if metrics.test_result == "timeout" else None
            self.repo.transition(run_id, RunState.TIMEOUT, "evaluation_time_limit_exceeded")
        except Exception as error:
            metrics.resolved = None
            # Only known service-generated messages can be persisted. Do not emit tracebacks
            # or arbitrary third-party exceptions containing request headers/credentials.
            if isinstance(error, (ProviderError, SandboxError, ValueError, RuntimeError)):
                message = str(error)
            else:
                message = "evaluation infrastructure error"
            self.repo.transition(run_id, RunState.FAILED, f"{type(error).__name__}: {message}")
        finally:
            if agent_sandbox:
                agent_sandbox.close()
            if evaluator:
                evaluator.close()
            persist()
        return self.repo.get(run_id)


def execute_run(settings: Settings, run_id: str, supplied_patch: str | None = None):
    """Spawn-safe worker child entry point; the parent enforces an absolute deadline."""
    os.setsid()  # Supervision can terminate Docker CLI descendants along with this child.
    configure_logging()
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(settings.data_dir / "mini-config")
    profiles = load_models(settings.models_file)
    repo = repository(settings, worker=True)
    engine = EvaluationEngine(repo, LocalBenchmark(settings.task_dir), profiles, settings)
    engine.execute(run_id, supplied_patch=supplied_patch)

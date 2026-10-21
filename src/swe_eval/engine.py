from __future__ import annotations

import os
import json
import time

from .agent import MiniSWEAgent, verify_mini_api
from .benchmarks.local import LocalBenchmark
from .config import Settings, load_models, resolve_key
from .providers import OpenAICompatibleProvider, ProviderError
from .sandbox import Cancelled, DockerSandbox, ExecutionTimeout, SandboxError
from .schema import Metrics, RunState
from .security import configure_logging
from .service import model_snapshot, repository
from .diagnostics import assertion_summary


class EvaluationEngine:
    def __init__(self, repo, benchmark, profiles, settings, *, sandbox_factory=DockerSandbox,
                 agent=None, provider_factory=OpenAICompatibleProvider):
        self.repo, self.benchmark, self.profiles, self.settings = repo, benchmark, profiles, settings
        self.sandbox_factory, self.agent, self.provider_factory = sandbox_factory, agent or MiniSWEAgent(), provider_factory

    def execute(self, run_id, *, supplied_patch: str | None = None):
        record = self.repo.get(run_id)
        if record and record["task"].get("benchmark_type")=="official":
            from .official_engine import OfficialEvaluationEngine
            return OfficialEvaluationEngine(self.repo,self.benchmark,self.profiles,self.settings).execute(run_id,supplied_patch=supplied_patch)
        if not record or record["state"] != RunState.PREPARING:
            raise ValueError("only a claimed preparing run can execute")
        started = time.monotonic()
        metrics = Metrics.model_validate(record["metrics"])
        agent_sandbox = evaluator = None
        task = self.benchmark.get_task(record["task"]["id"])
        profile = self.profiles[record["model"]["id"]]
        duration = min(task.time_limit, profile.max_evaluation_duration)
        final_state, final_error = RunState.COMPLETED, None

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
            if record.get('snapshot'):
                effective = record['snapshot']['effective_model']
                # Original configuration must still match; only server-validated
                # effective limits/reasoning are loaded from the immutable snapshot.
                profile = profile.model_copy(update={k: effective[k] for k in (
                    'max_evaluation_duration','max_agent_steps','max_model_calls','max_output_tokens',
                    'max_total_tokens','reasoning_effort')})
                duration = min(task.time_limit, profile.max_evaluation_duration)
                metrics.requested_reasoning_effort = profile.reasoning_effort
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
                key = resolve_key(profile, self.settings)
                self.repo.redact.add(key)
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
                log("tests_started", "Executing independent trusted assertions against isolated candidate operations")
                try:
                    grading = evaluator.tests(task)
                    results, verdict = grading.operations, grading.verdict
                    metrics.test_exit_codes = [result.returncode for result in results]
                    for result in results:
                        log("test_operation", json.dumps({"exit_code": result.returncode, "truncated": result.truncated}))
                    log("trusted_assertions", json.dumps(assertion_summary(verdict)))
                    metrics.execution_metadata["controller_image_digest"] = grading.controller_image_digest
                    metrics.execution_metadata["grading_protocol"] = verdict["protocol"]
                    metrics.assertions_expected = verdict["assertions_expected"]
                    metrics.assertions_executed = verdict["assertions_executed"]
                    metrics.assertions_passed = verdict["assertions_passed"]
                    passed = verdict["passed"]
                    malformed = verdict["execution_errors"] > 0
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
        except Cancelled:
            metrics.resolved = None
            final_state, final_error = RunState.CANCELLED, "evaluation_cancelled"
        except ExecutionTimeout:
            metrics.resolved = None
            final_state, final_error = RunState.TIMEOUT, "evaluation_time_limit_exceeded"
        except Exception as error:
            metrics.resolved = None
            # Only known service-generated messages can be persisted. Do not emit tracebacks
            # or arbitrary third-party exceptions containing request headers/credentials.
            if isinstance(error, (ProviderError, SandboxError, ValueError, RuntimeError)):
                message = str(error)
            else:
                message = "evaluation infrastructure error"
            final_state, final_error = RunState.FAILED, f"{type(error).__name__}: {message}"
        finally:
            if agent_sandbox:
                agent_sandbox.close()
            if evaluator:
                evaluator.close()
            metrics.wall_seconds = round(time.monotonic() - started, 4)
            # Verdict + terminal state commit together. A stale child cannot
            # mutate a row finalized by recovery or a supervisor.
            self.repo.transition(run_id, final_state, final_error, metrics=metrics)
        return self.repo.get(run_id)


def execute_run(settings: Settings, run_id: str, supplied_patch: str | None = None):
    """Spawn-safe worker child entry point; the parent enforces an absolute deadline."""
    os.setsid()  # Supervision can terminate Docker CLI descendants along with this child.
    configure_logging()
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(settings.data_dir / "mini-config")
    repo = repository(settings, worker=True)
    from .management import bound_profiles
    try:profiles = bound_profiles(settings, repo, repo.get(run_id))
    except (ValueError, KeyError):
        repo.transition(run_id, RunState.FAILED, "immutable_configuration_or_credential_unavailable")
        return
    from .benchmarks.official import TaskRegistry
    engine = EvaluationEngine(repo, TaskRegistry(settings), profiles, settings)
    engine.execute(run_id, supplied_patch=supplied_patch)

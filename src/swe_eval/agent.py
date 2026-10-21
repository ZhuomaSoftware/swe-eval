from __future__ import annotations

import importlib.metadata
import inspect
import os
from typing import Protocol

from .providers import ActionFormatError, BudgetExceeded, OpenAICompatibleProvider, parse_action
from .sandbox import SandboxError
from .schema import Metrics, ModelProfile, Task

PINNED_MINI_VERSION = "2.4.6"


def verify_mini_api():
    """Verify the installed package, not an assumed interface or a vendored imitation."""
    os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")
    # mini imports create a config directory; keep it in the dedicated worker's data directory.
    try:
        version = importlib.metadata.version("mini-swe-agent")
    except importlib.metadata.PackageNotFoundError:
        raise RuntimeError("mini-SWE-agent is not installed; install the [agent] extra") from None
    if version != PINNED_MINI_VERSION:
        raise RuntimeError(f"mini-SWE-agent version must be {PINNED_MINI_VERSION}; found {version}")
    from minisweagent.agents.default import AgentConfig, DefaultAgent
    from minisweagent.exceptions import FormatError, LimitsExceeded

    if not {"model", "env"} <= set(inspect.signature(DefaultAgent).parameters):
        raise RuntimeError("unsupported installed mini-SWE-agent constructor")
    if not {"step_limit", "wall_time_limit_seconds", "system_template", "instance_template",
            "cost_limit", "max_consecutive_format_errors", "output_path"} <= set(AgentConfig.model_fields):
        raise RuntimeError("unsupported installed mini-SWE-agent configuration")
    if "task" not in inspect.signature(DefaultAgent.run).parameters:
        raise RuntimeError("unsupported installed mini-SWE-agent run method")
    for method in ("query", "execute_actions", "save"):
        if not callable(getattr(DefaultAgent, method, None)):
            raise RuntimeError("unsupported installed mini-SWE-agent methods")
    return DefaultAgent, FormatError, LimitsExceeded, version


class CodingAgent(Protocol):
    def run(self, task: Task, sandbox, provider: OpenAICompatibleProvider, profile: ModelProfile,
            metrics: Metrics, persist, log, remaining) -> str: ...


def exit_message(status):
    return {"role": "exit", "content": status, "extra": {"exit_status": status, "submission": ""}}


class MiniModel:
    def __init__(self, provider, profile, format_error, limits_exceeded):
        self.provider, self.profile = provider, profile
        self.format_error, self.limits_exceeded = format_error, limits_exceeded

    def query(self, messages):
        try:
            message = self.provider.complete(messages)
        except BudgetExceeded:
            raise self.limits_exceeded(exit_message("LimitsExceeded")) from None
        try:
            action = parse_action(message, self.profile.capabilities.action_format)
        except ActionFormatError as error:
            # A malformed tool call cannot enter the next request without a tool response.
            correction = {"role": "user", "content": str(error)}
            safe_message = {"role": "assistant", "content": str(message.get("content") or "Invalid action format")}
            raise self.format_error(safe_message, correction) from None
        message["extra"] = {"actions": [action], "cost": 0.0}
        return message

    @staticmethod
    def format_message(**kwargs):
        return kwargs

    def format_observation_messages(self, message, outputs, template_vars=None):
        if outputs and outputs[0].get("submitted"):
            return [exit_message("Submitted")]
        output = outputs[0]
        content = f"Exit code: {output['returncode']}\n{output['output']}"
        if output.get("truncated"):
            content += "\n[output truncated]"
        if self.profile.capabilities.action_format == "native_tools":
            action = message["extra"]["actions"][0]
            return [{"role": "tool", "tool_call_id": action["tool_call_id"], "content": content}]
        return [{"role": "user", "content": content}]

    def get_template_vars(self, **kwargs):
        return {}

    def serialize(self):
        return {}  # Credential-bearing provider configuration must never be serialized.


class AgentEnvironment:
    def __init__(self, sandbox, task, profile, metrics, persist, log, limits_exceeded, check):
        self.sandbox, self.task, self.profile = sandbox, task, profile
        self.metrics, self.persist, self.log = metrics, persist, log
        self.limits_exceeded, self.check = limits_exceeded, check

    def execute(self, action, cwd=""):
        self.check()
        if action.get("submit"):
            return {"submitted": True}
        if self.metrics.agent_steps >= self.profile.max_agent_steps:
            raise self.limits_exceeded(exit_message("LimitsExceeded"))
        self.metrics.agent_steps += 1
        self.persist()
        self.log("agent_command", action["command"])
        try:
            result = self.sandbox.command(action["command"], self.task.command_timeout)
            if result.returncode:
                self.metrics.agent_execution_errors += 1
            self.log("agent_output", result.output + ("\n[truncated]" if result.truncated else ""))
            return {"returncode": result.returncode, "output": result.output[:32768], "truncated": result.truncated}
        except Exception:
            self.metrics.agent_execution_errors += 1
            raise
        finally:
            self.persist()

    def get_template_vars(self, **kwargs):
        return {"cwd": "/workspace"}

    def serialize(self):
        return {}


class MiniSWEAgent:
    def run(self, task, sandbox, provider, profile, metrics, persist, log, remaining):
        agent_class, format_error, limits_exceeded, version = verify_mini_api()
        metrics.agent_version = version
        persist()
        context = sandbox.command(
            "git ls-files | head -100; printf '\\nREADME:\\n'; "
            "if [ -f README.md ]; then head -c 12000 README.md; fi", min(task.command_timeout, remaining()))
        if context.returncode:
            raise SandboxError("failed to collect initial repository context")
        log("repository_context", context.output[:16000])
        text_format = ("Respond with exactly one fenced ```bash command block per turn. "
                       "When finished respond with exactly SUBMIT.")
        native_format = "Use exactly one bash function call per turn. Call submit when finished."
        system = ("You are repairing a software repository. The repository is in /workspace. "
                  "Inspect its files and tests, implement the issue, and run available tests. "
                  "Each command starts in /workspace; shell state does not persist between actions. "
                  "Network access and dependency installation are unavailable. "
                  "Your changes on disk will be evaluated in a separate clean workspace. " +
                  (text_format if profile.capabilities.action_format == "text" else native_format))
        model = MiniModel(provider, profile, format_error, limits_exceeded)
        env = AgentEnvironment(sandbox, task, profile, metrics, persist, log, limits_exceeded,
                               lambda: remaining())
        agent = agent_class(model, env, system_template=system,
                            instance_template="{{ task }}", step_limit=profile.max_model_calls,
                            wall_time_limit_seconds=max(1, int(remaining())), cost_limit=0,
                            max_consecutive_format_errors=3, output_path=None)
        official=getattr(task,"benchmark_type",None)=="official"
        policy=("All repository source paths are allowed, but do not change tests, test runner or build configuration, .git, symlinks, or grading files.\n" if official else "Only these repository paths may be changed in the submitted patch:\n"+"\n".join(f"- {path}" for path in task.allowed_patch_paths)+"\n")
        result = agent.run(task=f"Issue:\n{task.issue}\n\nBase commit: {task.base_commit}\n"
                                "Patch constraints (required):\n"
                                + policy +
                                "Do not change or add other paths. You may inspect and run existing tests; "
                                "leave files outside the allowed paths unchanged before submitting.\n\n"
                                f"Repository context (tracked files and README):\n{context.output[:16000]}\n\n"
                                "Begin by inspecting the repository.")
        # Only a safe summary enters persistence; raw trajectories can contain upstream data.
        status = result.get("exit_status", "Unknown")
        metrics.agent_exit_status = status
        log("agent_finished", status)
        persist()
        return status

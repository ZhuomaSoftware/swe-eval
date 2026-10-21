from __future__ import annotations

from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


ACTIVE = {RunState.PREPARING, RunState.RUNNING, RunState.EVALUATING}
TERMINAL = {RunState.COMPLETED, RunState.FAILED, RunState.TIMEOUT, RunState.CANCELLED}
TRANSITIONS = {
    RunState.QUEUED: {RunState.PREPARING, RunState.CANCELLED},
    RunState.PREPARING: {RunState.RUNNING, RunState.EVALUATING, *TERMINAL - {RunState.COMPLETED}},
    RunState.RUNNING: {RunState.EVALUATING, *TERMINAL - {RunState.COMPLETED}},
    RunState.EVALUATING: TERMINAL,
}


class Capabilities(StrictModel):
    protocol: Literal["chat_completions"] = "chat_completions"
    action_format: Literal["text", "native_tools"] = "text"
    reasoning_effort: bool = False
    output_token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class Pricing(StrictModel):
    input_per_million: float = Field(ge=0, allow_inf_nan=False)
    output_per_million: float = Field(ge=0, allow_inf_nan=False)
    currency: Literal["USD", "CNY", "EUR"] = "USD"


class ModelProfile(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    upstream_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    model_id: str = Field(min_length=1, max_length=200)
    data_origin: Literal["live", "local_stub", "audit", "unverified"] = "unverified"
    upstream_verified: bool = False
    base_url: str
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    api_key_file: str | None = None
    allow_no_api_key: bool = False
    allow_http: bool = False
    capabilities: Capabilities = Field(default_factory=Capabilities)
    reasoning_effort: str | None = Field(default=None, min_length=1, max_length=30)
    request_timeout: float = Field(default=60, gt=0, le=600)
    max_output_tokens: int = Field(default=4096, gt=0, le=100000)
    max_agent_steps: int = Field(default=30, gt=0, le=1000)
    max_model_calls: int = Field(default=35, gt=0, le=1000)
    max_evaluation_duration: int = Field(default=600, gt=0, le=86400)
    max_total_tokens: int | None = Field(default=None, gt=0)
    max_context_chars: int = Field(default=160000, ge=1000, le=2000000)
    pricing: Pricing | None = None

    provider_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    provider_revision: int | None = Field(default=None, ge=1)
    configuration_revision: int | None = Field(default=None, ge=1)
    credential_version: int | None = Field(default=None, ge=1)
    display_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_profile(self):
        url = urlsplit(self.base_url)
        if url.scheme not in {"https", "http"} or not url.hostname:
            raise ValueError("base_url must be an HTTP(S) URL")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url must not contain credentials, query, or fragment")
        if url.scheme == "http" and not self.allow_http:
            raise ValueError("HTTP endpoints require allow_http=true")
        if self.api_key_env and self.api_key_file:
            raise ValueError("choose api_key_env or api_key_file")
        if not (self.api_key_env or self.api_key_file or self.allow_no_api_key or (self.provider_id and self.credential_version)):
            raise ValueError("configure a server-side API key reference")
        if self.reasoning_effort and not self.capabilities.reasoning_effort:
            raise ValueError("reasoning_effort requested but capability is disabled")
        return self

    def public(self) -> dict:
        # Keep endpoint routing, credential references, and secret values server-side.
        excluded = {"api_key_env", "api_key_file", "base_url"}
        if self.provider_id is None:
            excluded.update({"provider_id", "provider_revision", "configuration_revision", "credential_version", "display_name"})
        return self.model_dump(exclude=excluded)


class RepositorySource(StrictModel):
    kind: Literal["snapshot", "git_bundle"] = "snapshot"
    path: str


class Runtime(StrictModel):
    agent_image: str = "swe-eval-sandbox:phase1"
    evaluator_image: str = "swe-eval-grader:phase1"
    cpus: float = Field(default=1, gt=0, le=8)
    memory_mb: int = Field(default=512, ge=64, le=8192)
    pids: int = Field(default=64, ge=16, le=512)
    workspace_mb: int = Field(default=256, ge=16, le=4096)
    requirements: list[str] = Field(default_factory=lambda: ["python3", "git", "bash", "coreutils"])


class Task(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    benchmark: str
    dataset_version: str
    repository: RepositorySource
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    issue: str = Field(min_length=1)
    test_commands: list[list[str]] = Field(min_length=1)
    grading_protocol: Literal["isolated_operations_v2"] = "isolated_operations_v2"
    success_marker: str = Field(min_length=1)
    allowed_patch_paths: list[str] = Field(min_length=1)
    runtime: Runtime = Field(default_factory=Runtime)
    command_timeout: int = Field(default=30, gt=0, le=600)
    test_timeout: int = Field(default=30, gt=0, le=3600)
    time_limit: int = Field(default=600, gt=0, le=86400)

    @model_validator(mode="after")
    def validate_commands(self):
        if any(not command or any("\x00" in arg for arg in command) for command in self.test_commands):
            raise ValueError("test commands must be nonempty argv arrays")
        if any(not path or path.startswith("/") or ".." in path.split("/") or
               ".git" in path.split("/") for path in self.allowed_patch_paths):
            raise ValueError("patch paths must be relative repository paths")
        return self

    def public(self) -> dict:
        return self.model_dump(exclude={"test_commands", "success_marker"})


class Metrics(StrictModel):
    resolved: bool | None = None
    patch_applied: bool | None = None
    test_result: Literal["not_run", "passed", "failed", "error", "timeout"] = "not_run"
    test_exit_codes: list[int] = Field(default_factory=list)
    assertions_expected: int | None = None
    assertions_executed: int | None = None
    assertions_passed: int | None = None
    agent_steps: int = 0
    model_requests: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    usage_complete: bool = False
    cost: float | None = None
    currency: str | None = None
    wall_seconds: float = 0
    api_errors: int = 0
    agent_execution_errors: int = 0
    test_execution_errors: int = 0
    model_id: str | None = None
    model_profile_id: str | None = None
    upstream_id: str | None = None
    requested_reasoning_effort: str | None = None
    agent_version: str | None = None
    benchmark_version: str | None = None
    agent_exit_status: str | None = None
    execution_metadata: dict = Field(default_factory=dict)


class CreateRun(StrictModel):
    task_id: str
    model_profile_id: str

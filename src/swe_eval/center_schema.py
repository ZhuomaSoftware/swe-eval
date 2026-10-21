from typing import Literal
from pydantic import Field, model_validator
from .schema import StrictModel


class RunLimits(StrictModel):
    timeout: int = Field(default=300, ge=1, le=3600)
    steps: int = Field(default=12, ge=1, le=100)
    requests: int = Field(default=15, ge=1, le=100)
    output_tokens: int = Field(default=2048, ge=1, le=16000)
    total_tokens: int = Field(default=30000, ge=1, le=1000000)


class BatchSubmission(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    task_ids: list[str] = Field(min_length=1, max_length=100)
    model_profile_ids: list[str] = Field(min_length=1, max_length=30)
    attempts: int = Field(default=1, ge=1, le=5)
    reasoning: dict[str, str | None] = Field(default_factory=dict)
    limits: RunLimits = Field(default_factory=RunLimits)
    max_duration: int = Field(default=3600, ge=1, le=86400)
    max_requests: int = Field(default=100, ge=1, le=10000)
    spending_limit: float | None = Field(default=None, gt=0)
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.task_ids)) != len(self.task_ids) or len(set(self.model_profile_ids)) != len(self.model_profile_ids):
            raise ValueError('task and profile selections must be unique')
        if set(self.reasoning) - set(self.model_profile_ids):
            raise ValueError('reasoning must reference a selected profile')
        if self.spending_limit is not None:
            raise ValueError('monetary enforcement unavailable: use request, token and time limits')
        return self


class Login(StrictModel):
    password: str = Field(min_length=1, max_length=512)

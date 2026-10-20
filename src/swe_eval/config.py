from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .schema import ModelProfile


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    models_file: Path
    admin_token: str = field(default="", repr=False)
    task_dir: Path | None = None
    docker_bin: str = "docker"
    lease_seconds: int = 90

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_dir=Path(os.getenv("SWE_DATA_DIR", "data")).resolve(),
            models_file=Path(os.getenv("SWE_MODELS_FILE", "config/models.json")).resolve(),
            admin_token=os.getenv("SWE_ADMIN_TOKEN", ""),
            task_dir=Path(os.environ["SWE_TASK_DIR"]).resolve() if os.getenv("SWE_TASK_DIR") else None,
            docker_bin=os.getenv("SWE_DOCKER_BIN", "docker"),
        )

    @property
    def database(self) -> Path:
        return self.data_dir / "runs.sqlite3"


def load_models(path: Path) -> dict[str, ModelProfile]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError("models file must be a JSON array")
    profiles = [ModelProfile.model_validate(value) for value in raw]
    if len({p.id for p in profiles}) != len(profiles):
        raise ValueError("duplicate model profile IDs")
    return {p.id: p for p in profiles}


def resolve_key(profile: ModelProfile) -> str:
    if profile.api_key_env:
        value = os.getenv(profile.api_key_env, "")
    elif profile.api_key_file:
        value = Path(profile.api_key_file).read_text().strip()
    else:
        value = ""
    if not value and not profile.allow_no_api_key:
        raise ValueError("model API key reference is empty or unavailable")
    if "\n" in value or "\r" in value:
        raise ValueError("invalid API key")
    return value

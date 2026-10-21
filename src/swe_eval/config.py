from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from pydantic import ValidationError

from .schema import ModelProfile


class ConfigurationError(ValueError):
    """Only fixed, secret-free administrator guidance may be placed here."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    models_file: Path
    admin_token: str = field(default="", repr=False)
    task_dir: Path | None = None
    docker_bin: str = "docker"
    lease_seconds: int = 90

    ui_password_hash: str = field(default="", repr=False)
    cookie_secure: bool = True
    public_origin: str = "http://127.0.0.1:8000"
    max_batch_runs: int = 100
    max_pending_runs: int = 200
    max_batch_duration: int = 86400
    max_batch_requests: int = 10000
    shadow_token: str = field(default="", repr=False)
    integration_file: Path | None = None

    def __post_init__(self):
        for field_name, low, high in [('max_batch_runs',1,10000),('max_pending_runs',1,100000),
                                      ('max_batch_duration',1,86400),('max_batch_requests',1,10000)]:
            if not low <= getattr(self,field_name) <= high:
                raise ConfigurationError(f"SWE_{field_name.upper()}: configure an integer in {low}..{high}")
        if self.ui_password_hash:
            import re
            if not re.fullmatch(r'pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}',self.ui_password_hash):
                raise ConfigurationError('SWE_UI_PASSWORD_HASH: generate a PBKDF2 hash using swe_eval.sessions.password_hash')
        from urllib.parse import urlsplit
        origin=urlsplit(self.public_origin)
        if origin.scheme not in ('http','https') or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path:
            raise ConfigurationError('SWE_PUBLIC_ORIGIN: configure the exact HTTP(S) origin without a path')

    @classmethod
    def from_env(cls) -> Settings:
        def integer(name, default):
            try:
                return int(os.getenv(name,str(default)))
            except ValueError:
                raise ConfigurationError(f"{name}: configure an integer within the documented limits") from None
        return cls(
            data_dir=Path(os.getenv("SWE_DATA_DIR", "data")).resolve(),
            models_file=Path(os.getenv("SWE_MODELS_FILE", "config/models.json")).resolve(),
            admin_token=os.getenv("SWE_ADMIN_TOKEN", ""),
            task_dir=Path(os.environ["SWE_TASK_DIR"]).resolve() if os.getenv("SWE_TASK_DIR") else None,
            ui_password_hash=os.getenv("SWE_UI_PASSWORD_HASH", ""),
            cookie_secure=os.getenv("SWE_COOKIE_SECURE", "true").lower() != "false",
            public_origin=os.getenv("SWE_PUBLIC_ORIGIN", "http://127.0.0.1:8000").rstrip("/"),
            max_batch_runs=integer("SWE_MAX_BATCH_RUNS",100),
            max_pending_runs=integer("SWE_MAX_PENDING_RUNS",200),
            max_batch_duration=integer("SWE_MAX_BATCH_DURATION",86400),
            max_batch_requests=integer("SWE_MAX_BATCH_REQUESTS",10000),
            shadow_token=os.getenv("SWE_SHADOW_TOKEN", ""),
            integration_file=Path(os.environ["SWE_INTEGRATION_FILE"]) if os.getenv("SWE_INTEGRATION_FILE") else None,
            docker_bin=os.getenv("SWE_DOCKER_BIN", "docker"),
        )

    @property
    def database(self) -> Path:
        return self.data_dir / "runs.sqlite3"


def load_models(path: Path) -> dict[str, ModelProfile]:
    try:
        raw = json.loads(path.read_text())
    except OSError:
        raise ConfigurationError("SWE_MODELS_FILE: provide a readable server-side model JSON file") from None
    except ValueError:
        raise ConfigurationError("SWE_MODELS_FILE: invalid JSON; provide an array of model profiles") from None
    if not isinstance(raw, list):
        raise ConfigurationError("SWE_MODELS_FILE: models file must be a JSON array")
    profiles = []
    for index, value in enumerate(raw):
        try:
            profiles.append(ModelProfile.model_validate(value))
        except ValidationError as error:
            # Locations are schema field names only, never raw input or ctx.
            item = error.errors()[0]
            fields = [str(part) for part in item["loc"] if part in ModelProfile.model_fields]
            location = ".".join(fields) or "profile/capabilities"
            raise ConfigurationError(f"SWE_MODELS_FILE: model[{index}].{location} is invalid ({item['type']}); check field limits and capability settings in config/models.json") from None
    if len({p.id for p in profiles}) != len(profiles):
        raise ConfigurationError("SWE_MODELS_FILE: duplicate model profile IDs; assign unique id values")
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

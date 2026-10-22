from __future__ import annotations

import hashlib
from .config import Settings, load_models, resolve_key
from .schema import ModelProfile
from .security import Redactor
from .storage import SQLiteRepository


def model_snapshot(profile: ModelProfile):
    snapshot = profile.public()
    # Compare immutable launch configuration without persisting endpoint URLs or credentials.
    snapshot["configuration_hash"] = hashlib.sha256(profile.model_dump_json(exclude={"provider_id","provider_revision","configuration_revision","credential_version","display_name"} if profile.provider_id is None else set()).encode()).hexdigest()
    return snapshot


def repository(settings: Settings, *, worker=False):
    secrets = [settings.admin_token]
    if worker:
        for profile in load_models(settings.models_file).values():
            try:
                secrets.append(resolve_key(profile))
            except (ValueError, OSError):
                pass
    repo = SQLiteRepository(settings.database, Redactor(secrets))
    repo.initialize()
    repo.recovery_settings=settings
    return repo


def enqueue(repo, benchmark, profiles, task_id, profile_id, *, mode="agent", parent_id=None, max_pending=None):
    task, profile = benchmark.get_task(task_id), profiles[profile_id]
    if getattr(task,"benchmark_type",None)=="official" and not task.environment_ready:
        raise ValueError("official task must pass environment, gold and negative validation before execution")
    from .management import ConfigurationRepository
    if ConfigurationRepository(repo, None).dataset_archived(task.dataset_version):
        raise ValueError("dataset revision is archived")
    from .center import snapshot
    return repo.create(task.model_dump(mode="json"), model_snapshot(profile), mode=mode, parent_id=parent_id,
                       snapshot=snapshot(task, profile), max_pending=max_pending)


def public_run(record):
    value = dict(record)
    value.pop("worker_id", None)
    task = dict(value["task"])
    task.pop("test_commands", None)
    task.pop("success_marker", None)
    value["task"] = task
    from .diagnostics import public_metadata
    value["metrics"] = dict(value["metrics"], execution_metadata=public_metadata(value["metrics"].get("execution_metadata", {})))
    return value

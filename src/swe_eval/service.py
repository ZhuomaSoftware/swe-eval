from __future__ import annotations

import hashlib
from .config import Settings, load_models, resolve_key
from .schema import ModelProfile
from .security import Redactor
from .storage import SQLiteRepository


def model_snapshot(profile: ModelProfile):
    snapshot = profile.public()
    # Compare immutable launch configuration without persisting endpoint URLs or credentials.
    snapshot["configuration_hash"] = hashlib.sha256(profile.model_dump_json().encode()).hexdigest()
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
    return repo


def enqueue(repo, benchmark, profiles, task_id, profile_id, *, mode="agent", parent_id=None):
    task, profile = benchmark.get_task(task_id), profiles[profile_id]
    return repo.create(task.model_dump(mode="json"), model_snapshot(profile), mode=mode, parent_id=parent_id)


def public_run(record):
    value = dict(record)
    value.pop("worker_id", None)
    task = dict(value["task"])
    task.pop("test_commands", None)
    task.pop("success_marker", None)
    value["task"] = task
    return value

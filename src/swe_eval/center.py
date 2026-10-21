"""Orchestration and immutable experiment provenance; the Phase 1 queue remains authoritative."""
import hashlib
import json
from pathlib import Path
from pydantic import ValidationError
from .service import model_snapshot
from .schema import ModelProfile

PROTOCOL = 'swe-eval-grading-v2'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def harness_revision():
    root = Path(__file__).parent
    files = ['agent.py', 'providers.py', 'engine.py', 'sandbox.py', 'candidate_runner.py',
             'benchmarks/data/intervals/hidden/grade.py']
    return digest({p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files})


def effective_profile(profile, limits=None, reasoning=None, override=False):
    data = profile.model_dump()
    if override:
        if reasoning and not profile.capabilities.reasoning_effort:
            raise ValueError('selected profile does not support reasoning effort')
        data['reasoning_effort'] = reasoning
    if limits:
        for field, value in [('max_evaluation_duration', limits.timeout), ('max_agent_steps', limits.steps),
                             ('max_model_calls', limits.requests), ('max_output_tokens', limits.output_tokens)]:
            data[field] = min(data[field], value)
        data['max_total_tokens'] = min(profile.max_total_tokens or limits.total_tokens, limits.total_tokens)
    try:
        return ModelProfile.model_validate(data)
    except ValidationError:
        raise ValueError("invalid effective profile limits or reasoning setting") from None


def snapshot(task, profile, effective=None):
    effective = effective or profile
    official=getattr(task,"benchmark_type",None)=="official"
    from .official_engine import stable_task
    if official:
        root=Path(__file__).parent
        harness=digest({"upstream":task.harness_commit,"version":task.harness_version,**{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ("official_engine.py","official_harness.py","swebench_bridge.py","benchmarks/official_sandbox.py")}})
    else:harness=harness_revision()
    return dict(schema_version=1, grading_protocol=task.grading_protocol if official else PROTOCOL, harness_revision=harness,
                **({"subset":task.subset,"agent_version":"2.4.6","official_harness_version":task.harness_version,"official_harness_commit":task.harness_commit,"environment_image_digest":task.environment_image_digest} if official else {}),
                task_fingerprint=digest(stable_task(task) if official else task.model_dump(mode='json')),
                configuration_fingerprint=model_snapshot(profile)['configuration_hash'],
                runtime_fingerprint=digest({'profile': effective.public(), 'configuration':model_snapshot(profile)['configuration_hash'], 'runtime': task.runtime.model_dump()}),
                effective_model=effective.public(), data_origin=profile.data_origin,
                upstream_verified=profile.upstream_verified,
                endpoint_identity=hashlib.sha256(profile.base_url.rstrip('/').encode()).hexdigest()[:16])


def submit_batch(repo, benchmark, profiles, body, settings):
    count = len(body.task_ids) * len(body.model_profile_ids) * body.attempts
    if body.max_duration > settings.max_batch_duration or body.max_requests > settings.max_batch_requests:
        raise ValueError('batch duration or request allowance exceeds server limit')
    if count > settings.max_batch_runs:
        raise ValueError('batch exceeds SWE_MAX_BATCH_RUNS')
    tasks = [benchmark.get_task(x) for x in body.task_ids]
    if any(getattr(task,"benchmark_type",None)=="official" and not task.environment_ready for task in tasks):
        raise ValueError("official tasks must pass environment, gold and negative validation before batch submission")
    selected = [profiles[x] for x in body.model_profile_ids]
    specs = []
    for task in tasks:
        for profile in selected:
            effective = effective_profile(profile, body.limits, body.reasoning.get(profile.id), profile.id in body.reasoning)
            for attempt in range(1, body.attempts + 1):
                specs.append((task.model_dump(mode='json'), model_snapshot(profile), snapshot(task, profile, effective), attempt))
    # Reserve each attempt's complete call allowance. No usage estimate is used as a hard budget.
    reserved = sum(x[2]['effective_model']['max_model_calls'] for x in specs)
    if reserved > body.max_requests:
        raise ValueError('reserved per-run request allowances exceed batch max_requests')
    return repo.create_batch(body.model_dump(mode='json'), specs, settings.max_pending_runs, reserved)

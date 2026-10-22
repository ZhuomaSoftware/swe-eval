"""Orchestration and immutable experiment provenance; the Phase 1 queue remains authoritative."""
import hashlib
import json
from pathlib import Path
from pydantic import ValidationError
from .service import model_snapshot
from .schema import ModelProfile

PROTOCOL = 'swe-eval-grading-v2'


class BatchRequestBudgetError(ValueError):
    """Only validated integer limits enter this safe administrator message."""
    def __init__(self, required, configured):
        super().__init__(f'批次总请求预留不足：至少需要 {int(required)} 次，当前为 {int(configured)} 次。'
                         '预留按题目数 × 尝试次数 × 各模型有效请求上限之和计算，启用恢复时另含恢复预留；有效上限取实验预算与模型配置的较小值。')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def harness_revision():
    root = Path(__file__).parent
    files = ['agent.py', 'providers.py', 'provider_errors.py', 'retries.py', 'outbound.py', 'engine.py', 'sandbox.py', 'candidate_runner.py',
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
        harness=digest({"upstream":task.harness_commit,"version":task.harness_version,**{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ("official_engine.py","official_harness.py","swebench_bridge.py","benchmarks/official_sandbox.py","providers.py","provider_errors.py","retries.py","outbound.py")}})
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
    # Optional management metadata must not change Phase 2.6 request hashes.
    request_configuration = body.model_dump(mode='json', exclude=({'subset_id','subset_revision'} if body.subset_id is None else set()) | {k for k in ('api_retry','run_recovery') if getattr(body,k) is None})
    from .retries import retry_schema_ready
    if (body.api_retry or body.run_recovery) and not retry_schema_ready(repo):raise ValueError('explicit migrate-retries required before retry-enabled admission')
    with repo.connect() as db:
        prior = db.execute('SELECT id,request_hash FROM evaluation_batches WHERE idempotency_key=?',(body.idempotency_key,)).fetchone()
    if prior:
        if prior['request_hash'] != digest(request_configuration):
            from .storage import Conflict
            raise Conflict('idempotency key already used for different configuration')
        return repo.batch(prior['id'])
    count = len(body.task_ids) * len(body.model_profile_ids) * body.attempts
    if body.max_duration > settings.max_batch_duration or body.max_requests > settings.max_batch_requests:
        raise ValueError('batch duration or request allowance exceeds server limit')
    recovery_multiplier = 1 + (body.run_recovery.max_recoveries if body.run_recovery and body.run_recovery.enabled else 0)
    if count * recovery_multiplier > settings.max_batch_runs:
        raise ValueError('batch exceeds SWE_MAX_BATCH_RUNS')
    tasks = [benchmark.get_task(x) for x in body.task_ids]
    if any(getattr(task,"benchmark_type",None)=="official" and not task.environment_ready for task in tasks):
        raise ValueError("official tasks must pass environment, gold and negative validation before batch submission")
    from .management import ConfigurationRepository
    configuration=ConfigurationRepository(repo,settings)
    if any(configuration.dataset_archived(task.dataset_version) for task in tasks):raise ValueError('dataset revision is archived')
    subset=None
    if body.subset_id:
        subset=configuration.subset(body.subset_id,benchmark,body.subset_revision)
        if subset['archived'] or set(subset['task_ids'])!=set(body.task_ids):raise ValueError('subset membership mismatch or archived subset')
    selected = [profiles[x] for x in body.model_profile_ids]
    specs = []
    for task in tasks:
        for profile in selected:
            effective = effective_profile(profile, body.limits, body.reasoning.get(profile.id), profile.id in body.reasoning)
            for attempt in range(1, body.attempts + 1):
                provenance=snapshot(task, profile, effective)
                if body.api_retry:provenance['api_retry']=body.api_retry.model_dump()
                if body.run_recovery:provenance['run_recovery']=body.run_recovery.model_dump()
                if body.api_retry or body.run_recovery:provenance['runtime_fingerprint']=digest({'base':provenance['runtime_fingerprint'],'api_retry':provenance.get('api_retry'),'run_recovery':provenance.get('run_recovery')})
                if subset:provenance['selected_subset']={'id':subset['id'],'revision':subset['revision'],'fingerprint':subset['fingerprint']}
                specs.append((task.model_dump(mode='json'), model_snapshot(profile), provenance, attempt))
    # Reserve each attempt's complete call allowance. No usage estimate is used as a hard budget.
    reserved = sum(x[2]['effective_model']['max_model_calls'] for x in specs) * recovery_multiplier
    if reserved > body.max_requests:
        raise BatchRequestBudgetError(reserved,body.max_requests)
    return repo.create_batch(request_configuration, specs, settings.max_pending_runs, reserved)

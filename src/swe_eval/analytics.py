"""Explicit denominators, matched coverage and provenance; never infer unknown usage/cost."""
from collections import Counter, defaultdict
import math
import time
from .center import PROTOCOL, digest
from .benchmarks.official import PROTOCOL as OFFICIAL_PROTOCOL, HARNESS_VERSION, HARNESS_COMMIT, DATASET

METHODOLOGY = {
    'version':'swe-comparison-v1', 'grading_protocol':PROTOCOL,
    'valid_evaluation':'completed agent attempt: isolated v2 assertions/patch rejection, or pinned official harness report/source-policy rejection; empty official predictions are skipped and excluded from valid evaluation denominator',
    'resolved_rate':'resolved / valid evaluations', 'attempt_success_rate':'resolved / all included attempts, including infrastructure failures',
    'pass_at_1':'micro-average over versioned task/full-configuration pairs: earliest parentless attempt numbered 1 (or unnumbered); retries and attempt >1 excluded; infrastructure failure counts as not successful',
    'trusted_origin':'live only for trusted overview/success/shadow; non-live comparison groups are explicitly diagnostic',
    'freshness':'evaluated_at from valid completed live evidence only; last_attempted_at is separate; generated_at is export time',
    'percentiles':'linear interpolation at (n-1)*p',
    'cost':'unknown if any included attempt cost is unknown; known subtotal shown separately',
    'coverage':'intersection of versioned task fingerprints within identical benchmark/dataset/harness cohorts',
    'limitations':'Local grading-v2 and official test-log reports remain separate. Internal subsets are not full official SWE-bench scores. Gold validation/stubs are not model capability scores.'}


def records(repo, **filters):
    offset = 0
    while True:
        page = repo.query_runs(limit=500, offset=offset, **filters)['items']
        if not page:
            return
        yield from page
        offset += len(page)


def eligible_attempt(run):
    """Shared provenance boundary; non-live experiments remain diagnostic only."""
    snap = run.get('snapshot') or {}
    return (run.get('mode') == 'agent' and snap.get('grading_protocol') in (PROTOCOL,OFFICIAL_PROTOCOL)
            and all(snap.get(k) for k in ('task_fingerprint','harness_revision','runtime_fingerprint',
                                         'configuration_fingerprint','endpoint_identity','effective_model'))
            and snap.get('data_origin') in ('live','local_stub','audit','unverified'))


def trusted_attempt(run):
    return eligible_attempt(run) and run['snapshot']['data_origin'] == 'live' and run['snapshot']['grading_protocol']==PROTOCOL


def trusted_success(run):
    return trusted_attempt(run) and valid(run) and run['metrics']['resolved'] is True


def first_attempt_identity(run):
    snap, task = run.get('snapshot') or {}, run['task']
    return (task['benchmark'], task['dataset_version'], snap.get('task_fingerprint',task['id']),
            snap.get('grading_protocol'), snap.get('harness_revision'), run['model']['id'],
            run['model']['upstream_id'], snap.get('endpoint_identity'),
            snap.get('configuration_fingerprint'), snap.get('runtime_fingerprint'),
            digest(snap.get('effective_model', {})), snap.get('data_origin'))


def valid(run):
    m, s = run['metrics'], run.get('snapshot') or {}
    if not eligible_attempt(run) or run['state'] != 'completed':
        return False
    if s.get('grading_protocol')==OFFICIAL_PROTOCOL:
        meta=m.get('execution_metadata',{})
        if run['task'].get('benchmark')!=DATASET or meta.get('grading_protocol')!=OFFICIAL_PROTOCOL or meta.get('harness_version')!=HARNESS_VERSION or meta.get('harness_commit')!=HARNESS_COMMIT or not meta.get('evaluator_image_digest') or m['test_execution_errors']!=0:
            return False
        if meta.get('failure_classification')=='patch_rejected':return m['resolved'] is False and m['patch_applied'] is False
        return (meta.get('failure_classification') in ('resolved','unresolved') and bool(meta.get('report_sha256')) and bool(meta.get('patch_sha256')) and bool(meta.get('harness_run_id')) and bool(meta.get('evaluation_config_fingerprint')) and m['test_result'] in ('passed','failed') and m['assertions_expected'] is not None and m['assertions_expected']>0 and m['assertions_executed']==m['assertions_expected'] and ((m['test_result']=='passed' and m['assertions_passed']==m['assertions_expected']) or (m['test_result']=='failed' and m['assertions_passed'] is not None and m['assertions_passed']<m['assertions_expected'])) and m['resolved'] is (m['test_result']=='passed'))
    if m['patch_applied'] is False and m['resolved'] is False:
        return True
    return (m['execution_metadata'].get('grading_protocol')==PROTOCOL and m['test_result'] in ('passed','failed')
            and m['assertions_expected'] is not None and m['assertions_expected']>0
            and m['test_execution_errors']==0 and bool(m['execution_metadata'].get('controller_image_digest'))
            and m['assertions_executed']==m['assertions_expected']
            and ((m['test_result']=='passed' and m['assertions_passed']==m['assertions_expected'])
                 or (m['test_result']=='failed' and m['assertions_passed'] is not None and m['assertions_passed']<m['assertions_expected']))
            and m['resolved'] is (m['test_result']=='passed'))


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    x = (len(values)-1)*p; low = math.floor(x); high = math.ceil(x)
    return values[low]+(values[high]-values[low])*(x-low)


def summary(runs):
    evaluated = [r for r in runs if valid(r)]
    resolved = sum(r['metrics']['resolved'] is True for r in evaluated)
    independent = {}
    for run in sorted(runs,key=lambda r:(r['created_at'],r['id'])):
        if run['parent_id'] is None and run.get('attempt',(run.get('batch') or {}).get('attempt',1)) in (None,1):
            independent.setdefault(first_attempt_identity(run),run)
    first_success = sum(valid(r) and r['metrics']['resolved'] is True for r in independent.values())
    durations = [r['metrics']['wall_seconds'] for r in runs if r['state'] in ('completed','failed','timeout','cancelled')]
    costs = [r['metrics']['cost'] for r in runs]
    known = [x for x in costs if x is not None]
    currencies={r['metrics'].get('currency') for r in runs if r['metrics']['cost'] is not None}
    single_currency=len(currencies)<=1
    by_currency={str(c):sum(r['metrics']['cost'] for r in runs if r['metrics']['cost'] is not None and r['metrics'].get('currency')==c) for c in currencies}
    requests = sum(r['metrics']['model_requests'] for r in runs)
    api_errors = sum(r['metrics']['api_errors'] for r in runs)
    infra = sum(r['state'] in ('failed','timeout') for r in runs)
    totals = {}
    for field in ('input_tokens','output_tokens','total_tokens'):
        values = [r['metrics'][field] for r in runs]
        totals[field] = sum(values) if values and all(v is not None for v in values) else None
        totals[field+'_known_subtotal'] = sum(v for v in values if v is not None)
    return dict(attempts=len(runs),valid_evaluations=len(evaluated),resolved=resolved,
        repair_failures=len(evaluated)-resolved,infrastructure_errors=infra,
        incomplete=sum(r['state'] in ('queued','preparing','running','evaluating') for r in runs),
        cancelled=sum(r['state']=='cancelled' for r in runs),
        resolved_rate=resolved/len(evaluated) if evaluated else None,
        attempt_success_rate=resolved/len(runs) if runs else None,
        pass_at_1=first_success/len(independent) if independent else None,pass_at_1_tasks=len(independent),
        average_seconds=sum(durations)/len(durations) if durations else None,
        p50_seconds=percentile(durations,.5),p95_seconds=percentile(durations,.95),
        latency_samples=len(durations),model_requests=requests,api_errors=api_errors,
        api_error_rate=api_errors/requests if requests else None,
        infrastructure_failure_rate=infra/len(runs) if runs else None,
        currency=next(iter(currencies)) if len(currencies)==1 else None,mixed_currencies=not single_currency,known_cost_by_currency=by_currency,
        known_cost_subtotal=sum(known) if known and single_currency else None,unknown_cost_attempts=len(costs)-len(known),
        total_cost=sum(known) if costs and single_currency and len(known)==len(costs) else None,
        average_task_cost=sum(known)/len(costs) if costs and single_currency and len(known)==len(costs) else None,
        cost_per_resolved_task=sum(known)/resolved if resolved and single_currency and len(known)==len(costs) else None,
        **totals)


def comparison(repo, *, profile_ids=None, batch_id=None):
    grouped, excluded = defaultdict(list), Counter()
    for run in records(repo, **({'batch_id':batch_id} if batch_id else {})):
        s = run.get('snapshot')
        if profile_ids and run['model']['id'] not in profile_ids:
            continue
        if not eligible_attempt(run):
            excluded['legacy_or_missing_provenance']+=1; continue
        if run['mode']!='agent':
            excluded['non_agent']+=1; continue
        task = run['task']
        key = (task['benchmark'],task['dataset_version'],s['harness_revision'],s['grading_protocol'],str(s.get('subset') or '')+' | '+s['selected_subset']['id']+'@'+str(s['selected_subset']['revision'])+':'+s['selected_subset']['fingerprint'] if s.get('selected_subset') else s.get('subset'),s.get('agent_version') if s['grading_protocol']==OFFICIAL_PROTOCOL else None,run['model']['id'],
               run['model']['upstream_id'],s['runtime_fingerprint'],s['effective_model']['reasoning_effort'],s['endpoint_identity'],
               s['configuration_fingerprint'],digest(s['effective_model']),s['data_origin'])
        grouped[key].append(run)
    groups, cohorts = [],defaultdict(list)
    for key, runs in grouped.items():
        benchmark, version, harness, protocol, subset, agent_version, profile, upstream, runtime, reasoning, endpoint, config, effective, origin = key
        tasks = {r['snapshot']['task_fingerprint'] for r in runs}
        item = dict(id=digest(key)[:20],benchmark=benchmark,dataset_version=version,harness_revision=harness,
            profile_id=profile,model_id=runs[0]['model']['model_id'],upstream_id=upstream,reasoning_effort=reasoning,
            endpoint_identity=runs[0]['snapshot']['endpoint_identity'],runtime_fingerprint=runtime,
            grading_protocol=protocol,subset=subset,selected_subset=runs[0]['snapshot'].get('selected_subset'),agent_version=agent_version,official_harness_version=HARNESS_VERSION if protocol==OFFICIAL_PROTOCOL else None,configuration_fingerprint=config,effective_configuration_fingerprint=effective,
            trusted_evidence=origin=='live' and protocol==PROTOCOL,evidence_authority='official_test_log_report' if protocol==OFFICIAL_PROTOCOL else 'isolated_v2_controller',data_origins=sorted({r['snapshot']['data_origin'] for r in runs}),
            upstream_verified=all(r['snapshot']['upstream_verified'] for r in runs),
            task_count=len(tasks),metrics=summary(runs),warnings=[],
            controller_digests=sorted({r['metrics']['execution_metadata']['controller_image_digest'] for r in runs if r['metrics']['execution_metadata'].get('controller_image_digest')}),
            last_attempted_at=max(r['created_at'] for r in runs),
            evaluated_at=max((r['finished_at'] for r in runs if trusted_attempt(r) and valid(r) and r['finished_at'] is not None),default=None),
            last_trusted_success_at=max((r['finished_at'] for r in runs if trusted_success(r) and r['finished_at'] is not None),default=None))
        if protocol==OFFICIAL_PROTOCOL:
            item['warnings'].append('official_subset: internal coverage only; official harness test-log trust boundary differs from isolated v2')
        if len(tasks)<5:
            item['warnings'].append('small_sample: insufficient tasks for general coding-capability ranking')
        if item['data_origins']!=['live']:
            item['warnings'].append('non_live_or_unverified_data')
        if not item['upstream_verified']:
            item['warnings'].append('upstream_unverified: gateway may reroute')
        item['task_matrix'] = [dict(task_id=r['task']['id'],task_fingerprint=r['snapshot']['task_fingerprint'],run_id=r['id'],
            state=r['state'],resolved=r['metrics']['resolved'] if valid(r) else None,valid=valid(r),attempt=r.get('attempt')) for r in runs]
        item['_runs'],item['_tasks'] = runs,tasks
        cohorts[key[:6]].append(item);groups.append(item)
    for cohort in cohorts.values():
        matched = set.intersection(*(g['_tasks'] for g in cohort))
        controller_sets = {tuple(g['controller_digests']) for g in cohort if g['controller_digests']}
        comparable = bool(matched) and len(controller_sets)<=1 and all(len(g['controller_digests'])<=1 for g in cohort)
        unequal = any(g['_tasks']!=matched for g in cohort)
        for group in cohort:
            group['matched_task_fingerprints'] = sorted(matched)
            group['matched_task_count'] = len(matched)
            group['comparison_eligible'] = comparable
            group['matched_metrics'] = summary([r for r in group['_runs'] if r['snapshot']['task_fingerprint'] in matched]) if comparable else None
            if unequal:
                group['warnings'].append('unequal_task_coverage: matched subset used')
            if not comparable:
                group['warnings'].append('incompatible_controller_or_no_matched_tasks')
            del group['_runs'],group['_tasks']
    protocols = sorted({group['grading_protocol'] for group in groups})
    methodology = {**METHODOLOGY, 'grading_protocol':protocols[0] if len(protocols)==1 else None,
                   'grading_protocols':protocols}
    return {'schema_version':'swe-comparison-v1','methodology':methodology,'groups':groups,'excluded':dict(excluded),
            'warnings':['Internal subset evidence cannot establish a full official SWE-bench score. No automatic ranking.']}


def shadow_export(repo):
    result = comparison(repo)
    items=[]
    for group in result['groups']:
        # No legacy/stub/incomplete outcomes enter the scoring input. Tiny-sample
        # summaries are informative only, never capability weights.
        if group['benchmark']!='local-python-repairs' or any(x['task_id']!='intervals-001' for x in group['task_matrix']):
            result['excluded']['unsupported_benchmark_configuration']=result['excluded'].get('unsupported_benchmark_configuration',0)+group['metrics']['attempts']
            continue
        if group['data_origins']!=['live'] or not group['upstream_verified']:
            continue
        runs = [repo.get(x['run_id']) for x in group['task_matrix'] if x['valid']]
        if not runs:
            continue
        data = {k:v for k,v in group.items() if k not in ('metrics','matched_metrics','task_matrix')}
        data['metrics']=summary(runs)
        # Pass@1's first-attempt denominator must retain infrastructure failures.
        for key in ('pass_at_1','pass_at_1_tasks','attempt_success_rate'):
            data['metrics'][key]=group['metrics'][key]
        data['evaluated_at']=max(r['finished_at'] for r in runs)
        data['freshness_seconds']=max(0,time.time()-data['evaluated_at'])
        data['quality']={'trusted':True,'scoring_eligible':len({r['snapshot']['task_fingerprint'] for r in runs})>=5 and len(runs)>=5 and group['comparison_eligible'],
                         'capability_weights':None,'eligible_run_count':len(runs), 'valid_task_count':len({r['snapshot']['task_fingerprint'] for r in runs}),
                         'excluded_attempt_count':group['metrics']['attempts']-len(runs)}
        # Reliability explicitly includes all original attempts, separate from scored outcomes.
        data['reliability']={k:group['metrics'][k] for k in ('attempts','infrastructure_errors','infrastructure_failure_rate','api_error_rate','incomplete','cancelled')}
        items.append(data)
    return {'schema_version':'gpt-auto-swe-v1','generated_at':time.time(),'read_only':True,
            'methodology':METHODOLOGY,'items':items,'excluded':result['excluded']}

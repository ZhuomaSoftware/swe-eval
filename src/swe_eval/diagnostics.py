"""Public diagnostics allowlists. Hidden controller material is memory-only.

Historical database/log backups remain operator-controlled forensic evidence;
ordinary repository/API reads must never return their private grading payloads.
"""
import json


def assertion_summary(verdict):
    safe = {'protocol': 'swe-eval-grading-v2'}
    for key in ('assertions_expected', 'assertions_executed', 'assertions_passed', 'execution_errors'):
        value = verdict.get(key)
        safe[key] = value if type(value) is int and value >= 0 else None
    executed, passed = safe['assertions_executed'], safe['assertions_passed']
    safe['assertions_failed'] = max(0, executed-passed) if executed is not None and passed is not None else None
    safe['passed'] = verdict.get('passed') if type(verdict.get('passed')) is bool else None
    safe['classification'] = ('execution_error' if safe['execution_errors'] else
                              'passed' if safe['passed'] else 'assertion_failure')
    return safe


def log_message(event, message):
    if event == 'official_grading_summary':
        try:
            value=json.loads(message)
            allowed={k:v for k,v in value.items() if (k in ('assertions_expected','assertions_executed','assertions_passed') and (v is None or type(v) is int and v>=0)) or (k=='classification' and v in ('resolved','unresolved','patch_rejected','empty_patch_skipped','evaluation_error','environment_failure','timeout')) or (k=='harness_version' and v=='5.0.2')}
            return json.dumps(allowed)
        except (ValueError,TypeError,AttributeError):return 'Private official grading details withheld'
    if event == 'test_output':
        # Candidate stdout/stderr can echo private inputs or correct answers.
        return 'Private grading operation output withheld; see assertion counts and execution status'
    if event == 'trusted_assertions':
        try:
            value = json.loads(message)
            if isinstance(value, dict):
                return json.dumps(assertion_summary(value))
        except (ValueError, TypeError):
            pass
        return 'Private grading details withheld; summary unavailable'
    return message


def public_log(record):
    return dict(record, message=log_message(record['event'], record['message']))


def public_metadata(metadata):
    # No arbitrary controller details/private configuration can enter run detail.
    allowed = ('network', 'uid', 'base_commit', 'mode', 'agent_image_digest',
               'evaluator_image_digest', 'controller_image_digest', 'grading_protocol',
               'harness_version','harness_commit','dataset_revision','instance_id','repo',
               'patch_sha256','harness_run_id','evaluation_config_fingerprint','report_sha256',
               'failure_classification','trust_boundary')
    return {key: metadata[key] for key in allowed if key in metadata and isinstance(metadata[key], (str, int))}

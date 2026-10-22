"""Bounded buffered-request retries and durable, opt-in clean-run recovery.
No upstream response message, header or arbitrary error code is public.
"""
import email.utils
import socket,ssl,http.client,errno
import math
import time
from pathlib import Path
from pydantic import Field, model_validator
from .schema import StrictModel, Metrics
from .provider_errors import ProviderError

class RequestRetryPolicy(StrictModel):
    enabled: bool = True
    max_attempts: int = Field(default=3, ge=1, le=5)
    initial_delay: float = Field(default=1, ge=.05, le=20, allow_inf_nan=False)
    multiplier: float = Field(default=2, ge=1, le=4, allow_inf_nan=False)
    max_delay: float = Field(default=20, ge=.05, le=30, allow_inf_nan=False)
    time_budget: float = Field(default=60, ge=.1, le=180, allow_inf_nan=False)
    @model_validator(mode='after')
    def valid(self):
        if self.initial_delay>self.max_delay:raise ValueError('initial retry delay exceeds maximum')
        return self

class RunRecoveryPolicy(StrictModel):
    enabled: bool = False
    max_recoveries: int = Field(default=1, ge=0, le=1)
    minimum_remaining_seconds: int = Field(default=60, ge=1, le=3600)
    # Whole-evaluation timeouts, crashes and repair outcomes are deliberately excluded.
    eligible_categories: list[str] = Field(default_factory=lambda:['transient_http','rate_limited','network','request_timeout','capacity_unavailable'],max_length=5)
    @model_validator(mode='after')
    def valid(self):
        if set(self.eligible_categories)-{'transient_http','rate_limited','network','request_timeout','capacity_unavailable'}:raise ValueError('ineligible recovery category')
        return self

def seconds(value, *, milliseconds=False):
    try:
        n=float(value)
        if not math.isfinite(n) or n<0:return None
        return min(n/(1000 if milliseconds else 1),86400)
    except (TypeError,ValueError):return None

def classify_http(status, headers, payload):
    error=payload.get('error',payload) if isinstance(payload,dict) else {}
    if not isinstance(error,dict):error={}
    # Inspect only bounded structured fields, never infer policy from human text.
    layers=[error]+([payload] if isinstance(payload,dict) and payload is not error else [])
    for k in ('details','metadata','capacity','quota'):
        if isinstance(error.get(k),dict):layers.append(error[k])
    code=error.get('code') or error.get('type')
    if not isinstance(code,str):code=None
    permanent={'insufficient_quota','quota_exhausted','billing_hard_limit_reached','quota_guard_request_too_large','request_too_large','invalid_api_key','invalid_model','invalid_request_error'}
    category=('quota_exhausted' if status==429 and code in permanent else
              'rate_limited' if status==429 else 'transient_http' if status in (408,500,502,503,504) else
              'authentication' if status in (401,403) else 'invalid_request' if status in (400,404,405,413,422) else 'unknown')
    retryable=category in ('rate_limited','transient_http')
    waits=[]
    raw=headers.get('Retry-After') or headers.get('retry-after')
    if raw is not None:
        n=seconds(raw)
        if n is None:
            try:n=seconds(email.utils.parsedate_to_datetime(str(raw)).timestamp()-time.time())
            except (ValueError,TypeError,OverflowError):pass
        if n is not None:waits.append(n)
    for layer in layers:
        for key in ('retry_after_ms','wait_ms','soonest_available_ms'):
            n=seconds(layer.get(key),milliseconds=True)
            if n is not None:waits.append(n)
    if status==429 and not waits and any(layer.get('eligible')==0 and layer.get('soonest_available_ms') is None for layer in layers):
        category='quota_exhausted';retryable=False
    return ProviderError('upstream HTTP '+str(status),category=category,status=status,retryable=retryable,
                         retry_after=max(waits) if waits else None,provider_code=code if code in permanent|{'rate_limit_exceeded','rate_limit','temporary_overload','overloaded','capacity_unavailable'} else None,ambiguous=status in (408,500,502,503,504))


def transport_failure(error):
    if isinstance(error,ssl.SSLCertVerificationError):
        return ProviderError('TLS verification failed',category='tls_verification')
    if isinstance(error,(TimeoutError,socket.timeout)):
        return ProviderError('provider request timed out',category='request_timeout',retryable=True,ambiguous=True)
    if isinstance(error,socket.gaierror):
        return ProviderError('provider DNS unavailable',category='network' if error.errno==socket.EAI_AGAIN else 'dns_permanent',retryable=error.errno==socket.EAI_AGAIN)
    transient=isinstance(error,(ConnectionError,http.client.RemoteDisconnected,http.client.IncompleteRead)) or getattr(error,'errno',None) in {errno.ECONNRESET,errno.ECONNREFUSED,errno.ETIMEDOUT,errno.ENETDOWN,errno.ENETUNREACH,errno.EHOSTUNREACH,errno.EPIPE,errno.ECONNABORTED}
    return ProviderError('provider transport unavailable',category='network' if transient else 'unknown_transport',retryable=transient,ambiguous=True)

def retry_schema_ready(repo):
    with repo.connect() as db:return db.execute("SELECT 1 FROM metadata WHERE key='api_retry_schema' AND value='1'").fetchone() is not None

def migrate_retries(repo):
    with repo.connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0]!=3:raise ValueError('retry migration requires management schema 3')
        if retry_schema_ready(repo):return
        try:db.executescript((Path(__file__).parent/'migrations/004_retries.sql').read_text())
        except BaseException:db.rollback();raise

class RetryRuntime:
    """Small provider hooks; all mutations validate the current lease/run state."""
    def __init__(self,repo,settings,record):self.repo,self.settings,self.record=repo,settings,record
    @property
    def key(self):
        s=self.record.get('snapshot') or {};return (self.record['model'].get('provider_id') or self.record['model']['upstream_id'])+':'+s.get('endpoint_identity','unknown')
    def available(self):
        from .storage import Conflict
        from .management import ConfigurationRepository
        with self.repo.connect() as db:self.repo._writable(db,self.record['id'])
        m=self.record['model']
        if m.get('provider_id'):
            c=ConfigurationRepository(self.repo,self.settings)
            # Runtime disabling stops pending API retries, without rewriting snapshots.
            with self.repo.connect() as db:
                p,_,_=c.revision(db,'provider',m['provider_id'])
                model,_,_=c.revision(db,'model',m['id'])
                if not p['enabled'] or p['archived'] or not model['enabled'] or model['archived']:
                    raise ProviderError('provider or profile disabled',category='disabled')
            try:c.secret(m['provider_id'],m['credential_version'])
            except ValueError:raise ProviderError('credential unavailable',category='credential_revoked') from None
        return True
    def cooldown(self,delay=None,category=None):
        if not retry_schema_ready(self.repo):return 0
        with self.repo.connect(write=delay is not None) as db:
            if delay is not None:
                self.repo._writable(db,self.record['id'])
                db.execute('INSERT INTO provider_cooldowns VALUES(?,?,?) ON CONFLICT(provider_key) DO UPDATE SET until_at=max(until_at,excluded.until_at),reason=excluded.reason',(self.key,time.time()+min(delay,86400),category))
            r=db.execute('SELECT until_at FROM provider_cooldowns WHERE provider_key=?',(self.key,)).fetchone()
            return max(0,r[0]-time.time()) if r else 0
    def log(self,event,detail):self.repo.log(self.record['id'],event,__import__('json').dumps(detail))

class RetryRepositoryMixin:
    def retry_info(self,db,run_id):
        if not db.execute("SELECT 1 FROM metadata WHERE key='api_retry_schema'").fetchone():return None
        row=db.execute('SELECT * FROM run_recoveries WHERE child_id=?',(run_id,)).fetchone()
        children=[dict(x) for x in db.execute('SELECT x.*,r.state FROM run_recoveries x JOIN runs r ON r.id=x.child_id WHERE x.parent_id=?',(run_id,))]
        decision=db.execute('SELECT reason,decided_at FROM recovery_decisions WHERE parent_id=?',(run_id,)).fetchone()
        return {'kind':'automatic_recovery' if row else 'original_or_manual','binding':dict(row) if row else None,'children':children,'decision':dict(decision) if decision else None}

    def schedule_recoveries(self,owner,settings):
        """A restart can scan again: unique parent + child insertion commit atomically."""
        from .schema import Metrics
        if not retry_schema_ready(self):return []
        with self.connect(write=True) as db:
            return self._schedule_recoveries(db,owner,settings)

    def _schedule_recoveries(self,db,owner,settings):
        created=[]
        self._check_owner(db,owner)
        self._reconcile_batches(db)
        rows=db.execute("""SELECT r.*,a.batch_id,b.configuration_json,b.deadline,b.cancel_requested AS batch_cancel
            FROM runs r JOIN batch_attempts a ON a.run_id=r.id JOIN evaluation_batches b ON b.id=a.batch_id
            WHERE r.state='failed' AND coalesce(r.error,'')!='worker_interrupted' AND r.parent_id IS NULL AND r.mode='agent' AND r.cancel_requested=0
              AND b.cancel_requested=0 AND b.deadline>?
              AND NOT EXISTS(SELECT 1 FROM recovery_decisions x WHERE x.parent_id=r.id)
            ORDER BY r.finished_at,r.id""",(time.time(),)).fetchall()
        for row in rows:
            config=__import__('json').loads(row['configuration_json'])
            policy=RunRecoveryPolicy.model_validate(config.get('run_recovery') or {})
            m=Metrics.model_validate_json(row['metrics_json']);failure=m.last_provider_error
            if not policy.enabled or not policy.max_recoveries or not m.recovery_eligible or failure.get('category') not in policy.eligible_categories:continue
            db.execute('INSERT INTO recovery_decisions VALUES(?,?,?)',(row['id'],'not_admitted',time.time()))
            snaprow=db.execute('SELECT snapshot_json FROM evaluation_snapshots WHERE run_id=?',(row['id'],)).fetchone()
            def decline(reason):db.execute('UPDATE recovery_decisions SET reason=? WHERE parent_id=?',(reason,row['id']))
            if not snaprow:decline('missing_snapshot');continue
            snap=__import__('json').loads(snaprow[0]);model=__import__('json').loads(row['model_json'])
            if model.get('provider_id'):
                from .management import ConfigurationRepository
                c=ConfigurationRepository(self,settings)
                try:
                    p,_,_=c.revision(db,'provider',model['provider_id']);mp,_,_=c.revision(db,'model',model['id'])
                    cred=db.execute('SELECT revoked FROM provider_credentials WHERE provider_id=? AND version=?',(model['provider_id'],model.get('credential_version'))).fetchone()
                    if not p['enabled'] or p['archived'] or not mp['enabled'] or mp['archived'] or (model.get('credential_version') and (not cred or cred[0])):decline('provider_or_credential_unavailable');continue
                except KeyError:decline('configuration_unavailable');continue
            key=(model.get('provider_id') or model['upstream_id'])+':'+snap.get('endpoint_identity','unknown')
            cooldown=db.execute('SELECT until_at FROM provider_cooldowns WHERE provider_key=?',(key,)).fetchone()
            due=max(time.time(),cooldown[0] if cooldown else 0)
            # Recovery requires enough time for a complete bounded attempt, not a nearly expired deadline.
            minimum=max(policy.minimum_remaining_seconds,min(__import__('json').loads(row['task_json'])['time_limit'],snap['effective_model']['max_evaluation_duration']))
            if row['deadline']-due<minimum:decline('insufficient_deadline');continue
            if self._pending(db)>=settings.max_pending_runs:decline('queue_capacity');continue
            # Reserve full per-run HTTP caps at batch admission; never admit more work later than reserved.
            cap=snap['effective_model']['max_model_calls']
            allowance=db.execute('SELECT coalesce(sum(coalesce(json_extract(r.metrics_json,\'$.http_attempts\'),json_extract(r.metrics_json,\'$.model_requests\'),0)),0) FROM runs r WHERE r.id IN (SELECT run_id FROM batch_attempts WHERE batch_id=? UNION SELECT child_id FROM run_recoveries WHERE batch_id=?)',(row['batch_id'],row['batch_id'])).fetchone()[0]
            if allowance+cap>config['max_requests']:decline('request_budget');continue
            child=self._insert_run(db,__import__('json').loads(row['task_json']),model,parent_id=row['id'],snapshot=snap)
            db.execute('INSERT INTO run_recoveries VALUES(?,?,?,?,?,?,?)',(row['id'],child,row['batch_id'],1,failure['category'],due,time.time()))
            self._log(db,child,'automatic_recovery_queued',__import__('json').dumps({'parent_id':row['id'],'sequence':1,'reason':failure['category'],'next_eligible_at':due}))
            db.execute('UPDATE recovery_decisions SET reason=? WHERE parent_id=?',('scheduled',row['id']))
            created.append(child)
        return created

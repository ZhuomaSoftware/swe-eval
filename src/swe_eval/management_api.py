"""Administrator-only management surface. No secrets in responses or exceptions."""
import time,re,os
from collections import Counter
from fastapi import HTTPException,Query
from .management import ConfigurationRepository,administration_ready,current_profiles
from .management_schema import ProviderWrite,ManagedModelWrite,SecretRotation,CredentialRevoke,RevisionAction,SubsetWrite,AdministrationJob
from .secret_store import SecretBox,SecretUnavailable
from .outbound import request_json,OutboundDenied
from .providers import ProviderError
from .administration_jobs import AdministrativeJobs
from .center_schema import BatchSubmission
from .storage import Conflict
from .security import Redactor
from .center import BatchRequestBudgetError

def install_management(app,settings,repo,benchmark,auth):
    c=ConfigurationRepository(repo,settings);jobs=AdministrativeJobs(repo,settings)
    def guard(fn,*args,**kwargs):
        try:return fn(*args,**kwargs)
        except KeyError:raise HTTPException(404,'resource not found') from None
        except Conflict:raise
        except BatchRequestBudgetError as error:raise HTTPException(422,str(error)) from None
        except (ValueError,ProviderError):raise HTTPException(422,'invalid configuration, revision, credential or outbound policy; review field limits and server configuration') from None
    def require():
        if not administration_ready(repo):raise HTTPException(503,'administration requires explicit migrate-admin authorization')
    prefix='/api/v1/manage'
    @app.get(prefix+'/capabilities',dependencies=auth)
    def capabilities():
        try:SecretBox();key=True
        except SecretUnavailable:key=False
        return {'schema_ready':administration_ready(repo),'credential_store_ready':key,'max_batch_runs':settings.max_batch_runs,'max_pending_runs':settings.max_pending_runs,'max_batch_requests':settings.max_batch_requests,'max_batch_duration':settings.max_batch_duration,'validation_concurrency':1,'max_validation_instances':5,'inference_connection_test':False}
    @app.get(prefix+'/providers',dependencies=auth)
    def providers():require();return {'items':guard(c.providers)}
    @app.post(prefix+'/providers',dependencies=auth,status_code=201)
    def create_provider(body:ProviderWrite):require();return guard(c.write_provider,body,create=True)
    @app.put(prefix+'/providers/{identity}',dependencies=auth)
    def update_provider(identity:str,body:ProviderWrite):
        require()
        if identity!=body.id:raise HTTPException(422,'resource ID cannot change')
        return guard(c.write_provider,body)
    @app.post(prefix+'/providers/{identity}/rotate',dependencies=auth)
    def rotate(identity:str,body:SecretRotation):
        require();p=guard(c.provider,identity);values={k:v for k,v in p.items() if k in ProviderWrite.model_fields};values.update(expected_revision=body.expected_revision,api_key=body.api_key)
        return guard(c.write_provider,ProviderWrite.model_validate(values),action='credential_rotated')
    @app.post(prefix+'/providers/{identity}/revoke',dependencies=auth)
    def revoke(identity:str,body:CredentialRevoke):require();return guard(c.revoke,identity,body.credential_version)
    @app.post(prefix+'/providers/{identity}/test',dependencies=auth)
    def test_provider(identity:str):
        require();p=guard(c.provider,identity)
        if not p['enabled'] or p['archived']:raise HTTPException(409,'provider is disabled or archived')
        started=time.monotonic()
        try:
            response=request_json(p['base_url'].rstrip('/')+'/models',c.secret(identity,p['credential_version']),timeout=min(5,p['request_timeout']))
            if not isinstance(response.get('data'),list):raise ProviderError('invalid model-list schema')
            count=len(response['data']);c.connection_event(identity,p['revision'],'ok')
            return {'status':'ok','model_count':count,'seconds':round(time.monotonic()-started,3),'inference_performed':False}
        except (ProviderError,SecretUnavailable):
            c.connection_event(identity,p['revision'],'failed','connection, credential, response schema or outbound policy error')
            raise HTTPException(502,'bounded non-inference provider connection test failed') from None
    @app.get(prefix+'/providers/{identity}/history',dependencies=auth)
    def provider_history(identity:str):require();return {'items':guard(c.history,'provider',identity)}
    @app.post(prefix+'/providers/{identity}/discover-models',dependencies=auth)
    def discover_models(identity:str):
        require();p=guard(c.provider,identity)
        if not p['enabled'] or p['archived']:raise HTTPException(409,'provider is disabled or archived')
        try:
            key=c.secret(identity,p['credential_version'])
            response=request_json(p['base_url'].rstrip('/')+'/models',key,timeout=min(5,p['request_timeout']))
            if not isinstance(response.get('data'),list):raise ProviderError('invalid model-list schema')
            # Treat the entire upstream document as untrusted. Return only bounded,
            # unique identifiers, never arbitrary metadata or reflected credentials.
            redact=Redactor([key,settings.admin_token,os.getenv('SWE_CONFIG_MASTER_KEY','')])
            identities=set()
            for item in response['data']:
                value=item.get('id') if isinstance(item,dict) else None
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/@()+-]{0,199}',value) and not redact.contains_secret(value):
                    identities.add(value)
            models=[{'id':value} for value in sorted(identities)[:500]]
            c.connection_event(identity,p['revision'],'ok')
            return {'provider_id':identity,'provider_revision':p['revision'],'items':models,
                    'total':len(identities),'truncated':len(identities)>500,'inference_performed':False}
        except (ProviderError,SecretUnavailable):
            c.connection_event(identity,p['revision'],'failed','connection, credential, response schema or outbound policy error')
            raise HTTPException(502,'bounded non-inference provider model discovery failed') from None
    @app.get(prefix+'/models',dependencies=auth)
    def models():
        require()
        from .config import load_models
        return {'items':guard(c.models),'file_profiles':[dict(p.public(),source='file',read_only=True) for p in load_models(settings.models_file).values()]}
    @app.post(prefix+'/models',dependencies=auth,status_code=201)
    def create_model(body:ManagedModelWrite):require();return guard(c.write_model,body,create=True)
    @app.put(prefix+'/models/{identity}',dependencies=auth)
    def update_model(identity:str,body:ManagedModelWrite):
        require()
        if body.id!=identity:raise HTTPException(422,'resource ID cannot change')
        return guard(c.write_model,body)
    @app.get(prefix+'/models/{identity}/history',dependencies=auth)
    def model_history(identity:str):require();return {'items':guard(c.history,'model',identity)}
    @app.get(prefix+'/datasets',dependencies=auth)
    def datasets():
        require();all_tasks=benchmark.catalogue.list_tasks();items=[]
        for revision in benchmark.catalogue.revisions():
            tasks=[t for t in all_tasks if t.dataset_version==revision['revision']]
            items.append(dict(revision,dataset='SWE-bench Verified',source='SWE-bench/SWE-bench_Verified',archived=c.dataset_archived(revision['revision']),prepared_images=sum(bool(t.environment_image_digest) for t in tasks),validated_tasks=sum(t.environment_ready for t in tasks),blocked_tasks=sum(t.validation_status in ('blocked','failed','interrupted') for t in tasks),validation_counts=dict(Counter(t.validation_status for t in tasks)),last_synchronization=_import_time(benchmark.catalogue,revision['revision'])))
        return {'items':items,'jobs':jobs.list()}
    @app.post(prefix+'/datasets/{revision}/archive',dependencies=auth)
    def archive_dataset(revision:str):
        require()
        if revision not in {r['revision'] for r in benchmark.catalogue.revisions()}:raise HTTPException(404,'dataset revision not found')
        return guard(c.archive_dataset,revision,True)
    @app.post(prefix+'/datasets/{revision}/restore',dependencies=auth)
    def restore_dataset(revision:str):require();return guard(c.archive_dataset,revision,False)
    @app.get(prefix+'/tasks',dependencies=auth)
    def tasks(limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0,le=2**63-1),dataset:str|None=None,revision:str|None=None,repository:str|None=None,search:str|None=Query(None,max_length=200),validation_status:str|None=None,ready:bool|None=None):
        require();items=[t for t in benchmark.list_tasks() if (not dataset or t.benchmark==dataset) and (not revision or t.dataset_version==revision) and (not repository or getattr(t,'repo',None)==repository) and (not search or search.lower() in (t.id+' '+t.issue).lower()) and (not validation_status or getattr(t,'validation_status','validated')==validation_status) and (ready is None or getattr(t,'environment_ready',True)==ready)]
        return {'items':[t.public() for t in items[offset:offset+limit]],'total':len(items),'limit':limit,'offset':offset}
    @app.get(prefix+'/subsets',dependencies=auth)
    def subsets():require();return {'items':guard(c.subsets,benchmark)}
    @app.post(prefix+'/subsets',dependencies=auth,status_code=201)
    def create_subset(body:SubsetWrite):require();return guard(c.write_subset,body,benchmark,create=True)
    @app.put(prefix+'/subsets/{identity}',dependencies=auth)
    def update_subset(identity:str,body:SubsetWrite):
        require()
        if identity!=body.id:raise HTTPException(422,'resource ID cannot change')
        return guard(c.write_subset,body,benchmark)
    @app.get(prefix+'/subsets/{identity}',dependencies=auth)
    def subset(identity:str,revision:int|None=Query(None,ge=1)):require();return guard(c.subset,identity,benchmark,revision)
    @app.get(prefix+'/subsets/{identity}/history',dependencies=auth)
    def subset_history(identity:str):
        require();current=guard(c.subset,identity,benchmark)
        return {'items':[c.subset(identity,benchmark,r) for r in range(current['revision'],0,-1)]}
    @app.post(prefix+'/subsets/{identity}/archive',dependencies=auth)
    def archive_subset(identity:str,body:RevisionAction):require();return guard(c.archive_subset,identity,body.expected_revision)
    @app.get(prefix+'/jobs',dependencies=auth)
    def job_list():require();return {'items':jobs.list()}
    @app.post(prefix+'/jobs',dependencies=auth,status_code=202)
    def job_create(body:AdministrationJob):require();return guard(jobs.create,body,benchmark)
    @app.post(prefix+'/jobs/{identity}/cancel',dependencies=auth,status_code=202)
    def job_cancel(identity:str):require();return guard(jobs.cancel,identity)
    @app.get(prefix+'/audit',dependencies=auth)
    def audit(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0,le=2**63-1)):require();return c.audit_events(limit,offset)
    @app.post(prefix+'/batch-preview',dependencies=auth)
    def preview(body:BatchSubmission):
        require()
        from .center import effective_profile
        def calculate():
            profiles=current_profiles(settings,repo);tasks=[benchmark.get_task(x) for x in body.task_ids];selected=[profiles[x] for x in body.model_profile_ids];count=len(tasks)*len(selected)*body.attempts
            from .retries import retry_schema_ready
            if (body.api_retry or body.run_recovery) and not retry_schema_ready(repo):raise ValueError('explicit migrate-retries required')
            multiplier=1+(body.run_recovery.max_recoveries if body.run_recovery and body.run_recovery.enabled else 0)
            if count*multiplier>settings.max_batch_runs:raise ValueError('oversized batch including recovery reservation')
            if body.max_duration>settings.max_batch_duration or body.max_requests>settings.max_batch_requests:raise ValueError('server limit exceeded')
            if body.subset_id:
                subset=c.subset(body.subset_id,benchmark,body.subset_revision)
                if subset['archived'] or set(subset['task_ids'])!=set(body.task_ids):raise ValueError('subset mismatch')
            reserved=len(tasks)*body.attempts*sum(effective_profile(p,body.limits,body.reasoning.get(p.id),p.id in body.reasoning).max_model_calls for p in selected)*multiplier
            blocked=sum(not getattr(t,'environment_ready',True) or c.dataset_archived(t.dataset_version) for t in tasks)
            if reserved>body.max_requests:raise BatchRequestBudgetError(reserved,body.max_requests)
            maximum=max(min(t.time_limit,effective_profile(p,body.limits).max_evaluation_duration) for t in tasks for p in selected)
            return {'task_count':len(tasks),'ready_tasks':len(tasks)-blocked,'blocked_tasks':blocked,'model_count':len(selected),'total_attempts':count,'reserved_requests':reserved,'possible_recoveries':count*(multiplier-1),'api_attempt_multiplier':body.api_retry.max_attempts if body.api_retry and body.api_retry.enabled else 1,'maximum_run_seconds':maximum,'known_cost_estimate':None,'cost_notice':'实际输入长度与请求用量未知；不提供硬性费用上限','unknown_pricing':any(p.pricing is None for p in selected),'submittable':blocked==0,'models':[p.public() for p in selected]}
        return guard(calculate)

def _import_time(catalogue,revision):
    if not catalogue.path.exists():return None
    import sqlite3
    with sqlite3.connect(f'file:{catalogue.path}?mode=ro',uri=True) as db:return db.execute('SELECT max(imported_at) FROM instances WHERE revision=?',(revision,)).fetchone()[0]

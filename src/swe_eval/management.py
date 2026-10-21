"""Versioned server-owned configuration, explicit migrations and non-secret audit."""
import json,time,uuid,hashlib,sqlite3
from pathlib import Path
from .schema import ModelProfile
from .storage import Conflict
from .secret_store import SecretBox,SecretUnavailable
from .outbound import validate_url

DYNAMIC_FIELDS={'provider_id','provider_revision','configuration_revision','credential_version','display_name'}
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def fingerprint(value):return hashlib.sha256(encoded(value).encode()).hexdigest()
def administration_ready(repo):
    if not repo.path.exists():return False
    with repo.connect() as db:return db.execute('PRAGMA user_version').fetchone()[0]==3

def migrate_administration(repo):
    with repo.connect() as db:
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version==3:
            if db.execute("SELECT value FROM metadata WHERE key='admin_crypto_namespace'").fetchone() is None:raise RuntimeError('administration migration is incomplete')
            return
        if version!=2:raise RuntimeError('administration migration requires accepted schema 2')
        sql=(Path(__file__).parent/'migrations/003_management.sql').read_text().replace('__NAMESPACE__',uuid.uuid4().hex)
        try:db.executescript(sql)
        except BaseException:db.rollback();raise

class ConfigurationRepository:
    def __init__(self,repo,settings):self.repo,self.settings=repo,settings
    def require(self):
        if not administration_ready(self.repo):raise ValueError('administration schema unavailable; run the explicitly authorized migrate-admin command')
    @staticmethod
    def audit(db,action,kind,identity,revision=None,**detail):
        allowed={k:v for k,v in detail.items() if k in ('previous_revision','credential_version','task_count','status','job_id') and isinstance(v,(str,int,bool))}
        db.execute('INSERT INTO management_audit(at,action,object_type,object_id,revision,detail_json) VALUES(?,?,?,?,?,?)',(time.time(),action,kind,identity,revision,encoded(allowed)))
    @staticmethod
    def revision(db,kind,identity,revision=None):
        base,history,column={'provider':('managed_providers','provider_revisions','provider_id'),'model':('managed_models','model_revisions','model_id')}[kind]
        item=db.execute('SELECT * FROM '+base+' WHERE id=?',(identity,)).fetchone()
        if item is None:raise KeyError(identity)
        number=revision if revision is not None else item['current_revision']
        row=db.execute('SELECT payload_json FROM '+history+' WHERE '+column+'=? AND revision=?',(identity,number)).fetchone()
        if row is None:raise KeyError(identity)
        return json.loads(row[0]),number,dict(item)
    def provider(self,identity):
        self.require()
        with self.repo.connect() as db:
            p,revision,base=self.revision(db,'provider',identity)
            result=dict(p,revision=revision,created_at=base['created_at'],updated_at=base['updated_at'])
            version=p.get('credential_version');secret=db.execute('SELECT revoked FROM provider_credentials WHERE provider_id=? AND version=?',(identity,version)).fetchone() if version else None
            result['credential']={'configured':bool(version),'reference':'provider:'+identity+':v'+str(version) if version else None,'revoked':bool(secret and secret['revoked'])}
            result['models']=[row['id'] for row in db.execute('SELECT id,current_revision FROM managed_models') if self.revision(db,'model',row['id'])[0]['provider_id']==identity]
            result['recent_connection_errors']=[dict(x) for x in db.execute("SELECT at,status,error,configuration_revision FROM provider_connection_events WHERE provider_id=? AND status!='ok' ORDER BY seq DESC LIMIT 10",(identity,))]
            return result
    def providers(self):
        self.require()
        with self.repo.connect() as db:ids=[x[0] for x in db.execute('SELECT id FROM managed_providers ORDER BY created_at DESC LIMIT 500')]
        return [self.provider(x) for x in ids]
    def write_provider(self,body,*,create=False,action='provider_updated'):
        self.require();payload=body.model_dump(exclude={'api_key','expected_revision'});payload['base_url']=validate_url(body.base_url)
        with self.repo.connect(write=True) as db:
            exists=db.execute('SELECT 1 FROM managed_providers WHERE id=?',(body.id,)).fetchone()
            if create and exists:raise Conflict('provider ID already exists')
            if not create and not exists:raise KeyError(body.id)
            old,number=({},0) if create else self.revision(db,'provider',body.id)[:2]
            if not create and body.expected_revision!=number:raise Conflict('provider revision changed; refresh before saving')
            number+=1;version=old.get('credential_version');now=time.time()
            if create:db.execute('INSERT INTO managed_providers VALUES(?,?,?,?)',(body.id,number,now,now))
            if body.api_key is not None:
                version=db.execute('SELECT coalesce(max(version),0)+1 FROM provider_credentials WHERE provider_id=?',(body.id,)).fetchone()[0]
                box=SecretBox();namespace=db.execute("SELECT value FROM metadata WHERE key='admin_crypto_namespace'").fetchone()[0]
                sealed=box.seal(body.api_key.get_secret_value(),encoded([namespace,body.id,version]))
                db.execute('INSERT INTO provider_credentials VALUES(?,?,?,?,?,?)',(body.id,version,sealed,box.key_id,0,now))
            if body.enabled and not body.archived and not (version or body.allow_no_api_key):raise ValueError('enabled provider requires a server-side credential or explicit no-key mode')
            payload['credential_version']=version
            db.execute('INSERT INTO provider_revisions VALUES(?,?,?,?)',(body.id,number,encoded(payload),now))
            db.execute('UPDATE managed_providers SET current_revision=?,updated_at=? WHERE id=?',(number,now,body.id))
            self.audit(db,'provider_created' if create else action,'provider',body.id,number,previous_revision=number-1,credential_version=version or 0)
        return self.provider(body.id)
    def revoke(self,identity,version):
        self.require()
        with self.repo.connect(write=True) as db:
            self.revision(db,'provider',identity)
            changed=db.execute('UPDATE provider_credentials SET revoked=1 WHERE provider_id=? AND version=?',(identity,version))
            if not changed.rowcount:raise KeyError(identity)
            self.audit(db,'credential_revoked','provider',identity,credential_version=version)
        return {'status':'revoked','credential_version':version}
    def secret(self,identity,version):
        if version is None:return ''
        self.require()
        with self.repo.connect() as db:
            row=db.execute('SELECT * FROM provider_credentials WHERE provider_id=? AND version=?',(identity,version)).fetchone()
            if row is None or row['revoked']:raise SecretUnavailable('provider credential is revoked or unavailable')
            namespace=db.execute("SELECT value FROM metadata WHERE key='admin_crypto_namespace'").fetchone()[0]
            return SecretBox().open(row['sealed'],encoded([namespace,identity,version]),row['key_id'])
    def profile_at(self,identity,model_revision=None,provider_revision=None,*,enabled=False,db=None):
        if db is None:
            with self.repo.connect() as connection:return self.profile_at(identity,model_revision,provider_revision,enabled=enabled,db=connection)
        m,mrev,_=self.revision(db,'model',identity,model_revision);p,prev,_=self.revision(db,'provider',m['provider_id'],provider_revision)
        if enabled and (not m['enabled'] or m['archived'] or not p['enabled'] or p['archived']):raise ValueError('provider or model is disabled or archived')
        version=p.get('credential_version')
        if enabled and version:
            key=db.execute('SELECT revoked,key_id FROM provider_credentials WHERE provider_id=? AND version=?',(m['provider_id'],version)).fetchone()
            if key is None or key['revoked']:raise SecretUnavailable('provider credential is revoked or unavailable')
            if key['key_id']!=SecretBox().key_id:raise SecretUnavailable('credential master key does not match')
        values={k:v for k,v in m.items() if k in ModelProfile.model_fields}
        values.update(base_url=p['base_url'],allow_http=p['base_url'].startswith('http://'),allow_no_api_key=p['allow_no_api_key'],provider_id=m['provider_id'],provider_revision=prev,configuration_revision=mrev,credential_version=version,upstream_verified=False,request_timeout=min(m['request_timeout'],p['request_timeout']))
        return ModelProfile.model_validate(values)
    def enabled_profiles(self):
        if not administration_ready(self.repo):return {}
        with self.repo.connect() as db:
            result={}
            for row in db.execute('SELECT id FROM managed_models'):
                try:result[row[0]]=self.profile_at(row[0],enabled=True,db=db)
                except (ValueError,KeyError):pass
            return result
    def write_model(self,body,*,create=False):
        self.require();payload=body.model_dump(exclude={'expected_revision'})
        from .config import load_models
        if body.id in load_models(self.settings.models_file):raise Conflict('profile ID belongs to a read-only file profile')
        with self.repo.connect(write=True) as db:
            self.revision(db,'provider',body.provider_id)
            exists=db.execute('SELECT 1 FROM managed_models WHERE id=?',(body.id,)).fetchone()
            if create and exists:raise Conflict('profile ID already exists')
            if not create and not exists:raise KeyError(body.id)
            number=0 if create else self.revision(db,'model',body.id)[1]
            if not create and body.expected_revision!=number:raise Conflict('model revision changed; refresh before saving')
            number+=1;now=time.time()
            if create:db.execute('INSERT INTO managed_models VALUES(?,?,?,?)',(body.id,number,now,now))
            db.execute('INSERT INTO model_revisions VALUES(?,?,?,?)',(body.id,number,encoded(payload),now))
            db.execute('UPDATE managed_models SET current_revision=?,updated_at=? WHERE id=?',(number,now,body.id))
            self.audit(db,'model_created' if create else 'model_updated','model',body.id,number,previous_revision=number-1)
        return self.model(body.id)
    def model(self,identity):
        self.require()
        with self.repo.connect() as db:
            m,revision,base=self.revision(db,'model',identity)
            result=dict(m,revision=revision,created_at=base['created_at'],updated_at=base['updated_at'],source='database',upstream_verified=False)
            try:result['effective_configuration']=self.profile_at(identity,enabled=True,db=db).public();result['runnable']=True
            except (ValueError,KeyError):result['effective_configuration']=None;result['runnable']=False
            return result
    def models(self):
        self.require()
        with self.repo.connect() as db:ids=[row[0] for row in db.execute('SELECT id FROM managed_models ORDER BY created_at DESC LIMIT 500')]
        return [self.model(x) for x in ids]
    def history(self,kind,identity):
        self.require();table,column={'provider':('provider_revisions','provider_id'),'model':('model_revisions','model_id')}[kind]
        with self.repo.connect() as db:
            self.revision(db,kind,identity)
            return [dict(json.loads(row['payload_json']),revision=row['revision'],created_at=row['created_at']) for row in db.execute('SELECT * FROM '+table+' WHERE '+column+'=? ORDER BY revision DESC',(identity,))]
    def connection_event(self,identity,revision,status,error=None):
        with self.repo.connect(write=True) as db:
            db.execute('INSERT INTO provider_connection_events(provider_id,at,configuration_revision,status,error) VALUES(?,?,?,?,?)',(identity,time.time(),revision,status,error))
            self.audit(db,'provider_connection_test','provider',identity,revision,status=status)
    def write_subset(self,body,benchmark,*,create=False):
        self.require()
        for task_id in body.task_ids:benchmark.get_task(task_id)
        with self.repo.connect(write=True) as db:
            old=db.execute('SELECT * FROM benchmark_subsets WHERE id=?',(body.id,)).fetchone()
            if create and old:raise Conflict('subset ID already exists')
            if not create and old is None:raise KeyError(body.id)
            if old and (old['archived'] or old['current_revision']!=body.expected_revision):raise Conflict('subset is archived or revision changed')
            revision=old['current_revision']+1 if old else 1;now=time.time()
            identity=fingerprint({'id':body.id,'revision':revision,'tasks':body.task_ids})
            if old:db.execute('UPDATE benchmark_subsets SET current_revision=?,updated_at=? WHERE id=?',(revision,now,body.id))
            else:db.execute('INSERT INTO benchmark_subsets VALUES(?,?,?,?,?)',(body.id,revision,0,now,now))
            db.execute('INSERT INTO subset_revisions VALUES(?,?,?,?,?,?)',(body.id,revision,body.name,encoded(body.task_ids),identity,now));self.audit(db,'subset_revision_created','subset',body.id,revision,task_count=len(body.task_ids))
        return self.subset(body.id,benchmark)
    def subset(self,identity,benchmark,revision=None):
        self.require()
        with self.repo.connect() as db:
            base=db.execute('SELECT * FROM benchmark_subsets WHERE id=?',(identity,)).fetchone()
            if base is None:raise KeyError(identity)
            row=db.execute('SELECT * FROM subset_revisions WHERE subset_id=? AND revision=?',(identity,revision or base['current_revision'])).fetchone()
            if row is None:raise KeyError(identity)
            item=dict(row);item['task_ids']=json.loads(item.pop('task_ids_json'));item.update(archived=bool(base['archived']),id=identity)
        tasks=[benchmark.get_task(x) for x in item['task_ids']];item['ready_tasks']=sum(getattr(t,'environment_ready',True) for t in tasks);item['blocked_tasks']=len(tasks)-item['ready_tasks'];item['task_count']=len(tasks)
        return item
    def subsets(self,benchmark):
        self.require()
        with self.repo.connect() as db:ids=[row[0] for row in db.execute('SELECT id FROM benchmark_subsets ORDER BY created_at DESC LIMIT 500')]
        return [self.subset(x,benchmark) for x in ids]
    def archive_subset(self,identity,expected):
        self.require()
        with self.repo.connect(write=True) as db:
            row=db.execute('SELECT * FROM benchmark_subsets WHERE id=?',(identity,)).fetchone()
            if row is None:raise KeyError(identity)
            if row['current_revision']!=expected:raise Conflict('subset revision changed')
            db.execute('UPDATE benchmark_subsets SET archived=1,updated_at=? WHERE id=?',(time.time(),identity));self.audit(db,'subset_archived','subset',identity,expected)
        return {'status':'archived'}
    def dataset_archived(self,revision):
        if not administration_ready(self.repo):return False
        with self.repo.connect() as db:
            row=db.execute('SELECT archived FROM dataset_states WHERE revision=?',(revision,)).fetchone();return bool(row and row[0])
    def archive_dataset(self,revision,archived):
        self.require()
        with self.repo.connect(write=True) as db:
            db.execute('INSERT INTO dataset_states VALUES(?,?,?) ON CONFLICT(revision) DO UPDATE SET archived=excluded.archived,updated_at=excluded.updated_at',(revision,int(archived),time.time()));self.audit(db,'dataset_archived' if archived else 'dataset_restored','dataset',revision)
        return {'revision':revision,'archived':archived}
    def audit_events(self,limit,offset):
        self.require()
        with self.repo.connect() as db:
            total=db.execute('SELECT count(*) FROM management_audit').fetchone()[0];rows=[dict(x) for x in db.execute('SELECT * FROM management_audit ORDER BY seq DESC LIMIT ? OFFSET ?',(limit,offset))]
        for row in rows:row['detail']=json.loads(row.pop('detail_json'))
        return {'items':rows,'total':total}

def current_profiles(settings,repo=None):
    from .config import load_models
    from .storage import SQLiteRepository
    result=load_models(settings.models_file);result.update(ConfigurationRepository(repo or SQLiteRepository(settings.database),settings).enabled_profiles());return result

def bound_profiles(settings,repo,record):
    model=record['model']
    if not model.get('provider_id'):
        from .config import load_models
        return load_models(settings.models_file)
    profile=ConfigurationRepository(repo,settings).profile_at(model['id'],model['configuration_revision'],model['provider_revision'])
    if profile.provider_id!=model['provider_id'] or profile.credential_version!=model['credential_version']:raise ValueError('immutable provider binding mismatch')
    return {profile.id:profile}

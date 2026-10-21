"""Durable bounded administrative jobs owned by the existing worker lease."""
import json,os,time,uuid
from types import SimpleNamespace
from .management import administration_ready,encoded,ConfigurationRepository
from .storage import Conflict
TERMINAL={'completed','failed','timeout','cancelled'}
class AdministrativeJobs:
    def __init__(self,repo,settings):self.repo,self.settings=repo,settings
    def get(self,identity):
        with self.repo.connect() as db:row=db.execute('SELECT * FROM administration_jobs WHERE id=?',(identity,)).fetchone()
        if row is None:raise KeyError(identity)
        item=dict(row)
        for key in ('payload','progress','result'):item[key]=json.loads(item.pop(key+'_json')) if item[key+'_json'] else None
        item.pop('owner');return item
    def list(self):
        if not administration_ready(self.repo):return []
        with self.repo.connect() as db:ids=[r[0] for r in db.execute('SELECT id FROM administration_jobs ORDER BY created_at DESC LIMIT 100')]
        return [self.get(x) for x in ids]
    def create(self,body,benchmark):
        ConfigurationRepository(self.repo,self.settings).require()
        if body.kind=='environment_validation':
            for identity in body.instance_ids:
                benchmark.catalogue.private(body.revision,identity)
        payload=body.model_dump();raw=encoded(payload);now=time.time();identity=uuid.uuid4().hex
        with self.repo.connect(write=True) as db:
            prior=db.execute('SELECT id,payload_json FROM administration_jobs WHERE idempotency_key=?',(body.idempotency_key,)).fetchone()
            if prior:
                if prior['payload_json']!=raw:raise Conflict('idempotency key reused with different parameters')
                identity=prior['id']
            else:
                if db.execute("SELECT count(*) FROM administration_jobs WHERE state IN ('queued','running')").fetchone()[0]>=10:raise Conflict('administrative queue limit reached')
                db.execute('INSERT INTO administration_jobs(id,kind,payload_json,idempotency_key,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(identity,body.kind,raw,body.idempotency_key,'queued',now,now))
                ConfigurationRepository.audit(db,'administrative_job_created','job',identity,job_id=identity)
        return self.get(identity)
    def cancel(self,identity):
        with self.repo.connect(write=True) as db:
            row=db.execute('SELECT state FROM administration_jobs WHERE id=?',(identity,)).fetchone()
            if row is None:raise KeyError(identity)
            if row[0] not in TERMINAL:
                now=time.time();queued=row[0]=='queued'
                db.execute('UPDATE administration_jobs SET cancel_requested=1,state=?,finished_at=?,updated_at=? WHERE id=?',('cancelled' if queued else row[0],now if queued else None,now,identity));ConfigurationRepository.audit(db,'administrative_job_cancelled','job',identity)
        return self.get(identity)
    def recover(self,owner):
        if not administration_ready(self.repo):return
        with self.repo.connect(write=True) as db:
            self.repo._check_owner(db,owner)
            db.execute("UPDATE administration_jobs SET state='failed',error='worker_interrupted_no_automatic_retry',finished_at=?,updated_at=? WHERE state='running'",(time.time(),time.time()))
    def claim(self,owner):
        if not administration_ready(self.repo):return None
        with self.repo.connect(write=True) as db:
            self.repo._check_owner(db,owner)
            row=db.execute("SELECT id FROM administration_jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:return None
            db.execute("UPDATE administration_jobs SET state='running',owner=?,started_at=?,updated_at=? WHERE id=?",(owner,time.time(),time.time(),row[0]));identity=row[0]
        return self.get(identity)
    def finish(self,identity,owner,state,result=None,error=None):
        with self.repo.connect(write=True) as db:
            self.repo._check_owner(db,owner)
            row=db.execute('SELECT state,owner,cancel_requested FROM administration_jobs WHERE id=?',(identity,)).fetchone()
            if row is None or row['state']!='running' or row['owner']!=owner:raise Conflict('stale administrative writer')
            if row['cancel_requested']:state='cancelled';result=None
            db.execute('UPDATE administration_jobs SET state=?,result_json=?,error=?,finished_at=?,updated_at=? WHERE id=?',(state,encoded(result) if result is not None else None,error,time.time(),time.time(),identity))
    def progress(self,identity,owner,value):
        with self.repo.connect(write=True) as db:
            self.repo._check_owner(db,owner)
            row=db.execute('SELECT state,owner,cancel_requested FROM administration_jobs WHERE id=?',(identity,)).fetchone()
            if not row or row['state']!='running' or row['owner']!=owner or row['cancel_requested']:raise Conflict('administrative job cancelled or stale')
            db.execute('UPDATE administration_jobs SET progress_json=?,updated_at=? WHERE id=?',(encoded(value),time.time(),identity))

def execute_administrative_job(settings,identity,owner):
    os.setsid()
    from .service import repository
    from .benchmarks.official import Catalogue
    from .official_harness import OfficialHarness
    from .dataset_validation import validate
    from .sandbox import Cancelled
    repo=repository(settings);jobs=AdministrativeJobs(repo,settings);item=jobs.get(identity);p=item['payload']
    def check():
        current=jobs.get(identity)
        with repo.connect() as db:repo._check_owner(db,owner)
        if current['state']!='running' or current['cancel_requested']:raise Cancelled('administrative job cancelled')
    try:
        if p['kind']=='dataset_import':
            result=OfficialHarness(settings).import_dataset(p['revision'])
            check();safe={k:result[k] for k in ('dataset','revision','records','inserted','images_prepared') if k in result}
        else:
            args=SimpleNamespace(timeout=p['timeout'],revision=p['revision'],repo=None,status=None,subset=None,instance=p['instance_ids'],limit=5,resume=False,dry_run=False,prepare=p['prepare'],continue_on_error=True)
            def progress(x):jobs.progress(identity,owner,x)
            result=validate(settings,args,check=check,service_id=repo.service_id,run_id=identity,progress=progress)
            safe={'items':[{'instance_id':x['instance_id'],'status':x['status'],'image_digest':x.get('image_digest'),'gold_classification':x.get('gold',{}).get('classification'),'negative_classification':x.get('negative',{}).get('classification')} for x in result['items']]}
        jobs.finish(identity,owner,'completed',safe)
    except Cancelled:jobs.finish(identity,owner,'cancelled',error='administrative_job_cancelled')
    except Conflict:return
    except Exception:jobs.finish(identity,owner,'failed',error='administrative_execution_error; inspect private validation evidence')

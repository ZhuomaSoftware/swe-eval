"""Phase 2.7 permanent regressions against real SQLite and authenticated HTTP."""
import base64,json,os,socket,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from swe_eval.api import create_app
from swe_eval.config import Settings,resolve_key
from swe_eval.schema import ModelProfile,Metrics
from swe_eval.service import repository,enqueue,model_snapshot
from swe_eval.management import ConfigurationRepository,migrate_administration,bound_profiles,current_profiles
from swe_eval.management_schema import ProviderWrite,ManagedModelWrite,SubsetWrite,AdministrationJob
from swe_eval.secret_store import SecretBox,SecretUnavailable
from swe_eval.outbound import validate_url,resolve_target,OutboundDenied,request_json
from swe_eval.storage import Conflict
from swe_eval.benchmarks.official import TaskRegistry
from swe_eval.administration_jobs import AdministrativeJobs

class ManagementTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.models=self.root/'models.json';self.models.write_text('[]')
  self.env=patch.dict(os.environ,{'SWE_CONFIG_MASTER_KEY':base64.b64encode(bytes(range(32))).decode(),'SWE_APPROVED_PROVIDER_ORIGINS':'http://127.0.0.1:18991'});self.env.start()
  self.settings=Settings(self.root,self.models,admin_token='management-test-admin-token-123456',public_origin='http://testserver',cookie_secure=False)
  self.repo=repository(self.settings);migrate_administration(self.repo);self.c=ConfigurationRepository(self.repo,self.settings);self.b=TaskRegistry(self.settings)
  self.client=TestClient(create_app(self.settings));self.headers={'Authorization':'Bearer '+self.settings.admin_token}
 def tearDown(self):self.client.close();self.env.stop();self.tmp.cleanup()
 def provider(self,**extra):return self.c.write_provider(ProviderWrite(id='gateway',display_name='Local gateway',base_url='http://127.0.0.1:18991/v1',api_key='canary-private-secret-9f32a0',**extra),create=True)
 def model(self,**extra):return self.c.write_model(ManagedModelWrite(id='dynamic',display_name='Dynamic model',provider_id='gateway',model_id='same-alias',upstream_id='unverified-gateway',**extra),create=True)
 def test_explicit_migration_and_idempotency(self):
  with self.repo.connect() as db:before=db.execute("SELECT value FROM metadata WHERE key='admin_crypto_namespace'").fetchone()[0]
  migrate_administration(self.repo);repository(self.settings)
  with self.repo.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3);self.assertEqual(before,db.execute("SELECT value FROM metadata WHERE key='admin_crypto_namespace'").fetchone()[0])
 def test_failed_migration_rolls_back_and_preserves_accepted_records(self):
  import sqlite3
  from dataclasses import replace
  old=repository(replace(self.settings,data_dir=self.root/'migration-failure'))
  task=self.b.get_task('intervals-001');profile=ModelProfile(id='legacy-file',upstream_id='old',model_id='old',base_url='https://example.com/v1',allow_no_api_key=True)
  run=old.create(task.model_dump(mode='json'),model_snapshot(profile));before=old.get(run['id'])
  with patch('swe_eval.management.Path.read_text',return_value='BEGIN IMMEDIATE;CREATE TABLE partial(x);INSERT INTO missing_table VALUES(1);COMMIT;'):
   with self.assertRaises(sqlite3.OperationalError):migrate_administration(old)
  with old.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2);self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone())
  migrate_administration(old);self.assertEqual(old.get(run['id']),before)
 def test_configuration_read_does_not_create_a_database(self):
  from dataclasses import replace
  fresh=replace(self.settings,data_dir=self.root/'not-initialized');self.assertEqual(current_profiles(fresh),{});self.assertFalse(fresh.database.exists())
 def test_core_schema_does_not_implicitly_migrate(self):
  from dataclasses import replace
  old=repository(replace(self.settings,data_dir=self.root/'old'))
  with old.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
 def test_encryption_aad_tamper_and_wrong_key(self):
  box=SecretBox();sealed=box.seal('sensitive','binding');self.assertNotIn(b'sensitive',sealed);self.assertEqual(box.open(sealed,'binding',box.key_id),'sensitive')
  for data,aad in ((sealed,'other'),(sealed[:-1]+bytes([sealed[-1]^1]),'binding')):
   with self.assertRaises(SecretUnavailable):box.open(data,aad,box.key_id)
  with patch.dict(os.environ,{'SWE_CONFIG_MASTER_KEY':base64.b64encode(b'x'*32).decode()}):
   with self.assertRaises(SecretUnavailable):SecretBox().open(sealed,'binding',box.key_id)
 def test_no_master_key_fails_closed_and_rolls_back(self):
  with patch.dict(os.environ,{'SWE_CONFIG_MASTER_KEY':''}):
   with self.assertRaises(SecretUnavailable):self.provider()
  self.assertEqual(self.c.providers(),[])
 def test_secret_never_in_responses_history_audit_or_database(self):
  self.provider();self.model();self.assertEqual(self.c.secret('gateway',1),'canary-private-secret-9f32a0')
  for route in ('providers','providers/gateway/history','models','models/dynamic/history','audit'):
   r=self.client.get('/api/v1/manage/'+route,headers=self.headers);self.assertEqual(r.status_code,200);self.assertNotIn('canary-private-secret',r.text)
  with self.repo.connect() as db:
   for row in db.iterdump():self.assertNotIn('canary-private-secret',row)
 def test_revision_cas(self):
  self.provider();body=ProviderWrite(id='gateway',display_name='Changed',base_url='http://127.0.0.1:18991/v1',expected_revision=1)
  self.assertEqual(self.c.write_provider(body)['revision'],2)
  with self.assertRaises(Conflict):self.c.write_provider(body)
 def test_rotation_preserves_queued_binding_and_revocation_fails_closed(self):
  self.provider();self.model();profiles=current_profiles(self.settings,self.repo);run=enqueue(self.repo,self.b,profiles,'intervals-001','dynamic')
  self.c.write_provider(ProviderWrite(id='gateway',display_name='Changed',base_url='http://127.0.0.1:18991/v1',api_key='new-private-secret',expected_revision=1))
  old=bound_profiles(self.settings,self.repo,run)['dynamic'];new=current_profiles(self.settings,self.repo)['dynamic']
  self.assertEqual(old.provider_revision,1);self.assertEqual(new.provider_revision,2);self.assertEqual(resolve_key(old,self.settings),'canary-private-secret-9f32a0');self.assertEqual(resolve_key(new,self.settings),'new-private-secret')
  self.c.revoke('gateway',1)
  with self.assertRaises(SecretUnavailable):resolve_key(old,self.settings)
 def test_model_edit_only_new_runs_and_disable(self):
  self.provider();self.model();old=enqueue(self.repo,self.b,current_profiles(self.settings,self.repo),'intervals-001','dynamic')
  self.c.write_model(ManagedModelWrite(id='dynamic',display_name='Edited',provider_id='gateway',model_id='different-alias',upstream_id='unverified-gateway',expected_revision=1))
  self.assertEqual(bound_profiles(self.settings,self.repo,old)['dynamic'].model_id,'same-alias');self.assertEqual(current_profiles(self.settings,self.repo)['dynamic'].model_id,'different-alias')
  self.c.write_provider(ProviderWrite(id='gateway',display_name='Disabled',base_url='http://127.0.0.1:18991/v1',enabled=False,expected_revision=1))
  self.assertNotIn('dynamic',current_profiles(self.settings,self.repo));self.assertEqual(bound_profiles(self.settings,self.repo,old)['dynamic'].provider_revision,1)
 def test_legacy_snapshot_hash_unchanged(self):
  import hashlib
  p=ModelProfile(id='file',upstream_id='file',model_id='alias',base_url='https://example.com/v1',allow_no_api_key=True)
  old=p.model_dump_json(exclude={'provider_id','provider_revision','configuration_revision','credential_version','display_name'})
  self.assertEqual(model_snapshot(p)['configuration_hash'],hashlib.sha256(old.encode()).hexdigest());self.assertNotIn('provider_id',p.public())
 def test_auth_and_csrf_management(self):
  for path in ('providers','models','datasets','subsets','audit','jobs','tasks'):
   self.assertEqual(self.client.get('/api/v1/manage/'+path).status_code,401)
  self.assertEqual(self.client.post('/api/v1/manage/providers',json={}).status_code,401)
 def test_validation_errors_do_not_echo_key(self):
  r=self.client.post('/api/v1/manage/providers',headers=self.headers,json={'api_key':'canary-private-secret','id':'!!','base_url':'oops','display_name':'x'})
  self.assertEqual(r.status_code,422);self.assertNotIn('canary-private-secret',r.text)
 def test_subset_revisions_membership_immutable(self):
  first=self.c.write_subset(SubsetWrite(id='regression',name='First',task_ids=['intervals-001']),self.b,create=True)
  self.c.write_subset(SubsetWrite(id='regression',name='Second',task_ids=['intervals-001'],expected_revision=1),self.b)
  self.assertEqual(self.c.subset('regression',self.b,1)['name'],'First');self.assertNotEqual(first['fingerprint'],self.c.subset('regression',self.b)['fingerprint'])
  self.c.archive_subset('regression',2)
  with self.assertRaises(Conflict):self.c.write_subset(SubsetWrite(id='regression',name='Third',task_ids=['intervals-001'],expected_revision=2),self.b)
 def test_dataset_archive_rejects_new_submission(self):
  self.provider();self.model();self.c.archive_dataset(self.b.get_task('intervals-001').dataset_version,True)
  r=self.client.post('/api/v1/runs',headers=self.headers,json={'task_id':'intervals-001','model_profile_id':'dynamic'});self.assertEqual(r.status_code,422)
 def test_batch_preview_limits_and_subset_binding(self):
  self.provider();self.model();self.c.write_subset(SubsetWrite(id='regression',name='Suite',task_ids=['intervals-001']),self.b,create=True)
  body=dict(name='Bound',task_ids=['intervals-001'],model_profile_ids=['dynamic'],subset_id='regression',subset_revision=1,idempotency_key='preview-123456')
  r=self.client.post('/api/v1/manage/batch-preview',headers=self.headers,json=body);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['total_attempts'],1);self.assertIsNone(r.json()['known_cost_estimate'])
  result=self.client.post('/api/v1/batches',headers=self.headers,json=body);self.assertEqual(result.status_code,202,result.text)
  record=self.repo.get(result.json()['attempts'][0]['run_id']);self.assertEqual(record['snapshot']['selected_subset']['revision'],1)
 def test_phase26_idempotency_survives_optional_fields_and_disabled_profile(self):
  from swe_eval.center_schema import BatchSubmission
  from swe_eval.center import snapshot,submit_batch
  self.provider();self.model();p=current_profiles(self.settings,self.repo)['dynamic'];task=self.b.get_task('intervals-001')
  body=BatchSubmission(name='Historical request',task_ids=[task.id],model_profile_ids=[p.id],idempotency_key='old-phase26-request')
  legacy=body.model_dump(mode='json',exclude={'subset_id','subset_revision'});old=self.repo.create_batch(legacy,[(task.model_dump(mode='json'),model_snapshot(p),snapshot(task,p),1)],200,15)
  self.c.write_provider(ProviderWrite(id='gateway',display_name='Disabled',base_url='http://127.0.0.1:18991/v1',enabled=False,expected_revision=1));self.assertEqual(current_profiles(self.settings,self.repo),{})
  response=self.client.post('/api/v1/batches',headers=self.headers,json=body.model_dump(mode='json'));self.assertEqual(response.status_code,202,response.text);self.assertEqual(response.json()['id'],old['id'])
  replay=submit_batch(self.repo,self.b,{},body,self.settings);self.assertEqual(replay['id'],old['id']);self.assertEqual(len(self.repo.list()),1)
  with self.assertRaises(Conflict):submit_batch(self.repo,self.b,{},body.model_copy(update={'name':'Changed'}),self.settings)
 def test_job_durability_replay_terminal_cancellation_stale_writer(self):
  jobs=AdministrativeJobs(self.repo,self.settings);body=AdministrationJob(kind='dataset_import',revision='a'*40,idempotency_key='job-12345678')
  first=jobs.create(body,self.b);self.assertEqual(jobs.create(body,self.b)['id'],first['id']);jobs.cancel(first['id']);self.assertEqual(jobs.cancel(first['id'])['state'],'cancelled')
  with self.assertRaises(Conflict):jobs.create(body.model_copy(update={'revision':'b'*40}),self.b)
  new=jobs.create(body.model_copy(update={'idempotency_key':'job-new-123456'}),self.b);self.repo.acquire('owner',90);jobs.claim('owner');jobs.finish(new['id'],'owner','completed',{'safe':True});self.assertEqual(jobs.cancel(new['id'])['state'],'completed')
  with self.assertRaises(Conflict):jobs.finish(new['id'],'owner','failed')
 def test_running_administrative_cancel_wins_over_late_success(self):
  jobs=AdministrativeJobs(self.repo,self.settings);job=jobs.create(AdministrationJob(kind='dataset_import',revision='a'*40,idempotency_key='running-cancel-1234'),self.b)
  self.repo.acquire('owner',90);jobs.claim('owner');jobs.cancel(job['id']);jobs.finish(job['id'],'owner','completed',{'items':['late']})
  self.assertEqual(jobs.get(job['id'])['state'],'cancelled');self.assertIsNone(jobs.get(job['id'])['result'])
 def test_worker_recovery_never_reexecutes_administrative_job(self):
  jobs=AdministrativeJobs(self.repo,self.settings);j=jobs.create(AdministrationJob(kind='dataset_import',revision='a'*40,idempotency_key='job-recover-1234'),self.b)
  self.repo.acquire('owner',90);jobs.claim('owner');jobs.recover('owner');self.assertEqual(jobs.get(j['id'])['state'],'failed');self.assertIsNone(jobs.claim('owner'))
 def test_mixed_currencies_cannot_be_summed(self):
  self.provider();self.model();run=enqueue(self.repo,self.b,current_profiles(self.settings,self.repo),'intervals-001','dynamic')
  other=json.loads(json.dumps(run));other['id']='other';other['metrics'].update(cost=3,currency='CNY');run['metrics'].update(cost=1,currency='USD')
  from swe_eval.analytics import summary
  result=summary([run,other]);self.assertIsNone(result['total_cost']);self.assertIsNone(result['known_cost_subtotal']);self.assertTrue(result['mixed_currencies']);self.assertEqual(result['known_cost_by_currency'],{'USD':1,'CNY':3})
 def test_export_csv_preserves_currency_and_valid_structure(self):
  import csv,io
  self.provider();self.model();run=enqueue(self.repo,self.b,current_profiles(self.settings,self.repo),'intervals-001','dynamic')
  with self.repo.connect(write=True) as db:
   m=run['metrics'];m.update(cost=1.25,currency='CNY');db.execute('UPDATE runs SET metrics_json=? WHERE id=?',(json.dumps(m),run['id']))
  response=self.client.get('/api/v1/comparison/export?format=csv',headers=self.headers);self.assertEqual(response.status_code,200)
  rows=list(csv.DictReader(io.StringIO(response.text)));self.assertEqual(rows[0]['currency'],'CNY');self.assertEqual(rows[0]['total_cost'],'1.25');self.assertEqual(rows[0]['mixed_currencies'],'False')
 def test_missing_worker_metrics_do_not_claim_health(self):
  r=self.client.get('/api/v1/system',headers=self.headers);self.assertFalse(r.json()['worker_ready'])
 def test_model_discovery_requires_admin_and_same_origin_csrf(self):
  self.provider();path='/api/v1/manage/providers/gateway/discover-models'
  self.assertEqual(self.client.post(path).status_code,401)
  from swe_eval.sessions import issue,COOKIE
  token,csrf,_=issue(self.repo);self.client.cookies.set(COOKIE,token)
  with patch('swe_eval.management_api.request_json',return_value={'data':[{'id':'model-a'}]}) as transport:
   self.assertEqual(self.client.post(path).status_code,403)
   transport.assert_not_called()
   self.assertEqual(self.client.post(path,headers={'Origin':'http://testserver','X-CSRF-Token':csrf}).status_code,200)
 def test_model_discovery_sanitizes_metadata_and_never_creates_profiles(self):
  self.provider();secret='canary-private-secret-9f32a0'
  values={'data':[{'id':'model-b','api_key':secret,'owned_by':self.settings.admin_token},{'id':'model-a'},{'id':'model-a'},{'id':secret},{'id':'bad\nmodel'},{'id':'<script>alert(1)</script>'},{'id':'x'*201},{'id':5},'invalid',{}],'private':secret}
  with patch('swe_eval.management_api.request_json',return_value=values) as transport:
   response=self.client.post('/api/v1/manage/providers/gateway/discover-models',headers=self.headers)
  self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['items'],[{'id':'model-a'},{'id':'model-b'}]);self.assertFalse(response.json()['inference_performed']);self.assertEqual(response.json()['provider_revision'],1)
  self.assertNotIn(secret,response.text);self.assertNotIn(self.settings.admin_token,response.text);self.assertNotIn('owned_by',response.text);self.assertEqual(self.c.models(),[])
  transport.assert_called_once_with('http://127.0.0.1:18991/v1/models',secret,timeout=5)
 def test_model_discovery_disabled_provider_never_contacts_upstream(self):
  self.provider(enabled=False)
  with patch('swe_eval.management_api.request_json') as transport:
   self.assertEqual(self.client.post('/api/v1/manage/providers/gateway/discover-models',headers=self.headers).status_code,409);transport.assert_not_called()
 def test_model_discovery_failure_never_echoes_upstream_or_credentials(self):
  from swe_eval.providers import ProviderError
  self.provider();path='/api/v1/manage/providers/gateway/discover-models'
  for values in ({'bad':'private'},{'data':'private'}):
   with patch('swe_eval.management_api.request_json',return_value=values):self.assertEqual(self.client.post(path,headers=self.headers).status_code,502)
  with patch('swe_eval.management_api.request_json',side_effect=ProviderError('canary-private-secret-9f32a0')):
   response=self.client.post(path,headers=self.headers);self.assertEqual(response.status_code,502);self.assertNotIn('canary-private-secret',response.text)
  self.assertNotIn('canary-private-secret',json.dumps(self.c.provider('gateway')['recent_connection_errors']))
 def test_model_discovery_revoked_credential_fails_closed(self):
  self.provider();self.c.revoke('gateway',1)
  with patch('swe_eval.management_api.request_json') as transport:
   self.assertEqual(self.client.post('/api/v1/manage/providers/gateway/discover-models',headers=self.headers).status_code,502);transport.assert_not_called()
 def test_model_discovery_bounds_and_reports_truncated_unique_ids(self):
  self.provider()
  with patch('swe_eval.management_api.request_json',return_value={'data':[{'id':f'model-{n:04d}'} for n in range(501)]}):
   result=self.client.post('/api/v1/manage/providers/gateway/discover-models',headers=self.headers).json()
  self.assertEqual(len(result['items']),500);self.assertEqual(result['total'],501);self.assertTrue(result['truncated'])
 def test_batch_request_budget_explains_effective_reservation_without_creating_jobs(self):
  self.provider();self.model();body={'name':'Budget validation','task_ids':['intervals-001'],'model_profile_ids':['dynamic'],'attempts':2,'limits':{'timeout':600,'steps':15,'requests':20,'output_tokens':5120,'total_tokens':300000},'max_requests':1,'idempotency_key':'budget-reservation-explanation'}
  for path in ('/api/v1/manage/batch-preview','/api/v1/batches'):
   r=self.client.post(path,json=body,headers=self.headers);self.assertEqual(r.status_code,422,r.text);self.assertIn('30',r.json()['detail']);self.assertIn('当前为 1',r.json()['detail']);self.assertNotIn('canary-private-secret',r.text)
  self.assertEqual(self.repo.list(),[])
  r=self.client.post('/api/v1/manage/batch-preview',json={**body,'max_requests':30},headers=self.headers);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['reserved_requests'],30);self.assertEqual(r.json()['maximum_run_seconds'],300);self.assertEqual(self.repo.list(),[])
 def test_batch_request_budget_uses_each_model_cap_and_preserves_server_ceiling(self):
  self.provider();self.model();self.c.write_model(ManagedModelWrite(id='second',display_name='Second',provider_id='gateway',model_id='alias2',upstream_id='gateway',max_model_calls=5),create=True)
  body={'name':'Independent request caps','task_ids':['intervals-001'],'model_profile_ids':['dynamic','second'],'attempts':2,'max_requests':40,'limits':{'requests':20},'idempotency_key':'budget-per-profile-cap'}
  r=self.client.post('/api/v1/manage/batch-preview',json=body,headers=self.headers);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['reserved_requests'],2*(15+5))
  self.assertEqual(self.client.post('/api/v1/manage/batch-preview',json={**body,'max_requests':10001},headers=self.headers).status_code,422)

class OutboundTests(unittest.TestCase):
 def test_unsafe_schemes_redirect_targets_and_http_denied(self):
  with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':''}):
   for value in ('file:///etc/passwd','http://127.0.0.1/v1','https://key@example.com','https://example.com/?token=secret','https://example.com\\@127.0.0.1','https://example.com/\npath'):
    with self.assertRaises(OutboundDenied):validate_url(value)
 def test_all_dns_addresses_checked_and_rebinding_pinned(self):
  with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':''}),patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaises(OutboundDenied):resolve_target('https://example.com/v1',2)
 def test_explicit_private_origin_allowed_but_metadata_and_transition_denied(self):
  for address in ('169.254.169.254','::ffff:169.254.169.254','2002:7f00:1::','fe80::1','100.100.100.200','168.63.129.16','fd00:ec2::254'):
   with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':'http://gateway:8000'}),patch('socket.getaddrinfo',return_value=[(2,1,6,'',(address,8000))]):
    with self.assertRaises(OutboundDenied):resolve_target('http://gateway:8000/v1',2)
  with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':'http://gateway:8000'}),patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',8000))]):self.assertEqual(resolve_target('http://gateway:8000/v1',2)[3],['127.0.0.1'])
 def test_live_non_inference_request_no_redirect_proxy_or_body_leak(self):
  import threading,http.server
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    self.send_response(302 if self.path=='/redirect' else 200);self.send_header('Location','http://169.254.169.254/');self.end_headers();self.wfile.write(b'{"data":[]}')
   def log_message(self,*args):pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
  try:
   with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':origin,'HTTP_PROXY':'http://127.0.0.1:1'}):
    self.assertEqual(request_json(origin+'/models','not-logged')['data'],[])
    from swe_eval.providers import ProviderError
    with self.assertRaises(ProviderError) as error:request_json(origin+'/redirect','not-logged')
    self.assertEqual(str(error.exception),'upstream HTTP 302')
  finally:server.shutdown();server.server_close();thread.join()

class DeadlineTests(unittest.TestCase):
 def test_http10_slow_body_obeys_whole_request_deadline(self):
  import threading,http.server
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    time.sleep(.5);self.send_response(200);self.send_header('Content-Length','11');self.end_headers();time.sleep(2)
   def log_message(self,*args):pass
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
  try:
   from swe_eval.providers import ProviderError
   with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':origin}):
    start=time.monotonic()
    with self.assertRaises(ProviderError):request_json(origin+'/slow','',timeout=.7)
    self.assertLess(time.monotonic()-start,1.05)
  finally:server.shutdown();server.server_close();thread.join()

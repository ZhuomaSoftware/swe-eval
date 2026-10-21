"""Phase 2 deterministic API, batch, analytics and integration contracts.
No candidate repository is imported or executed by these host tests.
"""
import dataclasses
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from fastapi.testclient import TestClient

from swe_eval.api import create_app
from swe_eval.analytics import comparison, summary, shadow_export, percentile
from swe_eval.benchmarks.local import LocalBenchmark
from swe_eval.center import snapshot, submit_batch
from swe_eval.center_schema import BatchSubmission
from swe_eval.config import Settings, load_models
from swe_eval.schema import Metrics, RunState
from swe_eval.service import enqueue, repository
from swe_eval.sessions import password_hash
from swe_eval.storage import Conflict, SQLiteRepository


class CenterCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password='dummy-console-password'
        cls.password_hash=password_hash(cls.password)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); models=self.root/'models.json'
        models.write_text(json.dumps([dict(id=x,model_id='same-model',upstream_id='channel-'+x,
            base_url='http://127.0.0.1:1/v1',allow_http=True,allow_no_api_key=True,
            data_origin='live',upstream_verified=True) for x in ('a','b')]))
        self.settings=Settings(self.root/'db',models,'dummy-admin-token-at-least-32-chars',
            ui_password_hash=self.password_hash,cookie_secure=False,public_origin='http://testserver',
            shadow_token='dummy-read-only-shadow-token-32-chars')
        self.profiles=load_models(models); self.benchmark=LocalBenchmark(); self.repo=repository(self.settings)
        self.client=TestClient(create_app(self.settings)); self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.settings.admin_token}

    def body(self,**changes):
        return dict(name='deterministic test',task_ids=['intervals-001'],model_profile_ids=['a'],
                    idempotency_key='test-key-12345',**changes)

    def batch(self,body=None):
        return submit_batch(self.repo,self.benchmark,self.profiles,BatchSubmission.model_validate(body or self.body()),self.settings)

    def result(self,profile='a',passed=True,infra=False,legacy=False,**changes):
        record=enqueue(self.repo,self.benchmark,self.profiles,'intervals-001',profile)
        self.repo.acquire('owner',60);self.repo.claim('owner',record['id'])
        m=Metrics(model_requests=2,api_errors=1 if infra else 0,wall_seconds=changes.pop('duration',10),
            input_tokens=10,output_tokens=5,total_tokens=15,usage_complete=True,cost=changes.pop('cost',None),
            patch_applied=True,test_result='passed' if passed else 'failed',assertions_expected=10,
            assertions_executed=10,assertions_passed=10 if passed else 8,
            execution_metadata={'grading_protocol':'swe-eval-grading-v2','controller_image_digest':'sha256:trusted'})
        self.repo.transition(record['id'],RunState.EVALUATING)
        self.repo.transition(record['id'],RunState.FAILED if infra else RunState.COMPLETED,metrics=m)
        if legacy or changes:
            with self.repo.connect(write=True) as db:
                if legacy: db.execute('DELETE FROM evaluation_snapshots WHERE run_id=?',(record['id'],))
                if changes:
                    snap=self.repo.get(record['id'])['snapshot'];snap.update(changes)
                    db.execute('UPDATE evaluation_snapshots SET snapshot_json=? WHERE run_id=?',(json.dumps(snap),record['id']))
        return self.repo.get(record['id'])


class DashboardAPITests(CenterCase):
    def test_empty_and_auth(self):
        for path in ('/overview','/system','/batches','/comparison','/comparison/export','/integrations/sub2api'):
            self.assertEqual(self.client.get('/api/v1'+path).status_code,401)
            self.assertEqual(self.client.get('/api/v1'+path,headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/v1/overview',headers=self.headers).json()['total_runs'],0)
        self.assertFalse(self.client.get('/api/v1/system',headers=self.headers).json()['worker_ready'])

    def test_cookie_csrf_logout_restart(self):
        login=self.client.post('/api/v1/session',headers={'Origin':'http://testserver'},json={'password':self.password})
        self.assertEqual(login.status_code,200);self.assertIn('HttpOnly',login.headers['set-cookie']);self.assertIn('SameSite=strict',login.headers['set-cookie'])
        self.assertNotIn(self.settings.admin_token,login.text)
        csrf=login.json()['csrf_token']
        self.assertEqual(self.client.post('/api/v1/batches',json=self.body()).status_code,403)
        self.assertEqual(self.client.post('/api/v1/batches',headers={'Origin':'https://evil.invalid','X-CSRF-Token':csrf},json=self.body()).status_code,403)
        self.assertEqual(self.client.post('/api/v1/batches',headers={'Origin':'http://testserver','X-CSRF-Token':csrf},json=self.body()).status_code,202)
        another=TestClient(create_app(self.settings));self.addCleanup(another.close);another.cookies.update(self.client.cookies)
        self.assertEqual(another.get('/api/v1/session').status_code,200)
        csrf=another.get('/api/v1/session').json()['csrf_token']
        self.assertEqual(another.delete('/api/v1/session',headers={'Origin':'http://testserver','X-CSRF-Token':csrf}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/models').status_code,401)

    def test_login_rate_origin_and_secret_exclusion(self):
        secret='sk-dummy-secret-reflection-password-123'
        self.assertEqual(self.client.post('/api/v1/session',json={'password':secret}).status_code,403)
        for _ in range(10):
            r=self.client.post('/api/v1/session',headers={'Origin':'http://testserver'},json={'password':secret})
            self.assertEqual(r.status_code,401);self.assertNotIn(secret,r.text)
        self.assertEqual(self.client.post('/api/v1/session',headers={'Origin':'http://testserver'},json={'password':self.password}).status_code,429)
        with self.repo.connect() as db:
            self.assertNotIn(secret,str([tuple(x) for x in db.execute('SELECT * FROM operational_events')]))
        models=self.client.get('/api/v1/models',headers=self.headers).text
        for value in ('base_url','api_key_env',self.settings.admin_token):self.assertNotIn(value,models)
        self.assertIn('endpoint_identity',models)

    def test_filters_pagination_detail_exports(self):
        good=self.result(); self.result('b',False)
        for key,val in [('model_profile_id','a'),('upstream_id','channel-a'),('state','completed'),('benchmark','local-python-repairs'),('grading_protocol','swe-eval-grading-v2')]:
            response=self.client.get('/api/v1/runs',params={key:val},headers=self.headers)
            self.assertEqual(response.status_code,200);self.assertGreaterEqual(response.json()['total'],1)
        self.assertEqual(self.client.get('/api/v1/runs?created_after='+str(time.time()+10),headers=self.headers).json()['total'],0)
        self.assertEqual(self.client.get('/api/v1/runs?limit=1&offset=1',headers=self.headers).json()['total'],2)
        for path in ('/batches?offset=9223372036854775808','/runs?created_after=nan','/runs?state=unknown'):
            self.assertEqual(self.client.get('/api/v1'+path,headers=self.headers).status_code,422)
        for suffix in ('','/logs','/patch'):
            self.assertEqual(self.client.get('/api/v1/runs/'+good['id']+suffix,headers=self.headers).status_code,200)
            self.assertEqual(self.client.get('/api/v1/runs/'+good['id']+suffix).status_code,401)
        for format in ('json','csv'):
            response=self.client.get('/api/v1/comparison/export?format='+format,headers=self.headers)
            self.assertEqual(response.status_code,200);self.assertIn('swe-eval-grading-v2',response.text)
            self.assertNotIn(self.settings.admin_token,response.text)
            self.assertNotIn('expected',response.text)

    def test_operational_readiness_requires_worker(self):
        self.repo.acquire('owner',10)
        self.assertFalse(self.repo.operations()['worker_ready'])
        self.repo.event('worker_starting');self.repo.event('worker_ready','cleanup complete in 0.3s')
        self.assertTrue(self.repo.operations()['worker_ready'])
        self.repo.event('cleanup_failed')
        self.assertFalse(self.repo.operations()['worker_ready'])


class BatchTests(CenterCase):
    def test_expansion_identity_and_restart(self):
        body=self.body();body.update(model_profile_ids=['a','b'],attempts=2)
        batch=self.batch(body);self.assertEqual(batch['total'],4)
        self.assertEqual(len({a['run_id'] for a in batch['attempts']}),4)
        for a in batch['attempts']:
            run=self.repo.get(a['run_id']);self.assertEqual(run['batch']['batch_id'],batch['id'])
            self.assertEqual(run['snapshot']['grading_protocol'],'swe-eval-grading-v2')
            self.assertEqual(len(run['snapshot']['harness_revision']),64)
            self.assertNotIn('base_url',json.dumps(run['snapshot']))
        repo=SQLiteRepository(self.settings.database);repo.initialize();repo.initialize()
        self.assertEqual(repo.batch(batch['id'])['total'],4)
        with repo.connect() as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_multiple_tasks(self):
        from swe_eval.benchmarks.local import LocalBenchmark
        original=self.benchmark.get_task('intervals-001')
        other=original.model_copy(update={'id':'second-trusted-task'})
        class TwoTasks:
            def get_task(self,task_id):return {'intervals-001':original,'second-trusted-task':other}[task_id]
        body=self.body();body['task_ids'].append(other.id)
        b=submit_batch(self.repo,TwoTasks(),self.profiles,BatchSubmission.model_validate(body),self.settings)
        self.assertEqual({a['task_id'] for a in b['attempts']},{original.id,other.id})

    def test_atomic_idempotency_and_conflict(self):
        b=self.batch();self.assertEqual(self.batch()['id'],b['id']);self.assertEqual(len(self.repo.list()),1)
        different=self.body();different['name']='other'
        with self.assertRaises(Conflict):self.batch(different)
        self.assertEqual(len(self.repo.list()),1)

    def test_concurrent_submission_deduplicates(self):
        ids=[];errors=[]
        def submit():
            try:ids.append(self.batch()['id'])
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=submit) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(len(set(ids)),1);self.assertEqual(len(self.repo.list()),1)

    def test_invalid_limits_models_tasks_and_no_partial_rows(self):
        for change in ({'task_ids':['unknown']},{'model_profile_ids':['unknown']},{'attempts':6},
            {'model_profile_ids':['a','b'],'attempts':5,'max_requests':1},
            {'reasoning':{'a':'high'}},{'spending_limit':1},{'task_ids':['intervals-001']*2}):
            body=self.body();body.update(change)
            response=self.client.post('/api/v1/batches',headers=self.headers,json=body)
            self.assertEqual(response.status_code,422,response.text)
        limited=dataclasses.replace(self.settings,max_batch_runs=1,max_pending_runs=1)
        with self.assertRaises(ValueError):submit_batch(self.repo,self.benchmark,self.profiles,BatchSubmission.model_validate(self.body(attempts=2)),limited)
        self.assertEqual(len(self.repo.list()),0)
        self.batch()
        body=self.body();body['idempotency_key']='different-key'
        with self.assertRaises(Conflict):submit_batch(self.repo,self.benchmark,self.profiles,BatchSubmission.model_validate(body),limited)

    def test_partial_failure_cancel_and_recovery(self):
        body=self.body();body['model_profile_ids']=['a','b'];b=self.batch(body)
        self.repo.acquire('old',1);active=self.repo.claim('old');self.repo.transition(active['id'],RunState.RUNNING)
        self.repo.cancel_batch(b['id'])
        self.assertTrue(self.repo.get(active['id'])['cancel_requested'])
        self.assertEqual(self.repo.batch(b['id'])['progress']['cancelled'],1)
        with self.repo.connect(write=True) as db:db.execute('UPDATE worker_lock SET expires_at=0')
        self.repo.acquire('new',60);self.repo.recover('new')
        recovered=self.repo.get(active['id']);self.assertEqual(recovered['state'],'failed');self.assertIsNone(recovered['metrics']['resolved'])
        self.assertEqual(self.repo.batch(b['id'])['terminal'],2)
        self.assertIsNone(self.repo.claim('new'))
        with self.assertRaises(Conflict):self.repo.save_metrics(active['id'],Metrics(resolved=True))

    def test_deadline_reconciliation_and_request_reservation(self):
        b=self.batch();self.assertEqual(b['configuration']['reserved_requests'],15)
        with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_batches SET deadline=0')
        self.repo.acquire('owner',60);self.assertIsNone(self.repo.claim('owner'))
        self.assertEqual(self.repo.batch(b['id'])['state'],'cancelled')
        self.assertEqual(self.repo.batch(b['id'])['stop_reason'],'batch_deadline_exceeded')
        self.repo.reconcile_batches();self.assertEqual(len(self.repo.list()),1)

    def test_effective_limits_not_bypass(self):
        body=self.body();body['limits']={'timeout':2,'steps':2,'requests':3,'output_tokens':100,'total_tokens':500}
        b=self.batch(body);r=self.repo.get(b['attempts'][0]['run_id'])
        self.assertEqual(r['snapshot']['effective_model']['max_model_calls'],3)
        self.assertEqual(r['model']['max_model_calls'],35)
        self.assertEqual(b['configuration']['reserved_requests'],3)


class AnalyticsTests(CenterCase):
    def test_exact_rates_costs_percentiles_infrastructure(self):
        self.result(passed=True,cost=1,duration=10);self.result(passed=False,cost=2,duration=20);self.result(infra=True,cost=None,duration=30)
        g=comparison(self.repo)['groups'][0];m=g['metrics']
        self.assertEqual(m['resolved_rate'],.5);self.assertAlmostEqual(m['attempt_success_rate'],1/3)
        self.assertEqual(m['pass_at_1'],1);self.assertEqual(m['pass_at_1_tasks'],1)
        self.assertEqual(m['p50_seconds'],20);self.assertEqual(m['p95_seconds'],29)
        self.assertIsNone(m['total_cost']);self.assertEqual(m['known_cost_subtotal'],3)
        self.assertIsNone(m['cost_per_resolved_task']);self.assertEqual(m['total_tokens'],45)
        self.assertEqual(m['infrastructure_errors'],1)

    def test_first_independent_not_best_attempt(self):
        self.result(infra=True);self.result(passed=True)
        self.assertEqual(comparison(self.repo)['groups'][0]['metrics']['pass_at_1'],0)

    def test_empty_unknown_usage_and_known_cost(self):
        self.assertEqual(comparison(self.repo)['groups'],[]);self.assertIsNone(percentile([], .5))
        r=self.result(cost=2);m=summary([r]);self.assertEqual(m['cost_per_resolved_task'],2)
        r['metrics']['input_tokens']=None;r['metrics']['cost']=None
        self.assertIsNone(summary([r])['input_tokens']);self.assertIsNone(summary([r])['average_task_cost'])

    def test_legacy_origins_versions_and_config_isolation(self):
        self.result(legacy=True);self.result('a');self.result('b')
        g=comparison(self.repo);self.assertEqual(len(g['groups']),2);self.assertEqual(g['excluded']['legacy_or_missing_provenance'],1)
        run=self.result('a');snap=run['snapshot'];snap['effective_model']['reasoning_effort']='high';snap['runtime_fingerprint']='other'
        with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_snapshots SET snapshot_json=? WHERE run_id=?',(json.dumps(snap),run['id']))
        self.assertEqual(len(comparison(self.repo)['groups']),3)
        with self.repo.connect(write=True) as db:
            task=run['task'];task['dataset_version']='2.0.0';db.execute('UPDATE runs SET task_json=? WHERE id=?',(json.dumps(task),run['id']))
        self.assertIn('2.0.0',{x['dataset_version'] for x in comparison(self.repo)['groups']})

    def test_unequal_coverage_and_controller_mismatch(self):
        self.result('a');self.result('b');self.result('a',task_fingerprint='extra-task')
        groups=comparison(self.repo)['groups'];self.assertTrue(all(g['matched_task_count']==1 for g in groups))
        self.assertTrue(all(any('unequal' in w for w in g['warnings']) for g in groups))
        run=self.result('b')
        with self.repo.connect(write=True) as db:
            m=run['metrics'];m['execution_metadata']['controller_image_digest']='other'
            db.execute('UPDATE runs SET metrics_json=? WHERE id=?',(json.dumps(m),run['id']))
        self.assertTrue(all(not g['comparison_eligible'] for g in comparison(self.repo)['groups']))

    def test_shadow_read_only_and_eligibility(self):
        self.result('a');self.result('a',infra=True);self.result('b',data_origin='local_stub')
        items=shadow_export(self.repo)['items'];self.assertEqual(len(items),1)
        self.assertEqual(items[0]['quality']['eligible_run_count'],1)
        self.assertFalse(items[0]['quality']['scoring_eligible']);self.assertIsNone(items[0]['quality']['capability_weights'])
        headers={'Authorization':'Bearer '+self.settings.shadow_token}
        self.assertEqual(self.client.get('/api/v1/shadow/results',headers=headers).status_code,200)
        for path in ('/batches','/runs','/integrations/sub2api/sync'):
            self.assertEqual(self.client.post('/api/v1'+path,headers=headers,json=self.body()).status_code,401)
        self.assertEqual(self.client.post('/api/v1/shadow/results',headers=headers).status_code,405)
        self.assertEqual(self.client.get('/api/v1/shadow/results').status_code,401)


class IntegrationTests(CenterCase):
    def test_source_contract_get_only_whitelist_and_failure_atomicity(self):
        observed=[];response={'code':0,'data':{'models':['same-model'],'api_key':'DUMMY-UPSTREAM-SECRET'}}
        class Stub(BaseHTTPRequestHandler):
            def do_GET(handler):
                observed.append((handler.command,handler.path))
                raw=json.dumps(response).encode();handler.send_response(200);handler.end_headers();handler.wfile.write(raw)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Stub);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        config=self.root/'integration.json';config.write_text(json.dumps(dict(source_id='test-gateway',base_url=f'http://127.0.0.1:{server.server_port}',allow_http=True,admin_key_env='DUMMY_SYNC_KEY',mappings=[dict(profile_id='a',group_id=7,upstream_source_id='manual-channel')])) )
        settings=dataclasses.replace(self.settings,integration_file=config)
        client=TestClient(create_app(settings));self.addCleanup(client.close)
        with patch.dict(os.environ,{'DUMMY_SYNC_KEY':'DUMMY-ADMIN-SYNC-SECRET'}):
            r=client.post('/api/v1/integrations/sub2api/sync',headers=self.headers)
            self.assertEqual(r.status_code,200,r.text);self.assertNotIn('SECRET',r.text)
            self.assertFalse(r.json()['items'][0]['upstream_verified'])
            response['data']['models']={'unknown':'schema'}
            self.assertEqual(client.post('/api/v1/integrations/sub2api/sync',headers=self.headers).status_code,502)
        self.assertTrue(all(x==('GET','/api/v1/admin/groups/7/effective-models') for x in observed))
        stored=client.get('/api/v1/integrations/sub2api',headers=self.headers).text
        self.assertNotIn('SECRET',stored);self.assertIn('same-model',stored)

    def test_integration_missing_dependency_reported(self):
        self.assertEqual(self.client.post('/api/v1/integrations/sub2api/sync',headers=self.headers).status_code,503)
        response=self.client.get('/api/v1/integrations/sub2api',headers=self.headers)
        self.assertIn('blocked',response.json()['federation'])
        self.assertEqual(response.headers['x-frame-options'],'DENY')
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])


if __name__=='__main__':unittest.main()

class MigrationTests(CenterCase):
    def test_v1_upgrade_rollback_retains_historical_records(self):
        run=self.result(legacy=True)
        with self.repo.connect() as db:
            before=tuple(db.execute('SELECT * FROM runs WHERE id=?',(run['id'],)).fetchone())
            logs=[tuple(x) for x in db.execute('SELECT * FROM logs')]
        sql=(Path(__import__('swe_eval').__file__).parent/'migrations/002_center.down.sql').read_text()
        with self.repo.connect() as db:db.executescript(sql)
        self.repo.initialize();self.repo.initialize()
        with self.repo.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM runs WHERE id=?',(run['id'],)).fetchone()),before)
            self.assertEqual([tuple(x) for x in db.execute('SELECT * FROM logs')],logs)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertIsNone(self.repo.get(run['id'])['snapshot'])
        self.assertEqual(comparison(self.repo)['groups'],[])

    def test_reasoning_validation_never_reflects_input(self):
        value='sk-dummy-reasoning-secret-'+('x'*100)
        profile=self.profiles['a'].model_copy(deep=True);profile.capabilities.reasoning_effort=True
        from swe_eval.center import effective_profile
        with self.assertRaises(ValueError) as error:effective_profile(profile,reasoning=value,override=True)
        self.assertNotIn(value,str(error.exception))

class ExportIntegrityTests(CenterCase):
    def test_shadow_retains_failed_first_attempt_denominator(self):
        self.result(infra=True);self.result(passed=True)
        export=shadow_export(self.repo)['items'][0]
        self.assertEqual(export['metrics']['pass_at_1'],0)
        self.assertEqual(export['metrics']['attempt_success_rate'],.5)
        self.assertEqual(export['reliability']['attempts'],2)
        self.assertEqual(export['quality']['eligible_run_count'],1)

    def test_false_accounting_and_unsupported_controller_excluded(self):
        run=self.result()
        with self.repo.connect(write=True) as db:
            m=run['metrics'];m['assertions_passed']=0
            db.execute('UPDATE runs SET metrics_json=? WHERE id=?',(json.dumps(m),run['id']))
        self.assertEqual(comparison(self.repo)['groups'][0]['metrics']['valid_evaluations'],0)
        self.assertEqual(shadow_export(self.repo)['items'],[])

class EndpointIdentityTests(CenterCase):
    def test_same_profile_different_endpoint_never_merges(self):
        self.result('a')
        self.profiles['a']=self.profiles['a'].model_copy(update={'base_url':'http://127.0.0.1:2/v1'})
        self.result('a')
        groups=comparison(self.repo)['groups']
        self.assertEqual(len(groups),2)
        self.assertEqual(len({g['endpoint_identity'] for g in groups}),2)

class FreshnessIntegrityTests(CenterCase):
    def test_pending_attempt_cannot_refresh_authoritative_result_timestamp(self):
        completed=self.result('a')
        pending=enqueue(self.repo,self.benchmark,self.profiles,'intervals-001','a')
        with self.repo.connect(write=True) as db:
            db.execute('UPDATE runs SET created_at=? WHERE id=?',(completed['finished_at']+1000,pending['id']))
        exported=shadow_export(self.repo)['items'][0]
        self.assertEqual(exported['evaluated_at'],completed['finished_at'])
        self.assertEqual(exported['quality']['eligible_run_count'],1)
        self.assertEqual(exported['reliability']['incomplete'],1)

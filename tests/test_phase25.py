"""Permanent Phase 2.5 regressions; synthetic fixtures never execute candidate code."""
import csv
import io
import json
import threading
import time
from test_center import CenterCase
from swe_eval.analytics import comparison, summary, shadow_export
from swe_eval.schema import Metrics, RunState
from swe_eval.storage import SQLiteRepository


class ConfidentialityTests(CenterCase):
    def test_historical_hidden_records_filtered_without_destroying_forensics(self):
        run=self.result(); hidden='PRIVATE-HIDDEN-CANARY-ANSWER'
        unsafe=json.dumps({'protocol':'swe-eval-grading-v2','assertions_expected':10,'assertions_executed':10,'assertions_passed':8,'execution_errors':0,'passed':False,'details':[{'expected':hidden,'observed':hidden,'input':hidden}]})
        with self.repo.connect(write=True) as db:
            for event,message in [('trusted_assertions',unsafe),('test_output',hidden)]:
                db.execute('INSERT INTO logs(run_id,at,event,message) VALUES (?,?,?,?)',(run['id'],time.time(),event,message))
        for suffix in ('','/logs'):
            response=self.client.get('/api/v1/runs/'+run['id']+suffix,headers=self.headers)
            self.assertNotIn(hidden,response.text)
        self.assertNotIn(hidden,json.dumps(self.repo.logs(run['id'])))
        for fmt in ('csv','json'):
            self.assertNotIn(hidden,self.client.get('/api/v1/comparison/export?format='+fmt,headers=self.headers).text)
        with self.repo.connect() as db:
            self.assertIn(hidden,db.execute("SELECT message FROM logs WHERE event='trusted_assertions'").fetchone()[0])

    def test_new_controller_diagnostics_are_sanitized_before_persistence(self):
        run=self.result();self.repo.log(run['id'],'trusted_assertions',json.dumps({'assertions_expected':10,'assertions_executed':10,'assertions_passed':4,'execution_errors':0,'passed':False,'details':[{'expected':'PRIVATE-ANSWER'}]}))
        self.repo.log(run['id'],'test_output','PRIVATE-INPUT-AND-OUTPUT')
        with self.repo.connect() as db:
            raw=' '.join(x[0] for x in db.execute('SELECT message FROM logs'))
        self.assertNotIn('PRIVATE-',raw);self.assertIn('assertions_failed',raw)


class BatchFinalityTests(CenterCase):
    def complete(self,batch):
        self.repo.acquire('owner',60)
        for attempt in batch['attempts']:
            self.repo.claim('owner',attempt['run_id']);self.repo.transition(attempt['run_id'],RunState.EVALUATING)
            self.repo.transition(attempt['run_id'],RunState.COMPLETED,metrics=Metrics(patch_applied=True,test_result='passed'))

    def test_completed_deadline_cancel_repeat_and_reopen(self):
        b=self.batch();self.complete(b);before=self.repo.batch(b['id'])
        with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_batches SET deadline=0 WHERE id=?',(b['id'],))
        self.repo.reconcile_batches();self.assertEqual(self.repo.batch(b['id'])['state'],'completed')
        for _ in range(2):
            r=self.client.post('/api/v1/batches/'+b['id']+'/cancel',headers=self.headers)
            self.assertEqual(r.status_code,202);self.assertEqual(r.json()['state'],'completed');self.assertFalse(r.json()['cancel_requested'])
        again=SQLiteRepository(self.settings.database);again.initialize()
        self.assertEqual(again.batch(b['id'])['progress'],before['progress'])
        self.assertEqual(again.batch(b['id'])['state'],'completed')

    def test_queued_partial_active_and_deadline_cancel(self):
        b=self.batch(self.body(attempts=2));self.repo.acquire('owner',60);r=self.repo.claim('owner')
        self.repo.transition(r['id'],RunState.RUNNING)
        with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_batches SET deadline=0')
        self.repo.reconcile_batches();self.assertEqual(self.repo.batch(b['id'])['state'],'stopping')
        self.assertTrue(self.repo.get(r['id'])['cancel_requested']);self.repo.transition(r['id'],RunState.CANCELLED)
        self.assertEqual(self.repo.cancel_batch(b['id'])['state'],'cancelled')
        self.assertEqual(self.repo.batch(b['id'])['progress']['cancelled'],2)

    def test_final_completion_races_reconciliation(self):
        for n in range(6):
            b=self.batch(dict(self.body(),idempotency_key='race-final-'+str(n)));self.repo.acquire('owner',60)
            r=self.repo.claim('owner',b['attempts'][0]['run_id']);self.repo.transition(r['id'],RunState.EVALUATING)
            with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_batches SET deadline=0 WHERE id=?',(b['id'],))
            barrier=threading.Barrier(2);errors=[]
            def act(f):
                try:barrier.wait();f()
                except Exception as e:errors.append(str(e))
            threads=[threading.Thread(target=act,args=(self.repo.reconcile_batches,)),threading.Thread(target=act,args=(lambda:self.repo.transition(r['id'],RunState.COMPLETED,metrics=Metrics(patch_applied=True,test_result='passed')),))]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertEqual(errors,[]);self.assertEqual(self.repo.batch(b['id'])['state'],'completed')


class TrustedIndicatorsTests(CenterCase):
    def test_legacy_and_synthetic_never_refresh_success(self):
        self.result(legacy=True)
        self.assertIsNone(self.repo.operations()['last_success_at'])
        live=self.result();self.result(passed=False);self.result(infra=True);self.result(data_origin='audit');self.result(data_origin='local_stub')
        self.assertEqual(self.repo.operations()['last_success_at'],live['finished_at'])
        o=self.client.get('/api/v1/overview',headers=self.headers).json()
        self.assertEqual(o['trusted_metrics']['resolved'],1)

    def test_quality_freshness_excludes_all_ineligible_activity(self):
        good=self.result();self.result(infra=True);self.result(data_origin='audit');self.result(data_origin='local_stub')
        export=shadow_export(self.repo)
        self.assertEqual(export['items'][0]['evaluated_at'],good['finished_at'])
        self.assertIn('last_attempted_at',export['items'][0])
        self.assertEqual(export['items'][0]['last_trusted_success_at'],good['finished_at'])


class OverviewIdentityTests(CenterCase):
    def test_ten_task_config_first_attempts_independent_reference(self):
        runs=[]
        for n in range(10):
            r=self.result('a',passed=n<8,task_fingerprint='task-'+str(n%4))
            r['snapshot']['endpoint_identity']='endpoint-'+str(n//4)
            runs.append(r)
        self.assertEqual(summary(runs)['pass_at_1_tasks'],10)
        self.assertEqual(summary(runs)['pass_at_1'],.8)
        # Explicit retries and numbered repeats cannot add first-attempt coverage.
        repeat=json.loads(json.dumps(runs[0]));repeat['id']='retry';repeat['parent_id']=runs[0]['id'];repeat['snapshot']['endpoint_identity']='retry-only';runs.append(repeat)
        repeat=json.loads(json.dumps(runs[0]));repeat['id']='second';repeat['attempt']=2;repeat['snapshot']['endpoint_identity']='second-only';runs.append(repeat)
        self.assertEqual(summary(runs)['pass_at_1_tasks'],10)


class CsvSafetyTests(CenterCase):
    def test_actual_export_bytes_formula_prefixes_and_parser(self):
        for prefix in ('=','+','-','@','\t=',' \t+','\r\n@','\x01-','\ufeff='):
            run=self.result()
            with self.repo.connect(write=True) as db:
                model=run['model'];model['model_id']=prefix+'1+1'
                db.execute('UPDATE runs SET model_json=? WHERE id=?',(json.dumps(model),run['id']))
                snap=run['snapshot'];snap['endpoint_identity']=prefix
                db.execute('UPDATE evaluation_snapshots SET snapshot_json=? WHERE run_id=?',(json.dumps(snap),run['id']))
        response=self.client.get('/api/v1/comparison/export?format=csv',headers=self.headers)
        self.assertEqual(response.status_code,200)
        rows=list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows),9)
        for row in rows:self.assertTrue(row['model_id'].startswith("'"),repr(row['model_id']));self.assertEqual(row['attempts'],'1')


class ObservabilityTests(CenterCase):
    def test_real_heartbeat_expiration_empty_and_recovery(self):
        o=self.repo.operations();self.assertIn('last_worker_heartbeat_at',o);self.assertIsNone(o['last_worker_heartbeat_at']);self.assertEqual(o['worker_lease_status'],'absent');self.assertEqual(o['queue_depth'],0)
        self.repo.acquire('owner',60);self.repo.event('worker_starting');self.repo.event('worker_ready')
        self.assertTrue(self.repo.heartbeat('owner',60));o=self.repo.operations()
        self.assertTrue(o['worker_ready']);self.assertLess(abs(time.time()-o['last_worker_heartbeat_at']),2)
        done=self.result();failed=self.result(infra=True)
        o=self.repo.operations();self.assertEqual(o['last_completed_evaluation']['id'],done['id']);self.assertEqual(o['recent_infrastructure_errors'][0]['id'],failed['id'])
        with self.repo.connect(write=True) as db:db.execute('UPDATE worker_lock SET expires_at=0')
        o=self.repo.operations();self.assertFalse(o['worker_ready']);self.assertEqual(o['worker_lease_status'],'expired')
        self.repo.acquire('new',60);self.repo.event('worker_starting');self.assertFalse(self.repo.operations()['worker_ready'])
        self.repo.event('cleanup_failed');self.assertEqual(self.repo.operations()['orphan_cleanup']['status'],'failed')
        self.repo.event('cleanup_complete');self.repo.event('worker_ready');self.assertTrue(self.repo.operations()['worker_ready'])

class AdditionalFinalityTests(CenterCase):
    def test_failed_terminal_batch_ignores_cancel_and_deadline(self):
        b=self.batch();self.repo.acquire('owner',60);r=self.repo.claim('owner');self.repo.transition(r['id'],RunState.FAILED,'provider_unavailable')
        self.assertEqual(self.repo.batch(b['id'])['state'],'failed')
        with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_batches SET deadline=0')
        for _ in range(2):
            self.repo.reconcile_batches();self.assertEqual(self.repo.cancel_batch(b['id'])['state'],'failed')
        self.assertFalse(self.repo.batch(b['id'])['cancel_requested']);self.assertEqual(self.repo.get(r['id'])['state'],'failed')

    def test_false_assertion_accounting_cannot_refresh_trusted_success(self):
        r=self.result()
        with self.repo.connect(write=True) as db:
            metrics=r['metrics'];metrics['assertions_passed']=0
            db.execute('UPDATE runs SET metrics_json=? WHERE id=?',(json.dumps(metrics),r['id']))
        self.assertIsNone(self.repo.operations()['last_success_at'])
        overview=self.client.get('/api/v1/overview',headers=self.headers).json()
        self.assertEqual(overview['trusted_metrics']['resolved'],0);self.assertEqual(shadow_export(self.repo)['items'],[])

"""Deterministic retry contracts: no paid inference and no candidate host execution."""
import unittest
from swe_eval.retries import RequestRetryPolicy, classify_http

class RetryClassificationTests(unittest.TestCase):
    def test_transient_http_classification(self):
        for status in (408,429,500,502,503,504):
            with self.subTest(status=status):self.assertTrue(classify_http(status,{},{}).retryable)
    def test_permanent_http_classification(self):
        for status in (400,401,403,404,405,413,422):
            with self.subTest(status=status):self.assertFalse(classify_http(status,{},{}).retryable)
    def test_quota_guard_without_recovery_fails_fast(self):
        error=classify_http(429,{}, {'error':{'code':'quota_guard_request_too_large','eligible':0,'soonest_available_ms':None}})
        self.assertFalse(error.retryable)
        self.assertEqual(error.category,'quota_exhausted')
    def test_defaults_are_bounded(self):
        self.assertEqual(RequestRetryPolicy().max_attempts,3)

import json,os,time,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from swe_eval.providers import OpenAICompatibleProvider,ProviderError,CompatibilityError,BudgetExceeded
from swe_eval.schema import Metrics,RunState
from swe_eval.retries import migrate_retries,RetryRuntime,retry_schema_ready
from swe_eval.management import migrate_administration
from swe_eval.storage import Conflict
from swe_eval.analytics import summary
from test_core import profile,completion
from test_center import CenterCase

class RequestRetryTests(unittest.TestCase):
    def setup_provider(self,sequence,**changes):
        self.responses=iter(sequence);self.calls=[];self.now=0.;self.delays=[];self.metrics=Metrics()
        def sleep(n):self.delays.append(n);self.now+=n
        def transport(*args):
            self.calls.append(args)
            value=next(self.responses)
            if isinstance(value,Exception):raise value
            return value
        return OpenAICompatibleProvider(profile(max_model_calls=changes.pop('max_model_calls',10)), 'dummy-private-canary',self.metrics,
          remaining=changes.pop('remaining',lambda:100),persist=lambda:None,transport=transport,sleep=sleep,clock=lambda:self.now,jitter=lambda:1,**changes)
    def test_502_twice_then_success(self):
        p=self.setup_provider([classify_http(502,{},{}),classify_http(502,{},{}),completion('SUBMIT')]);self.assertEqual(p.complete([])['content'],'SUBMIT')
        self.assertEqual((self.metrics.model_requests,self.metrics.http_attempts,self.metrics.http_retries,self.metrics.api_errors),(1,3,2,2));self.assertAlmostEqual(sum(self.delays),3);self.assertTrue(self.metrics.billing_uncertain);self.assertIsNone(self.metrics.total_tokens)
    def test_503_then_success(self):
        p=self.setup_provider([classify_http(503,{},{}),completion()]);p.complete([]);self.assertEqual(len(self.calls),2)
    def test_retry_after_minimum_is_respected(self):
        p=self.setup_provider([classify_http(429,{'Retry-After':'4'},{}),completion()]);p.complete([]);self.assertGreaterEqual(sum(self.delays),4)
    def test_structured_wait_and_no_message_matching(self):
        f=classify_http(429,{}, {'error':{'code':'rate_limit','wait_ms':2300,'retry_after_ms':1200}});self.assertEqual(f.retry_after,2.3)
        self.assertTrue(classify_http(429,{}, {'error':{'message':'insufficient_quota'}}).retryable)
    def test_permanent_quota_no_retry(self):
        for code in ('insufficient_quota','quota_guard_request_too_large'):
            p=self.setup_provider([classify_http(429,{}, {'error':{'code':code}})])
            with self.assertRaises(ProviderError):p.complete([])
            self.assertEqual(len(self.calls),1);self.assertFalse(self.metrics.recovery_eligible)
    def test_all_permanent_http_errors_fail_once(self):
        for status in (400,401,403,404,405,413,422):
            with self.subTest(status=status):
                p=self.setup_provider([classify_http(status,{},{})])
                with self.assertRaises(ProviderError):p.complete([])
                self.assertEqual(len(self.calls),1)
    def test_reset_then_success(self):
        p=self.setup_provider([ProviderError('reset',category='network',retryable=True,ambiguous=True),completion()]);p.complete([]);self.assertEqual(len(self.calls),2)
    def test_timeout_then_success(self):
        p=self.setup_provider([ProviderError('timeout',category='request_timeout',retryable=True,ambiguous=True),completion()]);p.complete([]);self.assertEqual(len(self.calls),2)
    def test_unknown_failure_is_not_retryable(self):
        p=self.setup_provider([ProviderError('unknown')])
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),1)
    def test_malformed_response_no_retry(self):
        p=self.setup_provider([{'unexpected':True}])
        with self.assertRaises(CompatibilityError):p.complete([])
        self.assertEqual(len(self.calls),1);self.assertFalse(self.metrics.recovery_eligible)
    def test_partial_stream_never_replayed(self):
        p=self.setup_provider([CompatibilityError('unexpected stream',category='malformed_response')]);self.assertFalse(p.body([])['stream'])
        with self.assertRaises(CompatibilityError):p.complete([])
        self.assertEqual(len(self.calls),1)
    def test_attempts_exhausted(self):
        p=self.setup_provider([classify_http(500,{},{}) for _ in range(3)])
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),3);self.assertTrue(self.metrics.recovery_eligible);self.assertEqual(self.metrics.retry_exhaustion_reason,'attempts_exhausted')
    def test_deadline_insufficient(self):
        p=self.setup_provider([classify_http(502,{},{})],remaining=lambda:.5)
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.metrics.retry_exhaustion_reason,'deadline_insufficient')
    def test_request_cap_counts_physical_attempts(self):
        p=self.setup_provider([classify_http(502,{},{}),completion()],max_model_calls=1)
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),1);self.assertFalse(self.metrics.recovery_eligible)
    def test_long_retry_after_does_not_idle_worker(self):
        p=self.setup_provider([classify_http(429,{'Retry-After':'1200'},{})])
        with self.assertRaises(ProviderError):p.complete([])
        self.assertFalse(self.delays);self.assertEqual(self.metrics.retry_exhaustion_reason,'retry_time_budget')
    def test_retry_disabled(self):
        p=self.setup_provider([classify_http(503,{},{})],retry_policy={'enabled':False})
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),1)
    def test_backoff_budget_exhaustion(self):
        p=self.setup_provider([classify_http(503,{},{})],retry_policy={'time_budget':.5})
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),1)
    def test_disabled_during_wait_stops_without_http_replay(self):
        p=self.setup_provider([classify_http(503,{},{}),completion()]);available=iter([True,False])
        class Runtime:
            def available(self):
                if not next(available):raise ProviderError('disabled',category='disabled')
            def cooldown(self,*args):return 0
            def log(self,*args):pass
        p.runtime=Runtime()
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual(len(self.calls),1)
    def test_true_http_transport_retries_and_redacts_payload(self):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                calls.append(1);self.rfile.read(int(self.headers['Content-Length']));code=502 if len(calls)<3 else 200
                data=json.dumps({'error':{'code':'temporary','message':'dummy-private-canary'}} if code==502 else completion()).encode()
                self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        from swe_eval.outbound import request_json
        origin='http://127.0.0.1:'+str(server.server_port)
        with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':origin}):
            p=self.setup_provider([]);p.profile=profile(base_url=origin+'/v1',allow_http=True);p.transport=request_json;p.complete([])
        self.assertEqual(len(calls),3);self.assertNotIn('dummy-private-canary',self.metrics.model_dump_json())

class DurableRecoveryTests(CenterCase):
    def setUp(self):
        super().setUp();migrate_administration(self.repo);migrate_retries(self.repo);self.repo.acquire('owner',300)
    def batch_with_recovery(self,enabled=True,**kw):
        return self.batch(self.body(api_retry={},run_recovery={'enabled':enabled},max_requests=100,**kw))
    def failed(self,batch,*,state=RunState.FAILED,category='transient_http',eligible=True):
        record=self.repo.claim('owner',batch['attempts'][0]['run_id'])
        self.repo.transition(record['id'],RunState.RUNNING)
        m=Metrics(model_requests=1,http_attempts=3,http_retries=2,api_errors=3,recovery_eligible=eligible,last_provider_error={'category':category,'http_status':502,'retryable':eligible})
        self.repo.transition(record['id'],state,metrics=m)
        return self.repo.get(record['id'])
    def test_atomic_one_child_original_snapshot_and_identity(self):
        batch=self.batch_with_recovery();parent=self.failed(batch);children=parent['retry']['children'];self.assertEqual(len(children),1)
        child=self.repo.get(children[0]['child_id']);self.assertEqual(child['parent_id'],parent['id']);self.assertNotEqual(child['id'],parent['id']);self.assertEqual(child['task'],parent['task']);self.assertEqual(child['model'],parent['model']);self.assertEqual(child['snapshot'],parent['snapshot']);self.assertEqual(child['state'],'queued');self.assertEqual(self.repo.patch(child['id']),'');self.assertEqual(child['metrics']['model_requests'],0)
        self.assertEqual(self.repo.batch(batch['id'])['total'],1);self.assertEqual(self.repo.batch(batch['id'])['state'],'running')
    def test_repeated_scans_do_not_duplicate_after_insert(self):
        b=self.batch_with_recovery();p=self.failed(b)
        for _ in range(4):self.assertEqual(self.repo.schedule_recoveries('owner',self.settings),[])
        self.assertEqual(len(self.repo.get(p['id'])['retry']['children']),1)
    def test_insertion_crash_rolls_back_parent_and_child(self):
        b=self.batch_with_recovery();rid=b['attempts'][0]['run_id'];self.repo.claim('owner',rid)
        m=Metrics(recovery_eligible=True,last_provider_error={'category':'transient_http'})
        with patch.object(self.repo,'_insert_run',side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(RuntimeError):self.repo.transition(rid,RunState.FAILED,metrics=m)
        self.assertEqual(self.repo.get(rid)['state'],'preparing');self.assertEqual(self.repo.get(rid)['retry']['children'],[])
        self.repo.transition(rid,RunState.FAILED,metrics=m);self.assertEqual(len(self.repo.get(rid)['retry']['children']),1)
    def test_disabled_recovery_no_child(self):
        self.assertFalse(self.failed(self.batch_with_recovery(False))['retry']['children'])
    def test_nontransient_failure_no_child(self):
        self.assertFalse(self.failed(self.batch_with_recovery(),category='authentication',eligible=False)['retry']['children'])
    def test_whole_timeout_no_recovery(self):
        self.assertFalse(self.failed(self.batch_with_recovery(),state=RunState.TIMEOUT)['retry']['children'])
    def test_unresolved_repair_no_child(self):
        b=self.batch_with_recovery();rid=b['attempts'][0]['run_id'];self.repo.claim('owner',rid);self.repo.transition(rid,RunState.EVALUATING);self.repo.transition(rid,RunState.COMPLETED,metrics=Metrics(patch_applied=False,resolved=False));self.assertEqual(self.repo.get(rid)['retry']['children'],[])
    def test_manual_retry_still_works(self):
        p=self.failed(self.batch_with_recovery(False));r=self.client.post('/api/v1/runs/'+p['id']+'/retry',headers=self.headers);self.assertEqual(r.status_code,202,r.text);self.assertEqual(r.json()['parent_id'],p['id'])
    def test_cancel_stops_recovery_and_keeps_parent_immutable(self):
        b=self.batch_with_recovery();p=self.failed(b);before=p['metrics'];self.repo.cancel_batch(b['id']);child=self.repo.get(p['retry']['children'][0]['child_id']);self.assertEqual(child['state'],'cancelled');self.assertEqual(self.repo.get(p['id'])['metrics'],before);self.assertEqual(self.repo.schedule_recoveries('owner',self.settings),[])
    def test_deadline_during_failed_transition_prevents_child(self):
        b=self.batch_with_recovery()
        with self.repo.connect(write=True) as db:db.execute('UPDATE evaluation_batches SET deadline=? WHERE id=?',(time.time()+.2,b['id']))
        self.assertFalse(self.failed(b)['retry']['children'])
    def test_stale_lease_cannot_finalize_or_schedule(self):
        b=self.batch_with_recovery();r=self.repo.claim('owner',b['attempts'][0]['run_id'])
        with self.repo.connect(write=True) as db:db.execute('UPDATE worker_lock SET expires_at=0')
        with self.assertRaises(Conflict):self.repo.schedule_recoveries('owner',self.settings)
        with self.assertRaises(Conflict):self.repo.transition(r['id'],RunState.FAILED,metrics=Metrics(recovery_eligible=True,last_provider_error={'category':'network'}))
    def test_deferred_state_survives_repository_restart(self):
        b=self.batch_with_recovery();p=self.failed(b);cid=p['retry']['children'][0]['child_id']
        with self.repo.connect(write=True) as db:db.execute('UPDATE run_recoveries SET next_eligible_at=?',(time.time()+120,))
        from swe_eval.service import repository
        fresh=repository(self.settings);self.assertIsNone(fresh.claim('owner',cid));self.assertEqual(fresh.get(cid)['state'],'queued');self.assertEqual(fresh.schedule_recoveries('owner',self.settings),[])
    def test_recovery_cannot_recursively_retry(self):
        b=self.batch_with_recovery();p=self.failed(b);cid=p['retry']['children'][0]['child_id'];self.repo.claim('owner',cid);self.repo.transition(cid,RunState.FAILED,metrics=Metrics(recovery_eligible=True,last_provider_error={'category':'network'}));self.assertEqual(self.repo.get(cid)['retry']['children'],[]);self.assertEqual(self.repo.batch(b['id'])['state'],'failed')
    def test_recovery_does_not_inflate_pass_at_one(self):
        b=self.batch_with_recovery();p=self.failed(b);cid=p['retry']['children'][0]['child_id'];self.repo.claim('owner',cid);self.repo.transition(cid,RunState.EVALUATING);self.repo.transition(cid,RunState.COMPLETED,metrics=Metrics(patch_applied=True,resolved=True,test_result='passed',assertions_expected=1,assertions_executed=1,assertions_passed=1,execution_metadata={'grading_protocol':'swe-eval-grading-v2','controller_image_digest':'sha256:verified'}))
        result=summary([self.repo.get(p['id']),self.repo.get(cid)]);self.assertEqual(result['attempts'],1);self.assertEqual(result['pass_at_1'],0);self.assertEqual(result['resolved'],0);self.assertEqual(result['operational_recovery_resolved'],1)
    def test_migration_idempotent_and_integrity(self):
        migrate_retries(self.repo)
        with self.repo.connect() as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3);self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_batch_preview_reserves_recovery(self):
        body=self.body(api_retry={},run_recovery={'enabled':True})
        r=self.client.post('/api/v1/manage/batch-preview',headers=self.headers,json=body);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['possible_recoveries'],1);self.assertEqual(r.json()['reserved_requests'],30)

class TransportClassificationTests(unittest.TestCase):
    def test_dns_permanent_vs_transient(self):
        import socket
        from swe_eval.retries import transport_failure
        self.assertFalse(transport_failure(socket.gaierror(socket.EAI_NONAME,'missing')).retryable)
        self.assertTrue(transport_failure(socket.gaierror(socket.EAI_AGAIN,'temporary')).retryable)
    def test_connection_refused_vs_unknown_os_error(self):
        from swe_eval.retries import transport_failure
        self.assertTrue(transport_failure(ConnectionRefusedError('refused')).retryable)
        self.assertFalse(transport_failure(OSError('unknown')).retryable)
    def test_tls_verification_is_permanent(self):
        import ssl
        from swe_eval.retries import transport_failure
        self.assertFalse(transport_failure(ssl.SSLCertVerificationError('invalid cert')).retryable)

class RealClockBackoffTests(unittest.TestCase):
    def test_runtime_check_can_outlast_remaining_backoff(self):
        responses=iter([classify_http(502,{},{}),completion()]);calls=[]
        class Runtime:
            def available(self):time.sleep(.07)
            def cooldown(self,*args):return 0
            def log(self,*args):pass
        def transport(*args):
            calls.append(1);v=next(responses)
            if isinstance(v,Exception):raise v
            return v
        p=OpenAICompatibleProvider(profile(),'',Metrics(),remaining=lambda:10,persist=lambda:None,runtime=Runtime(),transport=transport,retry_policy={'initial_delay':.05,'max_delay':.05})
        self.assertEqual(p.complete([])['content'],'SUBMIT');self.assertEqual(len(calls),2)

class RetryAccountingTests(unittest.TestCase):
    def run_record(self,cost=None,currency=None,known=None):
        return {'id':'a','state':'failed','parent_id':None,'created_at':1,'task':{'id':'t','benchmark':'b','dataset_version':'v'},'model':{'id':'p','upstream_id':'u'},'metrics':Metrics(cost=cost,currency=currency,known_cost_subtotal=known,known_cost_currency=currency).model_dump()}
    def test_unknown_cost_stays_unknown_in_operational_totals(self):
        m=summary([self.run_record()]);self.assertIsNone(m['total_cost']);self.assertIsNone(m['operational_known_cost_subtotal']);self.assertEqual(m['operational_unknown_cost_runs'],1)
    def test_different_currencies_are_not_added(self):
        m=summary([self.run_record(currency='USD',known=.1),self.run_record(currency='CNY',known=.2)]);self.assertIsNone(m['operational_known_cost_subtotal']);self.assertEqual(m['operational_known_cost_by_currency'],{'USD':.1,'CNY':.2})
    def test_only_allowlisted_provider_codes_are_persistable(self):
        self.assertIsNone(classify_http(502,{}, {'error':{'code':'DUMMY-SECRET-CODE'}}).provider_code)
        self.assertEqual(classify_http(429,{}, {'error':{'code':'insufficient_quota'}}).provider_code,'insufficient_quota')
    def test_root_level_rate_limit_fields_are_respected(self):
        self.assertEqual(classify_http(429,{}, {'error':{'code':'rate_limit'},'retry_after_ms':1234}).retry_after,1.234)

class ActualTransportFaultTests(unittest.TestCase):
    def exercise(self,mode):
        from swe_eval.outbound import request_json
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']));calls.append(1)
                if len(calls)==1:
                    if mode=='timeout':time.sleep(.2)
                    else:self.connection.close();return
                raw=json.dumps(completion()).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (OSError,ConnectionError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin='http://127.0.0.1:'+str(server.server_port);m=Metrics()
        with patch.dict(os.environ,{'SWE_APPROVED_PROVIDER_ORIGINS':origin}):
            p=OpenAICompatibleProvider(profile(base_url=origin+'/v1',allow_http=True,request_timeout=.05),'dummy',m,remaining=lambda:5,persist=lambda:None,transport=request_json,retry_policy={'initial_delay':.05,'max_delay':.05,'time_budget':2})
            self.assertEqual(p.complete([])['content'],'SUBMIT')
        self.assertEqual(len(calls),2);self.assertEqual(m.http_attempts,2);self.assertEqual(m.http_retries,1);self.assertTrue(m.billing_uncertain)
    def test_real_read_timeout_then_success(self):self.exercise('timeout')
    def test_real_disconnected_response_then_success(self):self.exercise('reset')

class DispatchAccountingTests(unittest.TestCase):
    def test_disabled_provider_before_dispatch_does_not_invent_http_attempt(self):
        class Runtime:
            def available(self):raise ProviderError('disabled',category='disabled')
            def log(self,*args):pass
        m=Metrics();calls=[]
        p=OpenAICompatibleProvider(profile(),'',m,remaining=lambda:10,persist=lambda:None,runtime=Runtime(),transport=lambda *args:calls.append(args))
        with self.assertRaises(ProviderError):p.complete([])
        self.assertEqual((m.model_requests,m.http_attempts,m.api_errors),(1,0,0));self.assertFalse(calls)
        from swe_eval.analytics import http_attempt_count
        self.assertEqual(http_attempt_count({'metrics':m.model_dump()}),0)

class InterruptedDecisionTests(CenterCase):
    def setUp(self):
        super().setUp();migrate_administration(self.repo);migrate_retries(self.repo);self.repo.acquire('owner',300)
    batch_with_recovery=DurableRecoveryTests.batch_with_recovery
    def test_crash_before_atomic_failure_commit_never_reopens_terminal_batch(self):
        b=self.batch_with_recovery();rid=b['attempts'][0]['run_id'];self.repo.claim('owner',rid)
        self.repo.save_metrics(rid,Metrics(recovery_eligible=True,last_provider_error={'category':'transient_http'}))
        self.repo.release('owner');self.repo.acquire('next-owner',60);self.repo.recover('next-owner')
        self.assertEqual(self.repo.batch(b['id'])['state'],'failed')
        self.assertFalse(self.repo.get(rid)['metrics']['recovery_eligible'])
        self.assertEqual(self.repo.schedule_recoveries('next-owner',self.settings),[])
        self.assertEqual(self.repo.batch(b['id'])['state'],'failed')

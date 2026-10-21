import json,sqlite3,tempfile,unittest
from pathlib import Path
from swe_eval.benchmarks.official import Catalogue,OfficialTask,fingerprint


def record():
    return {"instance_id":"sympy__sympy-20590","repo":"sympy/sympy","base_commit":"a"*40,"problem_statement":"Public issue","version":"1.7","patch":"GOLD_PRIVATE_CANARY","test_patch":"TEST_PRIVATE_CANARY","FAIL_TO_PASS":["EXPECTED_PRIVATE_CANARY"],"PASS_TO_PASS":[],"eval_script":"PRIVATE_SCRIPT","image":"swebench/sweb.eval.x86_64.sympy_1776_sympy-20590:latest","log_parser":"parse_log_sympy","eval_type":"pass_and_fail"}

class DatasetTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.c=Catalogue(Path(self.tmp.name));self.rev="b"*40
    def tearDown(self):self.tmp.cleanup()
    def test_idempotent_pinned_private_import(self):
        r=record();self.assertEqual(self.c.import_records(self.rev,[r,r])["inserted"],1)
        self.assertEqual(self.c.import_records(self.rev,[r])["inserted"],0)
        t=self.c.list_tasks()[0];raw=json.dumps(t.public())
        for v in ("GOLD_PRIVATE_CANARY","TEST_PRIVATE_CANARY","EXPECTED_PRIVATE_CANARY","PRIVATE_SCRIPT","eval_script","FAIL_TO_PASS","test_patch"):
            self.assertNotIn(v,raw)
        self.assertFalse(t.environment_ready);self.assertEqual(t.validation_status,"imported")
        self.assertEqual(self.c.private(self.rev,t.instance_id)["patch"],r["patch"])
        self.assertEqual(t.source_hash,fingerprint(r))
    def test_revision_history_not_overwritten(self):
        r=record();self.c.import_records(self.rev,[r]);r["patch"]="new patch"
        with self.assertRaises(ValueError):self.c.import_records(self.rev,[r])
        self.c.import_records("c"*40,[r]);self.assertEqual(len(self.c.list_tasks()),2)
        self.assertNotEqual(*[t.id for t in self.c.list_tasks()])
    def test_atomic_import_failure_and_duplicate_conflict(self):
        r=record();other=dict(r,problem_statement="different")
        with self.assertRaises(ValueError):self.c.import_records(self.rev,[r,other])
        self.assertFalse(self.c.path.exists())
        self.c.import_records(self.rev,[r]);bad=dict(r,patch="tampered")
        with self.assertRaises(ValueError):self.c.import_records(self.rev,[bad])
        self.assertEqual(self.c.private(self.rev,r["instance_id"]),r)
    def test_malformed_and_injection_metadata(self):
        for field,value in (("instance_id","../../etc/passwd"),("repo","x; rm -rf /"),("base_commit","git checkout HEAD"),("image","evil/registry:latest"),("FAIL_TO_PASS",{})):
            with self.subTest(field=field),self.assertRaises(ValueError):self.c.import_records(self.rev,[dict(record(),**{field:value})])
    def test_no_implicit_schema_creation_or_images(self):
        self.assertEqual(self.c.list_tasks(),[]);self.assertFalse(self.c.path.exists())
        result=self.c.import_records(self.rev,[record()],dry_run=True)
        self.assertEqual(result["records"],1);self.assertFalse(self.c.path.exists())
    def test_validation_status_is_separate_persistent_evidence(self):
        self.c.import_records(self.rev,[record()]);self.c.record_validation(self.rev,record()["instance_id"],"validated",{"image_digest":"sha256:"+"f"*64})
        t=Catalogue(Path(self.tmp.name)).list_tasks()[0];self.assertTrue(t.environment_ready);self.assertIsNotNone(t.last_verified_at)
        self.assertEqual(t.environment_image_digest,"sha256:"+"f"*64)
        self.assertEqual(self.c.list_tasks(status="blocked"),[])

class PatchPolicyTests(unittest.TestCase):
    def test_source_paths_and_forbidden_test_runner_paths(self):
        from swe_eval.benchmarks.official_sandbox import allowed_path
        for p in ('sympy/core/basic.py','requests/sessions.py','new_module.py'):
            self.assertTrue(allowed_path(p),p)
        for p in ('../secret','.git/config','/etc/passwd','a/../../b','tests/test_x.py','sympy/core/tests/test_basic.py','conftest.py','pyproject.toml','setup.py','sitecustomize.py','a\\..\\b','-option'):
            self.assertFalse(allowed_path(p),p)

from test_center import CenterCase
from swe_eval.benchmarks.official import TaskRegistry,PROTOCOL,HARNESS_COMMIT,HARNESS_VERSION
from swe_eval.analytics import comparison,valid,trusted_success
from swe_eval.schema import Metrics,RunState
from swe_eval.service import enqueue
from swe_eval.api import create_app
from fastapi.testclient import TestClient

class OfficialAPITests(CenterCase):
    def import_task(self,instance='sympy__sympy-20590',ready=False):
        c=Catalogue(self.settings.data_dir);r=dict(record(),instance_id=instance)
        c.import_records('b'*40,[r])
        if ready:c.record_validation('b'*40,instance,'validated',{'image_digest':'sha256:'+'f'*64})
        return next(t for t in c.list_tasks() if t.instance_id==instance)
    def test_catalogue_api_auth_and_reference_confidentiality(self):
        t=self.import_task()
        for endpoint in ('/api/v1/tasks','/api/v1/datasets'):
            self.assertEqual(self.client.get(endpoint).status_code,401)
            response=self.client.get(endpoint,headers=self.headers)
            self.assertEqual(response.status_code,200)
            for v in ('GOLD_PRIVATE_CANARY','TEST_PRIVATE_CANARY','EXPECTED_PRIVATE_CANARY','PRIVATE_SCRIPT','test_patch','FAIL_TO_PASS'):
                self.assertNotIn(v,response.text)
        selected=self.client.get('/api/v1/tasks',params={'dataset':t.benchmark,'repo':'sympy/sympy','validation_status':'imported','instance_id':'20590','benchmark_type':'official'},headers=self.headers).json()
        self.assertEqual(len(selected['items']),1);self.assertFalse(selected['items'][0]['environment_ready'])
        self.assertEqual(self.client.post('/api/v1/runs',json={'task_id':t.id,'model_profile_id':'a'},headers=self.headers).status_code,422)
    def test_official_batch_durability_cancellation_and_protocol(self):
        a=self.import_task(ready=True);b=self.import_task('sympy__sympy-20591',True)
        body=dict(name='unit catalogue batch',task_ids=[a.id,b.id],model_profile_ids=['a','b'],attempts=2,idempotency_key='official-sqlite-only-fixture',max_requests=1000)
        response=self.client.post('/api/v1/batches',json=body,headers=self.headers);self.assertEqual(response.status_code,202,response.text)
        batch=response.json();self.assertEqual(batch['total'],8)
        self.assertEqual(len({r['run_id'] for r in batch['attempts']}),8)
        for r in batch['attempts']:
            value=self.repo.get(r['run_id']);self.assertEqual(value['snapshot']['grading_protocol'],PROTOCOL)
            self.assertEqual(value['task']['dataset_version'],'b'*40)
            self.assertEqual(value['snapshot']['official_harness_commit'],HARNESS_COMMIT)
        again=self.client.post('/api/v1/batches',json=body,headers=self.headers).json();self.assertEqual(batch['id'],again['id'])
        with TestClient(create_app(self.settings)) as client:self.assertEqual(client.get('/api/v1/batches/'+batch['id'],headers=self.headers).json()['total'],8)
        stop=self.client.post('/api/v1/batches/'+batch['id']+'/cancel',headers=self.headers).json();self.assertEqual(stop['state'],'cancelled')
        self.assertTrue(all(r['state']=='cancelled' for r in stop['attempts']))
        again=self.client.post('/api/v1/batches/'+batch['id']+'/cancel',headers=self.headers).json();self.assertEqual(again['state'],'cancelled')
    def test_official_report_is_separate_from_v2_success_and_gold_scores(self):
        t=self.import_task(ready=True);registry=TaskRegistry(self.settings)
        r=enqueue(self.repo,registry,self.profiles,t.id,'a');self.repo.acquire('official-unit',60);self.repo.claim('official-unit',r['id'])
        m=Metrics(resolved=True,patch_applied=True,test_result='passed',assertions_expected=2,assertions_executed=2,assertions_passed=2,agent_version='2.4.6',execution_metadata={'grading_protocol':PROTOCOL,'harness_version':HARNESS_VERSION,'harness_commit':HARNESS_COMMIT,'evaluator_image_digest':'sha256:'+'f'*64,'report_sha256':'a'*64,'patch_sha256':'c'*64,'harness_run_id':'unique','evaluation_config_fingerprint':'d'*64,'failure_classification':'resolved'})
        self.repo.transition(r['id'],RunState.EVALUATING);self.repo.transition(r['id'],RunState.COMPLETED,metrics=m)
        actual=self.repo.get(r['id']);self.assertTrue(valid(actual));self.assertFalse(trusted_success(actual))
        result=comparison(self.repo);groups=result['groups'];self.assertEqual(len(groups),1);self.assertEqual(groups[0]['grading_protocol'],PROTOCOL);self.assertFalse(groups[0]['trusted_evidence']);self.assertEqual(groups[0]['metrics']['resolved_rate'],1)
        self.assertEqual(result['methodology']['grading_protocol'],PROTOCOL)
        self.assertEqual(result['methodology']['grading_protocols'],[PROTOCOL])
        self.assertIsNone(self.repo.operations()['last_success_at'])
        detail=self.client.get('/api/v1/runs/'+r['id'],headers=self.headers).text
        self.assertIn('harness_run_id',detail);self.assertNotIn('GOLD_PRIVATE_CANARY',detail)
        with self.repo.connect(write=True) as db:db.execute('UPDATE runs SET mode=? WHERE id=?',('patch_verification',r['id']))
        self.assertEqual(comparison(self.repo)['groups'],[])
    def test_historical_official_summary_filters_unknown_fields(self):
        from swe_eval.diagnostics import log_message
        safe=log_message('official_grading_summary',json.dumps({'classification':'unresolved','assertions_expected':2,'harness_version':'5.0.2','gold_patch':'GOLD_PRIVATE_CANARY','expected':['EXPECTED_PRIVATE_CANARY']}))
        self.assertNotIn('CANARY',safe);self.assertIn('unresolved',safe)
    def test_validation_observation_does_not_change_task_experiment_identity(self):
        from swe_eval.center import snapshot
        t=self.import_task(ready=True);a=snapshot(t,self.profiles['a'])
        other=t.model_copy(update={'last_verified_at':999,'validation_status':'validated'})
        self.assertEqual(a['task_fingerprint'],snapshot(other,self.profiles['a'])['task_fingerprint'])

class HarnessContractTests(unittest.TestCase):
    """Local contracts only; genuine official runtime evidence is recorded separately."""
    def test_different_patches_and_replays_never_share_harness_cache_identity(self):
        from swe_eval.config import Settings
        from swe_eval.official_harness import OfficialHarness
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            settings=Settings(Path(d),Path(d)/'unused-models');c=Catalogue(settings.data_dir);c.import_records('b'*40,[record()]);t=c.list_tasks()[0]
            captured=[]
            def bridge(request,directory,**kwargs):
                captured.append(request);return {'classification':'unresolved','resolved':False,'image_digest':'sha256:'+'f'*64}
            h=OfficialHarness(settings)
            with patch.object(h,'prepare',return_value='sha256:'+'f'*64),patch.object(h,'bridge',side_effect=bridge),patch('swe_eval.official_harness.cleanup_containers',return_value=True):
                values=[h.evaluate(t,p,'attempt1','profile','service') for p in ('patch-a','patch-b','patch-a')]
            self.assertEqual(len({v['harness_run_id'] for v in values}),3)
            self.assertNotEqual(values[0]['patch_sha256'],values[1]['patch_sha256'])
            self.assertNotEqual(values[0]['evaluation_config_fingerprint'],values[1]['evaluation_config_fingerprint'])
            for req in captured:
                self.assertEqual(req['prediction']['instance_id'],t.instance_id)
                self.assertNotIn('api_key',json.dumps(req['prediction']))
    def test_timeout_and_unavailable_harness_keep_attempt_and_patch_provenance(self):
        from swe_eval.config import Settings
        from swe_eval.official_harness import OfficialHarness
        from swe_eval.sandbox import ExecutionTimeout
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            settings=Settings(Path(d),Path(d)/'unused');c=Catalogue(settings.data_dir);c.import_records('b'*40,[record()]);t=c.list_tasks()[0];h=OfficialHarness(settings)
            for error,status in [(ExecutionTimeout('timeout'),'timeout'),(OSError('private diagnostic'),'environment_failure')]:
                with patch.object(h,'prepare',return_value='sha256:'+'f'*64),patch.object(h,'bridge',side_effect=error),patch('swe_eval.official_harness.cleanup_containers',return_value=True):
                    value=h.evaluate(t,'candidate patch','attempt1','profile','service')
                self.assertEqual(value['classification'],status);self.assertIsNone(value['resolved']);self.assertTrue(value['harness_run_id']);self.assertEqual(len(value['patch_sha256']),64);self.assertNotIn('private diagnostic',json.dumps(value))

import os,uuid
@unittest.skipUnless(os.environ.get('SWE_SWEBENCH_RUNTIME_TESTS')=='1','requires prepared official image and isolated harness venv')
class OfficialDockerRuntimeTests(unittest.TestCase):
    def setUp(self):
        from swe_eval.config import Settings
        from swe_eval.official_harness import OfficialHarness
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=Settings(Path(self.tmp.name),Path(self.tmp.name)/'unused-models')
        source=Catalogue(Path(os.environ['SWE_TEST_SWEBENCH_DATA_DIR']))
        public=next(t for t in source.list_tasks() if t.instance_id=='sympy__sympy-20590')
        self.private=source.private(public.dataset_version,public.instance_id)
        self.harness=OfficialHarness(self.settings)
        self.harness.catalogue.import_records(public.dataset_version,[self.private])
        self.task=self.harness.catalogue.list_tasks()[0]
        self.image=self.harness.prepare(self.task)
        self.service='test-official-'+uuid.uuid4().hex
    def test_pristine_coding_repository_and_actual_patch_policy_handoff(self):
        from swe_eval.benchmarks.official_sandbox import OfficialCodingSandbox
        from swe_eval.sandbox import cleanup_containers
        run=uuid.uuid4().hex
        box=OfficialCodingSandbox('docker',self.service,run,self.task,image_digest=self.image)
        try:
            box.prepare(None,self.task)
            self.assertEqual(box.command('git status --porcelain',30).output.strip(),'')
            box.command("printf '\\n# Infrastructure probe\\n' >> sympy/core/basic.py",30)
            patch=box.capture_patch(self.task.base_commit)
            self.assertIn('sympy/core/basic.py',patch);self.assertNotIn('egg-info',patch)
        finally:box.close()
        check=OfficialCodingSandbox('docker',self.service,run,self.task,image_digest=self.image)
        try:
            check.prepare(None,self.task);self.assertTrue(check.apply_patch(patch,self.task))
            self.assertFalse(check.apply_patch('not a patch',self.task))
        finally:check.close()
        self.assertTrue(cleanup_containers('docker',self.service))
    def test_genuine_official_gold_negative_invalid_and_timeout(self):
        h=self.harness;t=self.task
        gold=h.evaluate(t,self.private['patch'],uuid.uuid4().hex,'gold-validation',self.service,timeout=90)
        self.assertEqual(gold['classification'],'resolved');self.assertTrue(gold['resolved']);self.assertGreater(gold['assertions_expected'],0);self.assertEqual(gold['assertions_expected'],gold['assertions_passed'])
        negative=h.evaluate(t,'',uuid.uuid4().hex,'unmodified-validation',self.service,timeout=90,skip_patch=True)
        self.assertEqual(negative['classification'],'unresolved');self.assertFalse(negative['resolved']);self.assertGreater(negative['parsed_tests'],0)
        invalid=h.evaluate(t,'not a patch\n',uuid.uuid4().hex,'invalid-validation',self.service,timeout=90)
        self.assertEqual(invalid['classification'],'patch_rejected');self.assertFalse(invalid['patch_applied'])
        timeout=h.evaluate(t,self.private['patch'],uuid.uuid4().hex,'timeout-validation',self.service,timeout=1)
        self.assertEqual(timeout['classification'],'timeout');self.assertIsNone(timeout['resolved'])
        self.assertEqual(len({x['harness_run_id'] for x in (gold,negative,invalid,timeout)}),4)

class DatasetTransactionTests(unittest.TestCase):
    def test_partial_import_rolls_back_and_resume_preserves_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            c=Catalogue(Path(d));revision='b'*40;c.import_records(revision,[record()])
            first=dict(record(),instance_id='aaa__aaa-1',repo='aaa/aaa')
            conflict=dict(record(),patch='modified immutable patch')
            with self.assertRaises(ValueError):c.import_records(revision,[first,conflict])
            self.assertEqual(len(c.list_tasks()),1)
            c.import_records(revision,[first,record()]);self.assertEqual(len(c.list_tasks()),2)
            self.assertEqual(c.import_records(revision,[first,record()])['inserted'],0)

class OfficialEmptyPredictionTests(unittest.TestCase):
    def test_only_documented_official_empty_prediction_can_complete_without_test_verdict(self):
        import hashlib
        from swe_eval.storage import SQLiteRepository,Conflict
        from swe_eval.analytics import valid
        repo=SQLiteRepository(Path('/unused'))
        metrics=Metrics(resolved=False,test_result='not_run',execution_metadata={'grading_protocol':PROTOCOL,'harness_version':HARNESS_VERSION,'failure_classification':'empty_patch_skipped','patch_sha256':hashlib.sha256(b'').hexdigest(),'harness_run_id':'unique','evaluation_config_fingerprint':'fingerprint'})
        data=json.loads(repo._metrics_json(metrics,RunState.COMPLETED));self.assertFalse(data['resolved']);self.assertEqual(data['test_result'],'not_run');self.assertIsNone(data['patch_applied'])
        for key,value in [('grading_protocol','swe-eval-grading-v2'),('patch_sha256','different-patch'),('harness_run_id',None)]:
            invalid=metrics.model_copy(deep=True);invalid.execution_metadata[key]=value
            with self.assertRaises(Conflict):repo._metrics_json(invalid,RunState.COMPLETED)
        with self.assertRaises(Conflict):repo._metrics_json(Metrics(),RunState.COMPLETED)

class OfficialEnvironmentClassificationTests(unittest.TestCase):
    def test_only_actual_test_output_defines_observed_network_fault_when_runner_executed(self):
        from swe_eval.swebench_bridge import test_output_region
        start='>>>>> Start Test Output';end='>>>>> End Test Output'
        warning='Temporary failure in name resolution'
        text=warning+'\n'+start+'\nreal failing test\n'+end+'\ncleanup'
        self.assertNotIn(warning,test_output_region(text,True,start,end))
        actual=start+'\n'+warning+'\n'+end
        self.assertIn(warning,test_output_region(actual,True,start,end))
        self.assertIn(warning,test_output_region(text,False,start,end))

class ContainerCleanupRaceTests(unittest.TestCase):
    def test_concurrent_removal_requires_fresh_confirmed_absence(self):
        from unittest.mock import patch
        from swe_eval.sandbox import cleanup_containers,CommandResult
        for final,expected in [(CommandResult(0,''),True),(CommandResult(0,'still-present'),False),(CommandResult(1,'daemon unavailable'),False)]:
            with self.subTest(expected=expected,output=final.output),patch('swe_eval.sandbox.run_process',side_effect=[CommandResult(0,'container-id'),CommandResult(1,'No such container'),final]) as run:
                self.assertIs(cleanup_containers('docker','service','attempt'),expected)
                self.assertEqual(run.call_args.args[0],['docker','ps','--all','--quiet','--filter','label=swe-eval.service=service','--filter','label=swe-eval.run=attempt'])

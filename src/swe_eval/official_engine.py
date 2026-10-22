"""Official tasks share the accepted queue/supervisor, never the local v2 grader."""
import time
from .agent import MiniSWEAgent,verify_mini_api
from .providers import OpenAICompatibleProvider
from .schema import Metrics,RunState
from .sandbox import Cancelled,ExecutionTimeout,SandboxError
from .service import model_snapshot
from .official_harness import OfficialHarness
from .benchmarks.official import PROTOCOL
from .benchmarks.official_sandbox import OfficialCodingSandbox

def stable_task(task):
    value=task.model_dump(mode="json") if hasattr(task,"model_dump") else dict(task)
    return {k:v for k,v in value.items() if k not in ("last_verified_at","validation_status","environment_ready")}

class OfficialEvaluationEngine:
    def __init__(self,repo,benchmark,profiles,settings):
        self.repo,self.benchmark,self.profiles,self.settings=repo,benchmark,profiles,settings
    def execute(self,run_id,*,supplied_patch=None):
        record=self.repo.get(run_id)
        if not record or record["state"]!=RunState.PREPARING:raise ValueError("official evaluation requires claimed run")
        metrics=Metrics.model_validate(record["metrics"]);started=time.monotonic();box=None
        grading_started=False
        state,error=RunState.COMPLETED,None;duration=record["task"]["time_limit"]
        def remaining():
            if self.repo.get(run_id)["cancel_requested"]:raise Cancelled("evaluation cancelled")
            seconds=duration-(time.monotonic()-started)
            if record.get('batch'):
                batch=self.repo.batch(record['batch']['batch_id'])
                if batch['cancel_requested'] or batch['deadline']<=time.time():raise Cancelled('batch stopped')
                seconds=min(seconds,batch['deadline']-time.time())
            if seconds<=0:raise ExecutionTimeout("official evaluation duration exceeded")
            return seconds
        def persist():
            metrics.wall_seconds=round(time.monotonic()-started,4);self.repo.save_metrics(run_id,metrics)
        def log(event,message):self.repo.log(run_id,event,message)
        try:
            task=self.benchmark.get_task(record["task"]["id"]);profile=self.profiles[record["model"]["id"]]
            if stable_task(task)!=stable_task(record["task"]):raise SandboxError("official task provenance changed after submission")
            if not task.environment_ready:raise SandboxError("official environment not validated")
            if model_snapshot(profile)!=record["model"]:raise SandboxError("model configuration changed after submission")
            snap=record.get("snapshot") or {}
            if snap.get("grading_protocol")!=PROTOCOL:raise SandboxError("official grading protocol mismatch")
            effective=snap["effective_model"]
            profile=profile.model_copy(update={k:effective[k] for k in ("max_evaluation_duration","max_agent_steps","max_model_calls","max_output_tokens","max_total_tokens","reasoning_effort")})
            duration=min(task.time_limit,profile.max_evaluation_duration)
            metrics.requested_reasoning_effort=profile.reasoning_effort
            if record["mode"]=="agent" and supplied_patch is not None:raise SandboxError("agent run cannot accept supplied patch")
            if record["mode"]!="agent" and supplied_patch is None:raise SandboxError("patch verification requires explicit patch")
            metrics.execution_metadata={"grading_protocol":PROTOCOL,"harness_version":task.harness_version,"dataset_revision":task.dataset_version,"instance_id":task.instance_id}
            harness=OfficialHarness(self.settings);image=harness.prepare(task)
            metrics.execution_metadata={"grading_protocol":PROTOCOL,"network":"none","uid":10001,"base_commit":task.base_commit,"mode":record["mode"],"harness_version":task.harness_version,"harness_commit":task.harness_commit,"dataset_revision":task.dataset_version,"instance_id":task.instance_id,"repo":task.repo,"evaluator_image_digest":image,"trust_boundary":"official test-log report; distinct from isolated grading-v2"}
            def create():return OfficialCodingSandbox(self.settings.docker_bin,self.repo.service_id,run_id,task,image_digest=image,remaining=remaining,check=lambda:remaining())
            if supplied_patch is None:
                from .config import resolve_key
                metrics.agent_version=verify_mini_api()[3]
                box=create();box.prepare(None,task);metrics.execution_metadata["agent_image_digest"]=box.image_digest
                self.repo.transition(run_id,RunState.RUNNING);persist()
                key=resolve_key(profile,self.settings);self.repo.redact.add(key)
                from .retries import RetryRuntime
                provider=OpenAICompatibleProvider(profile,key,metrics,remaining=remaining,persist=persist,retry_policy=snap.get('api_retry',{'enabled':False}),runtime=RetryRuntime(self.repo,self.settings,record))
                status=MiniSWEAgent().run(task,box,provider,profile,metrics,persist,log,remaining)
                if status=="TimeExceeded":raise ExecutionTimeout("official agent duration exceeded")
                patch=box.capture_patch(task.base_commit);box.close();box=None
            else:
                patch=supplied_patch;log("patch_verification","Official patch verification; excluded from model scoring")
            self.repo.save_patch(run_id,patch);self.repo.transition(run_id,RunState.EVALUATING)
            # This sandbox receives no reference patch/test patch/grading script.
            box=create();box.prepare(None,task);allowed=box.apply_patch(patch,task);box.close();box=None
            metrics.patch_applied=allowed;persist()
            if not allowed:
                metrics.resolved=False;metrics.execution_metadata["failure_classification"]="patch_rejected"
                log("patch_rejected","Patch violates official source-path policy or failed exact application")
            else:
                log("official_grading_started","Executing pinned official harness in fresh restricted evaluation container")
                grading_started=True
                result=harness.evaluate(task,patch,run_id,profile.id,self.repo.service_id,timeout=max(1,int(min(task.test_timeout,remaining()))),check=lambda:remaining())
                status=result["classification"];metrics.resolved=result.get("resolved")
                metrics.patch_applied=result.get("patch_applied")
                for key in ("patch_sha256","harness_run_id","evaluation_config_fingerprint","report_sha256"):
                    if key in result:metrics.execution_metadata[key]=result[key]
                metrics.execution_metadata["failure_classification"]=status
                if status in ("resolved","unresolved"):
                    for key in ("assertions_expected","assertions_executed","assertions_passed"):setattr(metrics,key,result[key])
                    if not result.get("report_sha256") or result.get("parsed_tests",0)<=0 or metrics.assertions_expected<=0:raise SandboxError("official report lacks executed-test evidence")
                    if status=="resolved" and not (metrics.resolved is True and metrics.assertions_expected==metrics.assertions_executed==metrics.assertions_passed):raise SandboxError("inconsistent official resolution report")
                    metrics.test_result="passed" if status=="resolved" else "failed"
                elif status in ("empty_patch_skipped","patch_rejected"):
                    metrics.resolved=False;metrics.test_result="not_run"
                elif status=="cancelled":raise Cancelled("official evaluation cancelled")
                elif status=="timeout":raise ExecutionTimeout("official tests timed out")
                else:raise SandboxError("official harness reported infrastructure or evaluation error")
                log("official_grading_summary",__import__("json").dumps({"classification":status,"assertions_expected":metrics.assertions_expected,"assertions_executed":metrics.assertions_executed,"assertions_passed":metrics.assertions_passed,"harness_version":task.harness_version}))
            remaining()
        except Cancelled:
            state,error=RunState.CANCELLED,"evaluation_cancelled";metrics.resolved=None
        except ExecutionTimeout:
            state,error=RunState.TIMEOUT,"official_evaluation_timeout";metrics.resolved=None;metrics.test_result="timeout";metrics.test_execution_errors+=1
        except Exception:
            # Raw upstream exceptions and report/log payloads remain private.
            state,error=RunState.FAILED,"official_environment_or_evaluation_error";metrics.resolved=None
            metrics.execution_metadata.setdefault("failure_classification","model_api_error" if metrics.api_errors else "environment_failure")
            if grading_started:metrics.test_execution_errors+=1
        finally:
            if box:box.close()
            metrics.wall_seconds=round(time.monotonic()-started,4)
            self.repo.transition(run_id,state,error,metrics=metrics)
        return self.repo.get(run_id)

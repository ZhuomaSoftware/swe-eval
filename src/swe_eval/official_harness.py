"""Worker-only integration with the isolated official SWE-bench interpreter."""
from __future__ import annotations
import hashlib,json,os,re,shlex,time,uuid
from pathlib import Path
from .sandbox import SandboxError, ExecutionTimeout, Cancelled, run_process, cleanup_containers
from .benchmarks.official import Catalogue,PROTOCOL,HARNESS_COMMIT,HARNESS_VERSION,fingerprint

class OfficialHarness:
    def __init__(self,settings):
        self.settings=settings
        self.python=getattr(settings,"swebench_python",None) or os.getenv("SWE_SWEBENCH_PYTHON","/opt/swebench/bin/python")
        self.catalogue=Catalogue(settings.data_dir)
    def bridge(self,request,directory,*,timeout=600,check=lambda:None):
        directory=Path(directory);directory.mkdir(parents=True,mode=0o700,exist_ok=False)
        request_path=directory/"request.json";output=directory/"safe-result.json"
        request_path.write_text(json.dumps(request));request_path.chmod(0o600)
        # cwd cannot be selected by dataset or candidate metadata.
        import subprocess
        script=Path(__file__).with_name("swebench_bridge.py")
        start=time.monotonic()
        with (directory/"process-private.log").open("wb") as logs:
            process=subprocess.Popen([self.python,str(script),str(request_path),str(output)],cwd=directory,stdout=logs,stderr=logs,env=dict({k:v for k,v in os.environ.items() if k in ("PATH","DOCKER_HOST","DOCKER_API_VERSION","SSL_CERT_FILE","REQUESTS_CA_BUNDLE")},HOME=str(directory),HF_HOME=str(directory/"hf-cache")))
            try:
                while process.poll() is None:
                    check()
                    if time.monotonic()-start>=timeout: raise ExecutionTimeout("official harness wall-clock timeout")
                    time.sleep(.1)
            finally:
                if process.poll() is None:process.kill()
                process.wait()
        if not output.exists():return {"classification":"evaluation_error","resolved":None,"reason":"missing_harness_result"}
        value=json.loads(output.read_text())
        if process.returncode and value.get("classification") not in ("environment_failure",):return {"classification":"evaluation_error","resolved":None}
        return value
    def import_dataset(self,revision="main",*,instance_ids=None,repo=None,limit=None,dry_run=False,validation_status=None):
        path=self.settings.data_dir/"datasets"/"imports"/uuid.uuid4().hex
        result=self.bridge({"operation":"download","revision":revision},path,timeout=300)
        if "records" not in result:raise ValueError("official metadata download failed; private import diagnostics retained")
        rows=[r for r in result["records"] if (not instance_ids or r["instance_id"] in instance_ids) and (not repo or r["repo"]==repo)]
        if validation_status:
            statuses={t.instance_id:t.validation_status for t in self.catalogue.list_tasks(revision=result["revision"])}
            rows=[r for r in rows if statuses.get(r["instance_id"],"imported")==validation_status]
        rows=sorted(rows,key=lambda r:r["instance_id"])
        if limit is not None:rows=rows[:limit]
        if not rows:raise ValueError("no matching official metadata records")
        return self.catalogue.import_records(result["revision"],rows,dry_run=dry_run)
    def prepare(self,task,*,pull=False):
        r=self.catalogue.private(task.dataset_version,task.instance_id)
        # No evaluation-time pulls or arbitrary image names. Docker prep is explicit.
        if pull:
            result=run_process([self.settings.docker_bin,"pull","--platform=linux/amd64",r["image"]],timeout=900,max_output=65536)
            logs=self.settings.data_dir/"datasets"/"preparation"
            logs.mkdir(parents=True,mode=0o700,exist_ok=True)
            file=logs/(task.instance_id+"-"+uuid.uuid4().hex+".log")
            file.write_text(result.output);file.chmod(0o600)
            if result.returncode:raise SandboxError("official image preparation failed")
        info=run_process([self.settings.docker_bin,"image","inspect",r["image"]],timeout=30)
        if info.returncode:raise SandboxError("official environment missing; explicit dataset validation/preparation required")
        data=json.loads(info.output)[0]
        if data.get("Architecture")!="amd64": raise SandboxError("unverified official image architecture")
        if task.environment_image_digest and task.environment_image_digest!=data["Id"]:
            raise SandboxError("official image changed since validation; revalidate explicitly")
        return data["Id"]
    def evaluate(self,task,patch,run_id,profile_id,service_id,*,timeout=600,check=lambda:None,skip_patch=False):
        patch_hash=hashlib.sha256(patch.encode()).hexdigest()
        # Attempt+patch+dataset+harness+config plus nonce: no cross-patch cache reuse.
        identity=fingerprint({"run":run_id,"patch":patch_hash,"revision":task.dataset_version,"instance":task.instance_id,"source":task.source_hash,"harness":HARNESS_COMMIT,"model_profile":profile_id,"runtime":task.runtime.model_dump(),"shim":hashlib.sha256(Path(__file__).with_name("swebench_bridge.py").read_bytes()).hexdigest()})
        harness_id="sec-"+identity[:24]+"-"+uuid.uuid4().hex[:12]
        directory=self.settings.data_dir/"datasets"/"evaluations"/harness_id
        image=self.prepare(task)
        row=self.catalogue.private(task.dataset_version,task.instance_id)
        if fingerprint(row)!=task.source_hash:raise SandboxError("immutable official task provenance mismatch")
        request={"operation":"evaluate","record":row,"prediction":{"instance_id":task.instance_id,"model_name_or_path":"profile-"+hashlib.sha256(profile_id.encode()).hexdigest()[:16],"model_patch":patch},"harness_run_id":harness_id,"image_digest":image,"service_id":service_id,"run_id":run_id,"timeout":timeout,"skip_patch":skip_patch}
        try:
            if not patch and not skip_patch:
                # Official CLI excludes empty predictions before starting tests.
                directory.mkdir(parents=True,mode=0o700,exist_ok=False)
                result={"classification":"empty_patch_skipped","resolved":False,"patch_applied":None,"tests_executed":False,"harness_version":HARNESS_VERSION,"image_digest":image}
                (directory/"safe-result.json").write_text(json.dumps(result))
            else:
                result=self.bridge(request,directory,timeout=timeout+30,check=check)
        except (ExecutionTimeout,Cancelled) as error:
            result={"classification":"timeout" if isinstance(error,ExecutionTimeout) else "cancelled","resolved":None,"image_digest":image}
            if directory.exists():(directory/"safe-result.json").write_text(json.dumps(result))
        except (OSError,ValueError):
            result={"classification":"environment_failure","resolved":None,"image_digest":image}
            if directory.exists():(directory/"safe-result.json").write_text(json.dumps(result))
        finally:
            cleaned=cleanup_containers(self.settings.docker_bin,service_id,run_id)
        if not cleaned:result=dict(result,classification="environment_failure",resolved=None,reason="container_cleanup_failed")
        return dict(result,grading_protocol=PROTOCOL,patch_sha256=patch_hash,harness_run_id=harness_id,harness_version=HARNESS_VERSION,harness_commit=HARNESS_COMMIT,evaluation_config_fingerprint=identity,dataset_revision=task.dataset_version,instance_id=task.instance_id)

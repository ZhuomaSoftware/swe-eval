"""Runs ONLY in the dedicated official-harness venv. No mini-agent dependencies.

Version-pinned shim: upstream orchestration/parsers are unchanged; replace its
unsafe container defaults and bound output capture. Raw artifacts are private.
"""
import contextlib, hashlib, io, json, os, re, sys, time, urllib.request, tarfile, subprocess
from pathlib import Path

VERSION="5.0.2"

def test_output_region(content,found,start,end):
    return content.split(start,1)[-1].split(end,1)[0] if found else content

def download(revision):
    from datasets import load_dataset
    import huggingface_hub
    if not re.fullmatch(r"[a-f0-9]{40}|main",revision): raise ValueError("invalid revision")
    info=huggingface_hub.HfApi().dataset_info("SWE-bench/SWE-bench_Verified",revision=revision)
    rows=load_dataset("SWE-bench/SWE-bench_Verified",revision=info.sha,split="test")
    return {"revision":info.sha,"records":list(rows)}

def evaluate(request):
    import swebench, docker
    if swebench.__version__!=VERSION: raise RuntimeError("incompatible official harness")
    manifest=json.loads(Path(__file__).with_name("swebench_upstream.json").read_text())
    package=Path(swebench.__file__).parent
    if any(hashlib.sha256((package/name).read_bytes()).hexdigest()!=expected for name,expected in manifest["files"].items()):
        raise RuntimeError("official harness source does not match the pinned upstream commit")
    import swebench.harness.run_evaluation as runner
    from swebench.harness.utils import make_test_spec
    from swebench.harness.docker_utils import copy_to_container
    from swebench.harness.grading import get_logs_eval
    from swebench.harness.infra_failure import classify_logs,classify_text,TIER_ENVIRONMENT
    from swebench.harness.constants import START_TEST_OUTPUT,END_TEST_OUTPUT
    row=request["record"];pred=request["prediction"];run_id=request["harness_run_id"]
    image=request["image_digest"];service=request["service_id"];run=request["run_id"]
    client=docker.from_env(timeout=60)
    # Never pull images while evaluating candidate work. Preparation is separate.
    local=client.images.get(image)
    if local.id!=image: raise ValueError("image identity changed")
    row=dict(row,image=image)
    spec=make_test_spec(row)
    labels={"swe-eval.service":service,"swe-eval.run":run,"swe-eval.harness":VERSION}
    created=[];probe={}
    def create(test_spec,client,official_run_id,logger):
        seed=client.containers.create(image,command=["/bin/true"],network_mode="none",cap_drop=["ALL"],labels=labels)
        created.append(seed)
        stream,_=seed.get_archive("/testbed")
        data=bytearray()
        for block in stream:
            data.extend(block)
            if len(data)>256*1024*1024: raise RuntimeError("repository archive limit exceeded")
        seed.remove(force=True);created.remove(seed)
        c=client.containers.create(image,name="swe-"+service[:12]+"-"+run+"-official",user="root",command=["/bin/sleep","infinity"],entrypoint=[],working_dir="/testbed",network_mode="none",read_only=True,cap_drop=["ALL"],security_opt=["no-new-privileges:true"],mem_limit="2g",memswap_limit="2g",nano_cpus=1000000000,pids_limit=256,log_config=docker.types.LogConfig(type="none"),tmpfs={"/tmp":"rw,nosuid,nodev,size=128m,mode=1777","/testbed":"rw,exec,nosuid,nodev,size=1024m","/root":"rw,nosuid,nodev,size=16m"},environment={"PYTHONDONTWRITEBYTECODE":"1"},labels=labels)
        created.append(c)
        # Re-root the archive into the writable tmpfs, never extract on host.
        target=io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(data)) as src,tarfile.open(fileobj=target,mode="w") as dst:
            for member in src:
                parts=Path(member.name).parts
                if not parts or parts[0]!="testbed" or ".." in parts:raise ValueError("unsafe repository archive")
                if len(parts)==1:continue
                member.name="/".join(parts[1:])
                if member.islnk() or member.issym():
                    if member.linkname.startswith("/") or ".." in Path(member.linkname).parts:raise ValueError("unsafe repository link")
                if not (member.isfile() or member.isdir() or member.issym()):raise ValueError("unsupported repository entry")
                dst.addfile(member,src.extractfile(member) if member.isfile() else None)
        c.start()
        subprocess.run(["docker","exec","-i",c.id,"tar","--extract","--no-same-owner","-C","/testbed"],input=target.getvalue(),check=True,timeout=60,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        c.reload();probe.update({"image_digest":c.image.id,"host_config":{k:c.attrs["HostConfig"].get(k) for k in ("NetworkMode","ReadonlyRootfs","CapDrop","CapAdd","SecurityOpt","Memory","MemorySwap","NanoCpus","PidsLimit","Binds","Tmpfs")},"mounts":c.attrs["Mounts"]})
        # Upstream starts it once more; Docker start on a running container is idempotent.
        return c
    def copy(container,source,destination):
        if str(destination)=="/eval.sh": destination=Path("/tmp/eval.sh")
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode="w") as tar:
            tar.add(source,arcname=destination.name)
        subprocess.run(["docker","exec","-i",container.id,"tar","--extract","--no-same-owner","-C",str(destination.parent)],input=archive.getvalue(),check=True,timeout=30,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def execute(container,command,timeout):
        # CLI call has an outer absolute deadline; output is bounded on this channel too.
        if command=="/bin/bash /eval.sh": command="/bin/bash /tmp/eval.sh"
        start=time.monotonic();out=bytearray();result=container.exec_run(command,stream=True)
        for block in result.output:
            out.extend(block)
            if len(out)>8*1024*1024: raise RuntimeError("official test output limit exceeded")
            if time.monotonic()-start>timeout:
                container.kill();return out.decode(errors="replace"),True,time.monotonic()-start
        return out.decode(errors="replace"),False,time.monotonic()-start
    runner.create_container=create;runner.copy_to_container=copy;runner.exec_run_with_timeout=execute
    try:
        result=runner.run_instance(spec,pred,client,run_id,timeout=request["timeout"],skip_patch=request.get("skip_patch",False))
        logdir=runner.RUN_EVALUATION_LOG_DIR/run_id/pred["model_name_or_path"].replace("/","__")/row["instance_id"]
        (Path("isolation.json")).write_text(json.dumps(probe,indent=2))
        if result:
            report=result[1][row["instance_id"]]
            status_map,found=get_logs_eval(spec,logdir/"test_output.txt")
            content=(logdir/"test_output.txt").read_text(errors="replace")
            # Preparation warnings outside the actual test runner output do not
            # demonstrate that the evaluated tests suffered an environment fault.
            region=test_output_region(content,found,START_TEST_OUTPUT,END_TEST_OUTPUT)
            infra=classify_text(region)
            if report.get("infra_failure") or (report.get("resolved") is not True and infra and infra[1]==TIER_ENVIRONMENT): status="environment_failure"
            elif not found or not report.get("patch_successfully_applied"):status="evaluation_error"
            else:status="resolved" if report.get("resolved") is True else "unresolved"
            ts=report.get("tests_status",{});groups=[ts.get(k,{}) for k in ("FAIL_TO_PASS","PASS_TO_PASS")]
            def observed(case):
                if case in status_map:return True
                # Match upstream's truncated pytest-parameter compatibility only.
                matches=[key for key in status_map if key.startswith(case)] if case.count("[")>case.count("]") else []
                return bool(matches) and len({status_map[key] in ("PASSED","XFAIL") for key in matches})==1
            executed=sum(observed(case) for case in spec.FAIL_TO_PASS+spec.PASS_TO_PASS)
            passed=sum(len(g.get("success",[])) for g in groups)
            return {"classification":status,"resolved":report.get("resolved") if status in ("resolved","unresolved") else None,"patch_applied":True,"assertions_expected":len(spec.FAIL_TO_PASS)+len(spec.PASS_TO_PASS),"assertions_executed":executed,"assertions_passed":passed,"parsed_tests":len(status_map),"harness_version":VERSION,"image_digest":image,"report_sha256":hashlib.sha256((logdir/"report.json").read_bytes()).hexdigest()}
        text=(logdir/"run_instance.log").read_text(errors="replace") if (logdir/"run_instance.log").exists() else ""
        output=(logdir/"test_output.txt").read_text(errors="replace") if (logdir/"test_output.txt").exists() else ""
        status="timeout" if "timed out" in text.lower() or "Timeout error:" in output else "patch_rejected" if runner.APPLY_PATCH_FAIL in text else "evaluation_error"
        return {"classification":status,"resolved":False if status=="patch_rejected" else None,"patch_applied":False if status=="patch_rejected" else None,"harness_version":VERSION,"image_digest":image}
    finally:
        for c in created:
            try:c.remove(force=True)
            except docker.errors.NotFound:pass
        client.close()

def main():
    os.umask(0o077)
    request=json.loads(Path(sys.argv[1]).read_text());output=Path(sys.argv[2])
    try:
        with open("bridge-private.log","w") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            result=download(request["revision"]) if request["operation"]=="download" else evaluate(request)
        output.write_text(json.dumps(result))
    except Exception as e:
        # Never return exception messages from libraries or reference test names.
        output.write_text(json.dumps({"classification":"environment_failure","error_type":type(e).__name__}))
        raise
if __name__=="__main__":main()

"""Sequential, resumable administrative validation; never a model score."""
import json,shutil,uuid,time
from .official_harness import OfficialHarness
from .benchmarks.official import SUBSET
from .sandbox import run_process, SandboxError

def preflight(settings):
    result=run_process([settings.docker_bin,"info","--format={{json .}}"],timeout=15,max_output=65536)
    if result.returncode:raise SandboxError("Docker unavailable")
    info=json.loads(result.output)
    free=shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else settings.data_dir.parent).free
    memory=info.get("MemTotal",0)
    storage=run_process([settings.docker_bin,"system","df","--format={{json .}}"],timeout=15,max_output=65536)
    probe_image=__import__("os").getenv("SWE_RESOURCE_PROBE_IMAGE","")
    daemon_capacity=None
    if probe_image:
        probe=run_process([settings.docker_bin,"run","--rm","--pull=never","--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges:true","--memory=64m","--pids-limit=32","--entrypoint=df",probe_image,"-Pk","/"],timeout=30,max_output=4096)
        if probe.returncode==0:
            fields=probe.output.splitlines()[-1].split()
            if len(fields)>=4 and fields[3].isdigit():daemon_capacity=int(fields[3])*1024
    return {"architecture":info.get("Architecture"),"docker_version":info.get("ServerVersion"),"docker_memory_bytes":memory,"cpus":info.get("NCPU"),"data_filesystem_free_bytes":free,"concurrency":1,"docker_storage_usage":storage.output if storage.returncode==0 else None,"docker_filesystem_free_bytes":daemon_capacity,"image_preparation_estimate_gb_per_task":8,"ready":free>=10*1024**3 and memory>=6*1024**3 and (daemon_capacity is None or daemon_capacity>=10*1024**3),"limitations":"Official Verified images are amd64; ARM requires verified emulation. Free-space observation is for the mounted data filesystem; monitor daemon storage separately."}

def validate(settings,args,*,check=lambda:None,service_id="phase26-validation",run_id=None,progress=lambda value:None):
    if not 1<=args.timeout<=3600:raise ValueError("validation timeout must be 1..3600")
    h=OfficialHarness(settings);c=h.catalogue
    tasks=c.list_tasks(revision=args.revision,repo=args.repo,status=args.status,subset=SUBSET if args.subset else None)
    if args.instance:tasks=[t for t in tasks if t.instance_id in args.instance]
    if args.limit:tasks=tasks[:args.limit]
    elif not args.subset and not args.instance:tasks=tasks[:1]
    if len(tasks)>20:raise ValueError("at most 20 official environments may be validated per invocation")
    if not tasks:raise ValueError("no matching official instances")
    report={"schema_version":"swe-dataset-validation-v1","preflight":preflight(settings),"items":[]}
    for t in tasks:
        check()
        if args.resume and t.validation_status=="validated":
            report["items"].append({"instance_id":t.instance_id,"status":"validated","resumed":True});continue
        if args.dry_run:
            report["items"].append({"instance_id":t.instance_id,"status":"not_tested","plan":"prepare, official gold, official unmodified evaluation"});continue
        evidence={"source_hash":t.source_hash};status="blocked"
        try:
            if not report["preflight"]["ready"]:raise SandboxError("insufficient disk or RAM")
            image=h.prepare(t,pull=args.prepare);evidence["image_digest"]=image
            private=c.private(t.dataset_version,t.instance_id)
            gold=h.evaluate(t,private["patch"],run_id or uuid.uuid4().hex,"gold-validation",service_id,timeout=args.timeout,check=check)
            evidence["gold"]=gold
            if gold["classification"]!="resolved":status="blocked" if gold["classification"] in ("environment_failure","timeout","evaluation_error") else "failed"
            else:
                negative=h.evaluate(t,"",run_id or uuid.uuid4().hex,"unmodified-validation",service_id,timeout=args.timeout,skip_patch=True,check=check)
                evidence["negative"]=negative
                status="validated" if negative["classification"]=="unresolved" else "blocked" if negative["classification"] in ("environment_failure","timeout","evaluation_error") else "failed"
        except KeyboardInterrupt:
            c.record_validation(t.dataset_version,t.instance_id,"interrupted",evidence);raise
        except (SandboxError,OSError):
            evidence["error"]="environment_preparation_or_harness_unavailable"
        check()
        c.record_validation(t.dataset_version,t.instance_id,status,evidence)
        item={"instance_id":t.instance_id,"status":status,**evidence};report["items"].append(item)
        progress({"completed":len(report["items"]),"selected":len(tasks),"instance_id":t.instance_id,"status":status})
        print(json.dumps({"progress":len(report["items"]),"selected":len(tasks),"instance_id":t.instance_id,"status":status}),flush=True)
        # Stage gate: avoid expensive follow-on pulls when the first task fails.
        if status!="validated" and not getattr(args,"continue_on_error",False):break
    return report

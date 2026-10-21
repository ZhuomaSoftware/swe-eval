"""Pinned official metadata catalogue. Private records never become Task objects."""
from __future__ import annotations
import hashlib, json, re, sqlite3, time
from pathlib import Path
from pydantic import Field
from ..schema import StrictModel, Runtime

DATASET = "SWE-bench/SWE-bench_Verified"
PROTOCOL = "swebench-official-v5"
HARNESS_VERSION = "5.0.2"
HARNESS_COMMIT = "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e"
TASK_REPO_COMMIT = "3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d"
SUBSET = "curated-20-v1"

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class OfficialTask(StrictModel):
    id: str
    benchmark: str = DATASET
    dataset_version: str
    base_commit: str
    issue: str
    instance_id: str
    repo: str
    version: str
    source_hash: str
    benchmark_type: str = "official"
    grading_protocol: str = PROTOCOL
    harness_version: str = HARNESS_VERSION
    harness_commit: str = HARNESS_COMMIT
    subset: str | None = None
    environment_ready: bool = False
    validation_status: str = "imported"
    last_verified_at: float | None = None
    environment_image_digest: str | None = None
    runtime: Runtime = Field(default_factory=lambda: Runtime(agent_image="official-pinned-image",evaluator_image="official-swebench:5.0.2",memory_mb=2048,pids=256,workspace_mb=1024))
    allowed_patch_paths: list[str] = Field(default_factory=lambda: ["**"])
    command_timeout: int = 60
    test_timeout: int = 600
    time_limit: int = 1800
    def public(self):
        return self.model_dump(mode="json")

class Catalogue:
    """Separate private SQLite schema; created only by explicit dataset import."""
    def __init__(self, directory):
        self.directory=Path(directory)/"datasets"
        self.path=self.directory/"catalogue.sqlite3"
    def initialize(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        with sqlite3.connect(self.path) as db:
            v=db.execute("PRAGMA user_version").fetchone()[0]
            if v not in (0,1): raise ValueError("unsupported dataset schema")
            db.executescript("""BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS instances (revision TEXT NOT NULL, instance_id TEXT NOT NULL, source_hash TEXT NOT NULL, private_json TEXT NOT NULL, imported_at REAL NOT NULL, PRIMARY KEY(revision,instance_id));
CREATE TABLE IF NOT EXISTS validations (revision TEXT NOT NULL, instance_id TEXT NOT NULL, at REAL NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL, PRIMARY KEY(revision,instance_id,at));
CREATE TABLE IF NOT EXISTS subsets (revision TEXT NOT NULL, name TEXT NOT NULL, manifest_hash TEXT NOT NULL, ids_json TEXT NOT NULL, PRIMARY KEY(revision,name));
PRAGMA user_version=1; COMMIT;""")
        self.path.chmod(0o600)
    @staticmethod
    def parse(record):
        r=dict(record)
        required=("instance_id","repo","base_commit","problem_statement","version","patch","test_patch","FAIL_TO_PASS","PASS_TO_PASS","image","eval_script","log_parser","eval_type")
        if any(k not in r for k in required): raise ValueError("missing official schema fields")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+",r["instance_id"]): raise ValueError("invalid instance identity")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",r["repo"]): raise ValueError("invalid repository")
        if not r["instance_id"].startswith(r["repo"].replace("/","__")+"-"):raise ValueError("instance identity does not match repository")
        if not re.fullmatch(r"[a-f0-9]{40}",r["base_commit"]): raise ValueError("invalid base commit")
        if not isinstance(r["problem_statement"],str) or not r["problem_statement"]: raise ValueError("empty issue")
        for key in ("FAIL_TO_PASS","PASS_TO_PASS"):
            if isinstance(r[key],str): r[key]=json.loads(r[key])
            if not isinstance(r[key],list) or any(not isinstance(t,str) for t in r[key]): raise ValueError("invalid test metadata")
        for key in ("patch","test_patch","image","eval_script","log_parser","eval_type","version"):
            if not isinstance(r[key],str): raise ValueError("invalid official schema value")
        # Imported image names/scripts are data, never host shell arguments.
        if not re.fullmatch(r"swebench/sweb\.eval\.x86_64\.[a-zA-Z0-9_.-]+:latest",r["image"]): raise ValueError("unapproved official image namespace")
        if r["eval_type"]!="pass_and_fail": raise ValueError("unsupported evaluation type")
        return r
    def import_records(self, revision, records, *, dry_run=False):
        if len(records)>500:raise ValueError("official catalogue import is limited to 500 records per transaction")
        if not re.fullmatch(r"[a-f0-9]{40}",revision): raise ValueError("dataset revision must be a resolved commit")
        parsed=[self.parse(r) for r in records]
        unique={}
        for r in parsed:
            i=r["instance_id"]
            if i in unique and unique[i]!=r: raise ValueError("conflicting duplicate instance")
            unique[i]=r
        if dry_run: return {"revision":revision,"records":len(unique),"dry_run":True}
        self.initialize()
        inserted=0
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            for i,r in sorted(unique.items()):
                h=fingerprint(r);old=db.execute("SELECT source_hash FROM instances WHERE revision=? AND instance_id=?",(revision,i)).fetchone()
                if old and old[0]!=h: raise ValueError("immutable revision content mismatch")
                if not old:
                    db.execute("INSERT INTO instances VALUES (?,?,?,?,?)",(revision,i,h,json.dumps(r),time.time()));inserted+=1
        return {"dataset":DATASET,"revision":revision,"records":len(unique),"inserted":inserted,"images_prepared":0}
    def revisions(self):
        if not self.path.exists(): return []
        with sqlite3.connect(self.path) as db:
            return [{"revision":r,"count":n} for r,n in db.execute("SELECT revision,count(*) FROM instances GROUP BY revision ORDER BY revision")]
    def private(self, revision, instance):
        with sqlite3.connect(f"file:{self.path}?mode=ro",uri=True) as db:
            row=db.execute("SELECT private_json FROM instances WHERE revision=? AND instance_id=?",(revision,instance)).fetchone()
        if not row: raise KeyError(instance)
        return json.loads(row[0])
    def select_subset(self,revision):
        tasks=self.list_tasks(revision=revision);ids=[]
        # Five instances from each of four repositories, lexicographic selection,
        # with the upstream documented SymPy example anchored first.
        for repo in ("sympy/sympy","pytest-dev/pytest","sphinx-doc/sphinx","psf/requests"):
            candidates=sorted(t.instance_id for t in tasks if t.repo==repo)
            if repo=="sympy/sympy" and "sympy__sympy-20590" in candidates:
                candidates.remove("sympy__sympy-20590");candidates.insert(0,"sympy__sympy-20590")
            if len(candidates)<5: raise ValueError("insufficient repository coverage for curated-20-v1")
            ids+=candidates[:5]
        h=fingerprint({"revision":revision,"ids":ids,"policy":SUBSET})
        with sqlite3.connect(self.path) as db:
            old=db.execute("SELECT manifest_hash FROM subsets WHERE revision=? AND name=?",(revision,SUBSET)).fetchone()
            if old and old[0]!=h: raise ValueError("immutable subset mismatch")
            db.execute("INSERT OR IGNORE INTO subsets VALUES (?,?,?,?)",(revision,SUBSET,h,json.dumps(ids)))
        return {"name":SUBSET,"manifest_hash":h,"instance_ids":ids,"label":"SWE-bench Verified — Internal 20-Instance Subset"}
    def list_tasks(self, *, revision=None, repo=None, search=None, status=None, subset=None):
        if not self.path.exists(): return []
        with sqlite3.connect(f"file:{self.path}?mode=ro",uri=True) as db:
            rows=db.execute("SELECT revision,instance_id,source_hash,private_json FROM instances ORDER BY revision,instance_id").fetchall()
            memberships={r:json.loads(ids) for r,ids in db.execute("SELECT revision,ids_json FROM subsets WHERE name=?",(SUBSET,))}
            latest={}
            for rev,i,at,s,e in db.execute("SELECT * FROM validations ORDER BY at"):
                latest[(rev,i)]=(at,s,json.loads(e))
        tasks=[]
        for rev,i,h,raw in rows:
            if revision and rev!=revision: continue
            r=json.loads(raw);at,s,e=latest.get((rev,i),(None,"imported",{}))
            member=SUBSET if i in memberships.get(rev,[]) else None
            if repo and r["repo"]!=repo or status and s!=status or subset and member!=subset: continue
            if search and search.lower() not in (i+" "+r["repo"]+" "+r["problem_statement"]).lower(): continue
            tasks.append(OfficialTask(id="swv-"+i+"-"+rev,dataset_version=rev,base_commit=r["base_commit"],issue=r["problem_statement"],instance_id=i,repo=r["repo"],version=r["version"],source_hash=h,subset=member,environment_ready=s=="validated",validation_status=s,last_verified_at=at,environment_image_digest=e.get("image_digest")))
        return tasks
    def record_validation(self,revision,instance,status,evidence):
        self.private(revision,instance)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO validations VALUES (?,?,?,?,?)",(revision,instance,time.time(),status,json.dumps(evidence)))

class TaskRegistry:
    def __init__(self,settings):
        from .local import LocalBenchmark
        self.local=LocalBenchmark(settings.task_dir);self.catalogue=Catalogue(settings.data_dir)
    def list_tasks(self): return self.local.list_tasks()+self.catalogue.list_tasks()
    def get_task(self,task_id):
        if not task_id.startswith("swv-"): return self.local.get_task(task_id)
        for task in self.catalogue.list_tasks():
            if task.id==task_id:return task
        raise KeyError(task_id)
    def source_archive(self,task): return self.local.source_archive(task)

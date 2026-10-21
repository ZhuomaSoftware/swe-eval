"""Hidden-free coding and patch-policy precheck using official base images."""
import re
from ..sandbox import DockerSandbox,SandboxError

def allowed_path(path):
    parts=path.replace("\\","/").split("/")
    if not path or path.startswith(("/","-")) or any(x in ("..",".git","") for x in parts):return False
    if any(x.lower() in ("test","tests","testing",".github",".pytest_cache") for x in parts):return False
    name=parts[-1].lower()
    if name.startswith("test_") or name.endswith("_test.py"):return False
    return name not in ("conftest.py","pytest.ini","tox.ini","setup.cfg","pyproject.toml","setup.py","sitecustomize.py","usercustomize.py","dockerfile","eval.sh")

class OfficialCodingSandbox(DockerSandbox):
    def __init__(self,docker,service_id,run_id,task,*,image_digest,remaining=lambda:600,check=lambda:None):
        runtime=task.runtime.model_copy(update={"agent_image":image_digest})
        super().__init__(docker,service_id,run_id,task.model_copy(update={"runtime":runtime}),remaining=remaining,check=check)
    def _exec(self,argv,*,timeout=30,stdin=b"",required=False,max_output=1024*1024):
        return self._docker(["exec","-i","--user=10001:10001","--workdir=/workspace",self.name,"/usr/bin/env","-i","PATH=/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/bin:/usr/bin:/bin","HOME=/tmp","LANG=C.UTF-8","PYTHONDONTWRITEBYTECODE=1","GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",*argv],timeout=timeout,stdin=stdin,required=required,max_output=max_output)
    def prepare(self,source,task):
        # Repository contents come only from the already-pinned hidden-free image.
        self._exec(["cp","-R","--no-preserve=ownership","/testbed/.","/workspace"],timeout=60,required=True)
        self._exec(["git","-c","core.hooksPath=/dev/null","checkout","--force","--detach",task.base_commit],required=True)
        self._exec(["git","-c","core.hooksPath=/dev/null","reset","--hard",task.base_commit],required=True)
        self._exec(["git","-c","core.hooksPath=/dev/null","clean","-ffdx"],required=True)
        if self._exec(["git","status","--porcelain"],required=True).output.strip():raise SandboxError("official coding workspace is not pristine")
        if self._exec(["git","rev-parse","HEAD"],required=True).output.strip()!=task.base_commit:raise SandboxError("official base commit mismatch")
    def apply_patch(self,patch,task):
        if patch:
            for args in (["git","-c","core.hooksPath=/dev/null","apply","--check","--index","-"],["git","-c","core.hooksPath=/dev/null","apply","--index","-"]):
                r=self._exec(args,stdin=patch.encode())
                if r.returncode or r.truncated:return False
        paths=self._exec(["git","diff","--name-only","-z",task.base_commit,"--"],required=True)
        changed={path for path in paths.output.split("\0") if path}
        if any(not allowed_path(path) for path in changed):return False
        modes=self._exec(["git","ls-files","--stage","-z"],required=True)
        if any(entry.split("\t",1)[-1] in changed and entry.split(" ",1)[0] not in ("100644","100755") for entry in modes.output.split("\0") if entry):return False
        return True

from __future__ import annotations

import os
import selectors
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .benchmarks.local import SNAPSHOT_COMMIT_MESSAGE
from .schema import Task


class SandboxError(RuntimeError):
    pass


class ExecutionTimeout(SandboxError):
    pass


class Cancelled(SandboxError):
    pass


@dataclass
class CommandResult:
    returncode: int
    output: str
    truncated: bool = False


class Sandbox(Protocol):
    def prepare(self, source: bytes, task: Task) -> None: ...
    def command(self, command: str, timeout: float) -> CommandResult: ...
    def capture_patch(self, base_commit: str) -> str: ...
    def apply_patch(self, patch: str, task: Task) -> bool: ...
    def close(self) -> None: ...


def run_process(argv: list[str], *, timeout: float, stdin: bytes = b"",
                max_output: int = 1024 * 1024, check: Callable[[], None] = lambda: None) -> CommandResult:
    """Bound both wall time and captured output; never invoke a host shell."""
    deadline = time.monotonic() + max(0.01, timeout)
    captured = bytearray()
    truncated = False
    try:
        with tempfile.TemporaryFile() as input_file:
            input_file.write(stdin)
            input_file.seek(0)
            process = subprocess.Popen(argv, stdin=input_file, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
    except OSError:
        raise SandboxError("Docker CLI is unavailable or could not be started") from None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map() or process.poll() is None:
                check()
                if time.monotonic() >= deadline:
                    raise ExecutionTimeout("sandbox operation exceeded execution time limit")
                for key, _ in selector.select(timeout=0.1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = max_output - len(captured)
                    captured.extend(chunk[:remaining])
                    truncated |= len(chunk) > remaining
            return CommandResult(process.wait(), captured.decode("utf-8", errors="replace"), truncated)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


class DockerSandbox:
    def __init__(self, docker: str, service_id: str, run_id: str, task: Task, *, evaluator=False,
                 remaining: Callable[[], float] = lambda: 600,
                 check: Callable[[], None] = lambda: None):
        self.docker, self.task = docker, task
        self.remaining, self.check = remaining, check
        self.name = f"swe-{service_id[:12]}-{run_id}-{'eval' if evaluator else 'agent'}"
        self.image = task.runtime.evaluator_image if evaluator else task.runtime.agent_image
        self.image_digest = None
        self.created = False
        runtime = task.runtime
        argv = [docker, "create", "--pull=never", "--name", self.name,
                "--label", f"swe-eval.service={service_id}", "--label", f"swe-eval.run={run_id}",
                "--network=none", "--read-only", "--user=10001:10001", "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true", f"--cpus={runtime.cpus}",
                f"--memory={runtime.memory_mb}m", f"--memory-swap={runtime.memory_mb}m",
                f"--pids-limit={runtime.pids}", "--ulimit=nofile=1024:1024", "--ulimit=core=0:0",
                "--log-driver=none", "--ipc=private",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
                "--tmpfs", f"/workspace:rw,nosuid,nodev,size={runtime.workspace_mb}m,uid=10001,gid=10001,mode=0700",
                "--workdir=/workspace", "--entrypoint=/bin/sleep", self.image, "infinity"]
        try:
            self._docker(argv[1:], timeout=30, required=True)
            self.created = True
            self._docker(["start", self.name], required=True)
            self.image_digest = self._docker(["inspect", "--format={{.Image}}", self.name], required=True).output.strip()
        except BaseException:
            # Creation might have reached the daemon even when the CLI was interrupted.
            self.close()
            raise

    def _docker(self, args, *, timeout=30, stdin=b"", required=False, max_output=1024 * 1024):
        self.check()
        result = run_process([self.docker, *args], timeout=min(timeout, self.remaining()),
                             stdin=stdin, check=self.check, max_output=max_output)
        if required and (result.returncode or result.truncated):
            # Docker errors can include host paths; persist only a stable safe description.
            raise SandboxError("Docker operation failed; check daemon availability and prebuilt sandbox images")
        return result

    def _exec(self, argv, *, timeout=30, stdin=b"", required=False, max_output=1024 * 1024):
        return self._docker(["exec", "-i", "--user=10001:10001", "--workdir=/workspace", self.name,
                             "/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp",
                             "LANG=C.UTF-8", "LC_ALL=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1",
                             "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
                             *argv], timeout=timeout, stdin=stdin, required=required, max_output=max_output)

    def prepare(self, source, task):
        self._exec(["tar", "--extract", "--file=-", "--no-same-owner", "--no-same-permissions"],
                   stdin=source, required=True)
        if task.repository.kind == "snapshot":
            self._exec(["git", "init", "--initial-branch=main", "."], required=True)
            self._exec(["git", "add", "--all", "--force"], required=True)
            self._exec(["env", "GIT_AUTHOR_DATE=1704067200 +0000", "GIT_COMMITTER_DATE=1704067200 +0000",
                        "git", "-c", "user.name=SWE Eval", "-c", "user.email=fixture@swe-eval.invalid",
                        "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "--quiet",
                        "--allow-empty", "--message", SNAPSHOT_COMMIT_MESSAGE.rstrip("\n")], required=True)
        else:
            self._exec(["git", "clone", "--no-checkout", "/workspace/source.bundle", "/tmp/clone"], required=True)
            self._exec(["bash", "-c", "mv /tmp/clone/.git /workspace/.git; rm /workspace/source.bundle"], required=True)
        self._exec(["git", "checkout", "--force", "--detach", task.base_commit], required=True)
        result = self._exec(["git", "rev-parse", "HEAD"], required=True)
        if result.output.strip() != task.base_commit:
            raise SandboxError("workspace base commit verification failed")

    def command(self, command, timeout):
        # coreutils timeout also kills the command's process group inside the container.
        result = self._exec(["timeout", "--signal=TERM", "--kill-after=1s", f"{max(0.1, timeout):.2f}s",
                             "bash", "--noprofile", "--norc", "-c", command], timeout=timeout + 2)
        if result.returncode in (124, 137):
            self.close()  # Detached descendants must not keep running after a timed-out action.
            raise ExecutionTimeout("sandbox command timed out or exceeded memory limit")
        if result.returncode in (125, 126, 127):
            # These can also be normal shell errors; preserve for agent correction.
            return result
        return result

    def capture_patch(self, base_commit):
        self._exec(["git", "-c", "core.hooksPath=/dev/null", "add", "--intent-to-add", "--all", "--force"], required=True)
        result = self._exec(["git", "-c", "core.hooksPath=/dev/null", "diff", "--no-ext-diff", "--no-textconv",
                             "--binary", base_commit, "--"], max_output=512 * 1024, required=True)
        return result.output

    def apply_patch(self, patch, task):
        if patch:
            for args in (["git", "apply", "--check", "--index", "-"], ["git", "apply", "--index", "-"]):
                result = self._exec(args, stdin=patch.encode())
                if result.returncode or result.truncated:
                    return False
        paths = self._exec(["git", "diff", "--name-only", "-z", task.base_commit, "--"], required=True)
        changed = [path for path in paths.output.split("\0") if path]
        if any(path not in task.allowed_patch_paths for path in changed):
            return False
        modes = self._exec(["git", "ls-files", "--stage", "-z"], required=True)
        if any(entry.split(" ", 1)[0] not in {"100644", "100755"}
               for entry in modes.output.split("\0") if entry):
            return False
        return True

    def tests(self, task):
        results = []
        for argv in task.test_commands:
            result = self.command(shlex.join(argv), task.test_timeout)
            results.append(result)
            if result.returncode:
                break
        return results

    def close(self):
        try:
            run_process([self.docker, "rm", "--force", self.name], timeout=10, max_output=4096)
        except SandboxError:
            pass
        self.created = False


def cleanup_containers(docker: str, service_id: str, run_id: str | None = None):
    args = [docker, "ps", "--all", "--quiet", "--filter", f"label=swe-eval.service={service_id}"]
    if run_id:
        args += ["--filter", f"label=swe-eval.run={run_id}"]
    try:
        result = run_process(args, timeout=10, max_output=65536)
        if result.returncode:
            return False
        ids = result.output.split()
        if ids:
            removal = run_process([docker, "rm", "--force", *ids], timeout=20, max_output=65536)
            return removal.returncode == 0
        return True
    except SandboxError:
        return False

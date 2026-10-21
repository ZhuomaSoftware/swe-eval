from __future__ import annotations

import os
import json
import selectors
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


@dataclass
class GradingResult:
    """Produced by the trusted controller, never by a candidate command."""
    verdict: dict
    operations: list[CommandResult]
    controller_image_digest: str


class Sandbox(Protocol):
    def prepare(self, source: bytes, task: Task) -> None: ...
    def command(self, command: str, timeout: float) -> CommandResult: ...
    def capture_patch(self, base_commit: str) -> str: ...
    def apply_patch(self, patch: str, task: Task) -> bool: ...
    def tests(self, task: Task) -> GradingResult: ...
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
                 trusted_controller=False,
                 remaining: Callable[[], float] = lambda: 600,
                 check: Callable[[], None] = lambda: None):
        self.docker, self.task = docker, task
        self.service_id, self.run_id = service_id, run_id
        self.remaining, self.check = remaining, check
        self.name = f"swe-{service_id[:12]}-{run_id}-{'controller' if trusted_controller else 'eval' if evaluator else 'agent'}"
        # Both coding and evaluation candidates use an image WITHOUT hidden
        # files. Only the controller gets the grader image, never candidate data.
        self.image = task.runtime.evaluator_image if trusted_controller else task.runtime.agent_image
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
        if len(task.test_commands) != 1 or task.test_commands[0][-1] != "judge":
            raise SandboxError("task requires an isolated_operations_v2 controller command ending in judge")
        controller = DockerSandbox(self.docker, self.service_id, self.run_id, task,
                                   trusted_controller=True, remaining=self.remaining, check=self.check)
        started = time.monotonic()

        def budget():
            seconds = min(self.remaining(), task.test_timeout - (time.monotonic() - started))
            if seconds <= 0:
                raise ExecutionTimeout("hidden evaluation time limit exceeded")
            return seconds

        def decode(result):
            if result.returncode or result.truncated:
                raise SandboxError("trusted grading controller did not complete")
            try:
                return json.loads(result.output)
            except (ValueError, RecursionError):
                raise SandboxError("trusted grading controller returned invalid JSON") from None

        try:
            argv = task.test_commands[0]
            plan = decode(controller._exec([*argv[:-1], "plan"], timeout=budget(), max_output=65536))
            if not isinstance(plan, list) or not 1 <= len(plan) <= 100:
                raise SandboxError("invalid grading operation plan")
            observations, operations = [], []
            for request in plan:
                # Stderr is diagnostic only. There is no verdict channel in
                # this container; raw stdout is just an untrusted JSON value.
                result = self._exec(["timeout", "--signal=TERM", "--kill-after=1s", f"{budget():.2f}s",
                                     "bash", "-c", "python3 -I -S /opt/swe-candidate.py 2>/tmp/operation.err"],
                                    stdin=json.dumps(request).encode(), timeout=budget(), max_output=65536)
                diagnostic = self._exec(["cat", "/tmp/operation.err"], timeout=budget(), max_output=8192)
                error, response = None, None
                if result.returncode or result.truncated:
                    error = f"candidate operation exit={result.returncode}, truncated={result.truncated}"
                else:
                    try:
                        response = json.loads(result.output)
                    except (ValueError, RecursionError):
                        error = "candidate operation returned malformed JSON"
                operations.append(CommandResult(result.returncode, diagnostic.output + result.output,
                                                result.truncated or diagnostic.truncated))
                observations.append({"response": response, "error": error})
            verdict = decode(controller._exec(argv, stdin=json.dumps(observations, allow_nan=False).encode(),
                                              timeout=budget(), max_output=131072))
            counts = ("cases_expected", "cases_observed", "assertions_expected", "assertions_executed",
                      "assertions_passed", "execution_errors")
            if (not isinstance(verdict, dict) or verdict.get("protocol") != "swe-eval-grading-v2"
                    or any(type(verdict.get(key)) is not int or verdict[key] < 0 for key in counts)
                    or type(verdict.get("passed")) is not bool
                    or verdict["cases_expected"] != len(plan) or verdict["cases_observed"] != len(plan)):
                raise SandboxError("invalid trusted assertion accounting")
            verified = (verdict["execution_errors"] == 0 and verdict["assertions_expected"] > 0
                        and verdict["assertions_executed"] == verdict["assertions_expected"]
                        and verdict["assertions_passed"] == verdict["assertions_expected"])
            if verdict["passed"] != verified:
                raise SandboxError("inconsistent trusted assertion accounting")
            return GradingResult(verdict, operations, controller.image_digest)
        finally:
            controller.close()

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
            if removal.returncode==0:return True
            # Child shutdown can remove the same labelled container between ps
            # and rm. Confirm absence with a fresh successful daemon query;
            # never treat an unknown/unavailable daemon as cleaned.
            remaining=run_process(args,timeout=10,max_output=65536)
            return remaining.returncode==0 and not remaining.output.strip()
        return True
    except SandboxError:
        return False

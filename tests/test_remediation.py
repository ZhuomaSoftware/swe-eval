"""Permanent acceptance regressions. Candidate code executes only in Docker."""
from __future__ import annotations

import contextlib
import difflib
import io
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_core
import test_docker_integration as integration
from fastapi.testclient import TestClient
from swe_eval.api import create_app
from swe_eval.cli import main
from swe_eval.config import Settings
from swe_eval.schema import Metrics, RunState
from swe_eval.storage import Conflict, SQLiteRepository


# Exact original audit exploit. Do not replace with a weaker approximation.
ORIGINAL_EXPLOIT = '''import os
import re
from pathlib import Path
grader = Path('/opt/hidden/grade.py').read_text()
marker = re.search(r'print\("([^"]+)", flush=True\)', grader).group(1)
os.write(1, (marker + '\\n').encode())
os._exit(0)
'''


@unittest.skipUnless(os.getenv("SWE_DOCKER_TESTS") == "1", "requires actual Docker images")
class GradingIntegrityTests(unittest.TestCase):
    setUp = integration.DockerPipelineTests.setUp
    engine = integration.DockerPipelineTests.engine
    record = integration.DockerPipelineTests.record

    def evaluate_source(self, source, **engine_options):
        task = self.benchmark.get_task("intervals-001")
        original = (self.benchmark.source_path(task) / "intervals.py").read_text()
        diff = "".join(difflib.unified_diff(original.splitlines(keepends=True),
                        source.splitlines(keepends=True), fromfile="a/intervals.py", tofile="b/intervals.py"))
        run = self.record()
        return self.engine(**engine_options).execute(run["id"], supplied_patch=diff)

    def test_original_f01_exploit(self):
        result = self.evaluate_source(ORIGINAL_EXPLOIT)
        self.assertIsNot(result["metrics"]["resolved"], True, result)

    def test_malicious_and_broken_candidates(self):
        sources = {
            "old_marker": "print('SWE_EVAL_REGRESSION_PASSED:9')\n",
            "new_marker": "print('SWE_EVAL_TRUSTED_PASSED:9')\n",
            "exit_zero": "import os\nos._exit(0)\n",
            "exit_import": "raise SystemExit(0)\n",
            "signal_import": "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n",
            "exception_import": "raise RuntimeError('candidate import failed')\n",
            "forged_output": "print('{\"passed\":true,\"assertions_passed\":10}')\n",
            "forged_controller_verdict": "print('{\"protocol\":\"swe-eval-grading-v2\",\"cases_expected\":9,\"cases_observed\":9,\"assertions_expected\":10,\"assertions_executed\":10,\"assertions_passed\":10,\"execution_errors\":0,\"passed\":true}')\n",
            "wrong_fix": "def merge_ranges(ranges):\n    return []\n",
            "malformed_result": "def merge_ranges(ranges):\n    return object()\n",
        }
        for name, source in sources.items():
            with self.subTest(name=name):
                result = self.evaluate_source(source)
                self.assertIsNot(result["metrics"]["resolved"], True, result)

    def test_candidate_hidden_access_denied(self):
        # A correct fix remains correct only if the candidate cannot read hidden
        # logic or find a controller process through its private /proc namespace.
        task = self.benchmark.get_task("intervals-001")
        original = (self.benchmark.source_path(task) / "intervals.py").read_text()
        source = '''from pathlib import Path
assert not Path('/opt/hidden').exists(), 'HIDDEN_FILES_EXPOSED'
assert not Path('/proc/1/root/opt/hidden').exists(), 'HIDDEN_FILES_EXPOSED'
assert not Path('/var/run/docker.sock').exists(), 'SOCKET_EXPOSED'
try:
    Path('/opt/hidden/grade.py').read_text()
except (FileNotFoundError, PermissionError):
    print('HIDDEN_ACCESS_DENIED')
else:
    raise RuntimeError('HIDDEN_FILES_EXPOSED')
''' + original.replace("start < merged[-1][1]", "start <= merged[-1][1]")
        # Verify the original denial marker in private in-memory operations.
        # Public logs must not carry candidate grading output that can echo
        # hidden inputs/answers (Phase 2.5 F-01).
        private_operations = []
        class ObservedSandbox(integration.DockerSandbox):
            def tests(box, task):
                grading = super().tests(task)
                private_operations.extend(grading.operations)
                return grading
        result = self.evaluate_source(source, sandbox_factory=ObservedSandbox)
        self.assertTrue(result["metrics"]["resolved"], result)
        self.assertTrue(any("HIDDEN_ACCESS_DENIED" in operation.output for operation in private_operations))
        logs = self.repo.logs(result["id"], limit=1000)
        self.assertFalse(any("HIDDEN_ACCESS_DENIED" in entry["message"] or "input_after" in entry["message"] for entry in logs))
        for field in ("assertions_expected", "assertions_executed", "assertions_passed"):
            self.assertEqual(result["metrics"][field], 10)

    def test_invalid_patch_rejected_and_failed_assertions_counted(self):
        run = self.record()
        result = self.engine().execute(run["id"], supplied_patch="not a valid patch\n")
        self.assertEqual(result["state"], "completed")
        self.assertIs(result["metrics"]["patch_applied"], False)
        self.assertIs(result["metrics"]["resolved"], False)
        self.assertEqual(result["metrics"]["test_result"], "not_run")
        self.assertIsNone(result["metrics"]["assertions_executed"])
        task = self.benchmark.get_task("intervals-001")
        original = (self.benchmark.source_path(task) / "intervals.py").read_text()
        result = self.evaluate_source(original.replace("start < merged[-1][1]", "start > merged[-1][1]"))
        self.assertFalse(result["metrics"]["resolved"])
        self.assertEqual(result["metrics"]["assertions_executed"], 10)
        self.assertLess(result["metrics"]["assertions_passed"], 10)


class RecoveryIntegrityTests(unittest.TestCase):
    setUp = test_core.StorageTests.setUp
    create = test_core.StorageTests.create

    def active(self, state=RunState.EVALUATING):
        run = self.create()
        self.repo.acquire("worker", 30)
        self.repo.claim("worker", run["id"])
        if state != RunState.PREPARING:
            self.repo.transition(run["id"], state)
        return run["id"]

    def test_original_f02_recovery(self):
        run_id = self.active()
        self.repo.save_metrics(run_id, Metrics(resolved=True, patch_applied=True,
                               test_result="passed", test_exit_codes=[0], input_tokens=71))
        self.repo.recover("worker")
        result = self.repo.get(run_id)
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["metrics"]["resolved"])
        self.assertEqual(result["metrics"]["input_tokens"], 71)
        self.assertEqual(result["metrics"]["test_result"], "passed")

    def test_crash_windows_and_stale_writes(self):
        for state, metrics in [
            (RunState.PREPARING, Metrics()),
            (RunState.RUNNING, Metrics(agent_steps=2, total_tokens=123)),
            (RunState.EVALUATING, Metrics(test_result="not_run", patch_applied=True)),
            (RunState.EVALUATING, Metrics(test_exit_codes=[0], test_result="passed", resolved=True)),
        ]:
            with self.subTest(state=state, metrics=metrics.model_dump()):
                run_id = self.active(state)
                self.repo.save_metrics(run_id, metrics)
                with self.repo.connect(write=True) as db:
                    db.execute("UPDATE worker_lock SET expires_at=0")
                self.assertTrue(self.repo.acquire("replacement", 30))
                self.repo.recover("replacement")
                self.assertIsNone(self.repo.get(run_id)["metrics"]["resolved"])
                with self.assertRaises(Conflict):
                    self.repo.save_metrics(run_id, Metrics(resolved=True, test_result="passed"))
                with self.assertRaises(Conflict):
                    self.repo.transition(run_id, RunState.COMPLETED)
                with self.assertRaises(Conflict):
                    self.repo.save_patch(run_id, "stale patch")
                self.repo.release("replacement")

    def test_atomic_terminal_rollback_and_restart(self):
        run_id = self.active()
        self.repo.save_metrics(run_id, Metrics(resolved=True, patch_applied=True, test_result="passed"))
        with patch.object(self.repo, "_log", side_effect=RuntimeError("injected transaction fault")):
            with self.assertRaises(RuntimeError):
                self.repo.transition(run_id, RunState.COMPLETED)
        self.assertEqual(self.repo.get(run_id)["state"], "evaluating")
        self.repo.recover("worker")
        reopened = SQLiteRepository(self.path)
        reopened.initialize()
        self.assertIsNone(reopened.get(run_id)["metrics"]["resolved"])

    def test_failure_timeout_cancel_normalize_verdict_atomically(self):
        for state in (RunState.FAILED, RunState.TIMEOUT, RunState.CANCELLED):
            run_id = self.active()
            self.repo.save_metrics(run_id, Metrics(resolved=True, patch_applied=True, test_result="passed"))
            self.repo.transition(run_id, state)
            self.assertIsNone(self.repo.get(run_id)["metrics"]["resolved"])

    def test_expired_lease_cannot_write_before_recovery(self):
        run_id = self.active()
        with self.repo.connect(write=True) as db:
            db.execute("UPDATE worker_lock SET expires_at=0")
        for write in (lambda: self.repo.save_metrics(run_id, Metrics(resolved=True)),
                      lambda: self.repo.save_patch(run_id, "stale"),
                      lambda: self.repo.transition(run_id, RunState.FAILED)):
            with self.assertRaises(Conflict):
                write()

    def test_completion_recovery_race_has_one_consistent_terminal_result(self):
        from concurrent.futures import ThreadPoolExecutor
        run_id = self.active()
        self.repo.save_metrics(run_id, Metrics(resolved=True, patch_applied=True, test_result="passed"))
        def complete():
            try:
                self.repo.transition(run_id, RunState.COMPLETED)
            except Conflict:
                pass  # Recovery won this transaction race.
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(complete)
            b = pool.submit(self.repo.recover, "worker")
            a.result()
            b.result()
        result = self.repo.get(run_id)
        self.assertIn(result["state"], ("completed", "failed"))
        self.assertIs(result["metrics"]["resolved"], True if result["state"] == "completed" else None)


class APIHygieneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        models = root / "models.json"
        models.write_text(json.dumps([test_core.profile().model_dump()]))
        self.token = "test-administrator-token-long-enough"
        self.app = create_app(Settings(root / "data", models, self.token))
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + self.token}
        self.body = {"task_id": "intervals-001", "model_profile_id": "test-profile"}

    def test_integer_boundaries(self):
        run = self.client.post("/api/v1/runs", headers=self.headers, json=self.body).json()
        paths = ["/api/v1/runs?offset=", f"/api/v1/runs/{run['id']}/logs?after="]
        for path in paths:
            for value in ("-1", "1.5", "abc", str(2**63), str(10**100)):
                with self.subTest(path=path, value=value):
                    response = self.client.get(path + value, headers=self.headers)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertIsInstance(response.json()["detail"], list)
            for value in ("0", "1", str(2**63-1)):
                self.assertEqual(self.client.get(path + value, headers=self.headers).status_code, 200)

    def test_no_validation_secret_reflection_or_logging(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        for name, secret in {"api_key": "sk-dummy-must-never-be-reflected-12345",
                             "password": "dummy-password-do-not-echo",
                             "Authorization": "Bearer dummy-authorization-token",
                             "bearer": "Bearer dummy-bearer-token"}.items():
            response = self.client.post("/api/v1/runs", headers=self.headers,
                                        json={**self.body, name: secret})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(secret, response.text)
            self.assertIn(name, response.text)
            self.assertNotIn(secret, stream.getvalue())
        malformed = '{"api_key":"sk-malformed-secret-canary",'
        response = self.client.post("/api/v1/runs", headers=self.headers,
                                    content=malformed)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("sk-malformed-secret-canary", response.text)
        for token in ("Bearer dummy-invalid-auth-canary", "Basic dummy-password-canary"):
            response = self.client.get("/api/v1/models", headers={"Authorization": token})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn(token, response.text + stream.getvalue())


class StartupDiagnosticsTests(unittest.TestCase):
    def test_missing_and_invalid_model_config_safe_diagnostics(self):
        from swe_eval.config import ConfigurationError, load_models
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            for content, field in [(None, "readable"), ("{malformed-secret-canary", "JSON"),
                                   (json.dumps([test_core.profile().model_dump() | {"max_agent_steps": "secret-canary"}]), "max_agent_steps")]:
                if content is not None:
                    path.write_text(content)
                with self.assertRaises(ConfigurationError) as error:
                    load_models(path)
                self.assertIn("SWE_MODELS_FILE", str(error.exception))
                self.assertIn(field, str(error.exception))
                self.assertNotIn("secret-canary", str(error.exception))

    def test_missing_short_and_placeholder_admin(self):
        for token in ("", "short-secret-canary", "replace-this-secret-canary"):
            with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
                "SWE_ADMIN_TOKEN": token, "SWE_DATA_DIR": root,
                "SWE_MODELS_FILE": str(Path(__file__).resolve().parents[1] / "config/models.json")}), contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(main(["serve"]), 2)
                self.assertIn("SWE_ADMIN_TOKEN", error.getvalue())
                self.assertIn("24", error.getvalue())
                if token:
                    self.assertNotIn(token, error.getvalue())


class DependencyContractTests(unittest.TestCase):
    def test_exact_exception_only(self):
        from swe_eval.dependency_check import EXCLUDED, validate_lean_check
        expected = "\n".join(f"mini-swe-agent 2.4.6 requires {name}, which is not installed." for name in EXCLUDED)
        validate_lean_check(1, expected)
        for code, text in ((0, expected), (1, expected + "\nmissing core dependency"),
                           (1, expected.replace("2.4.6", "2.4.7")), (1, "")):
            with self.assertRaises(RuntimeError):
                validate_lean_check(code, text)

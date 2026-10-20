"""Real execution tests. No benchmark repository code runs on the host.

Set SWE_DOCKER_TESTS=1 after building both images. Scripted inference responses
in one test exercise the actual installed mini agent, not a live-model score.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from swe_eval.agent import verify_mini_api
from swe_eval.benchmarks.local import LocalBenchmark
from swe_eval.config import Settings
from swe_eval.engine import EvaluationEngine
from swe_eval.providers import OpenAICompatibleProvider
from swe_eval.sandbox import DockerSandbox, run_process
from swe_eval.service import enqueue
from swe_eval.storage import SQLiteRepository
from test_core import profile, completion


@unittest.skipUnless(os.getenv("SWE_DOCKER_TESTS") == "1", "requires opt-in Docker daemon and prebuilt sandbox/grader images")
class DockerPipelineTests(unittest.TestCase):
    def setUp(self):
        result = run_process(["docker", "info", "--format={{.ServerVersion}}"], timeout=10)
        self.assertEqual(result.returncode, 0, "SWE_DOCKER_TESTS requires a working Docker daemon")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.repo = SQLiteRepository(root / "data" / "runs.sqlite3")
        self.repo.initialize()
        self.assertTrue(self.repo.acquire("test-worker", 300))
        self.benchmark = LocalBenchmark()
        self.profile = profile(api_key_env=None, allow_no_api_key=True)
        self.settings = Settings(root / "data", root / "unused.json")

    def engine(self, **kwargs):
        return EvaluationEngine(self.repo, self.benchmark, {self.profile.id: self.profile}, self.settings, **kwargs)

    def record(self, mode="patch_verification"):
        queued = enqueue(self.repo, self.benchmark, {self.profile.id: self.profile}, "intervals-001", self.profile.id, mode=mode)
        return self.repo.claim("test-worker", queued["id"])

    def test_known_valid_fix_and_unchanged_fail(self):
        task = self.benchmark.get_task("intervals-001")
        good = (self.benchmark.tasks[task.id][1] / "known_good.patch").read_text()
        for patch, expected in ((good, True), ("", False)):
            record = self.record()
            result = self.engine().execute(record["id"], supplied_patch=patch)
            self.assertEqual(result["state"], "completed", result)
            self.assertTrue(result["metrics"]["patch_applied"])
            self.assertEqual(result["metrics"]["resolved"], expected)
            self.assertEqual(result["metrics"]["test_result"], "passed" if expected else "failed")
            self.assertTrue(result["metrics"]["test_exit_codes"])
            self.assertEqual(result["metrics"]["model_requests"], 0)
            self.assertTrue(self.repo.logs(record["id"]))
            self.assertEqual(self.repo.patch(record["id"]), patch)

    def test_agent_cannot_read_hidden_tests(self):
        task = self.benchmark.get_task("intervals-001")
        sandbox = DockerSandbox("docker", self.repo.service_id, "isolationcheck", task)
        self.addCleanup(sandbox.close)
        sandbox.prepare(self.benchmark.source_archive(task), task)
        self.assertEqual(sandbox.command("test ! -e /opt/hidden && test $(id -u) = 10001 && test ! -e /var/run/docker.sock", 5).returncode, 0)
        self.assertNotEqual(sandbox.command("touch /etc/forbidden", 5).returncode, 0)

    def test_actual_mini_agent_inspects_modifies_and_grades(self):
        verify_mini_api()  # Fail explicitly if the installed API/version differs.
        commands = iter([
            "```bash\nls -la && cat intervals.py && python3 -m unittest -v test_public\n```",
            "```bash\npython3 - <<'PY'\nfrom pathlib import Path\np = Path('intervals.py')\np.write_text(p.read_text().replace('start < merged[-1][1]', 'start <= merged[-1][1]'))\nPY\npython3 -m unittest -v test_public\n```",
            "SUBMIT",
        ])
        requests = []
        def transport(url, key, body, timeout):
            requests.append(body)
            return completion(next(commands), {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20})
        def factory(profile, key, metrics, **kwargs):
            return OpenAICompatibleProvider(profile, key, metrics, **kwargs,
                                             transport=transport)
        record = self.record(mode="agent")
        result = self.engine(provider_factory=factory).execute(record["id"])
        self.assertEqual(result["state"], "completed", result)
        self.assertTrue(result["metrics"]["resolved"])
        self.assertEqual(result["metrics"]["model_requests"], 3)
        self.assertEqual(result["metrics"]["agent_steps"], 2)
        self.assertIn("Repository context", requests[0]["messages"][1]["content"])
        self.assertIn("intervals.py", requests[0]["messages"][1]["content"])
        self.assertIn("+        if merged and start <=", self.repo.patch(record["id"]))

    def test_disallowed_patch_is_not_tested(self):
        patch = "diff --git a/extra.py b/extra.py\nnew file mode 100644\n--- /dev/null\n+++ b/extra.py\n@@ -0,0 +1 @@\n+print('not allowed')\n"
        record = self.record()
        result = self.engine().execute(record["id"], supplied_patch=patch)
        self.assertFalse(result["metrics"]["patch_applied"])
        self.assertFalse(result["metrics"]["resolved"])
        self.assertEqual(result["metrics"]["test_result"], "not_run")

    def test_exit_zero_without_tests_is_not_a_pass(self):
        import difflib
        task = self.benchmark.get_task("intervals-001")
        original = (self.benchmark.source_path(task) / "intervals.py").read_text()
        patch = "".join(difflib.unified_diff(original.splitlines(keepends=True),
                        ["import os\n", "os._exit(0)\n"], fromfile="a/intervals.py", tofile="b/intervals.py"))
        record = self.record()
        result = self.engine().execute(record["id"], supplied_patch=patch)
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["metrics"]["resolved"])
        self.assertEqual(result["metrics"]["test_result"], "error")
        self.assertEqual(result["metrics"]["test_execution_errors"], 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from swe_eval.benchmarks.local import LocalBenchmark, snapshot_commit
from swe_eval.config import load_models, resolve_key
from swe_eval.providers import (ActionFormatError, BudgetExceeded, CompatibilityError,
                                OpenAICompatibleProvider, ProviderError, parse_action)
from swe_eval.sandbox import CommandResult, DockerSandbox, ExecutionTimeout, run_process
from swe_eval.schema import Metrics, ModelProfile, RunState
from swe_eval.security import Redactor
from swe_eval.service import enqueue, model_snapshot, public_run
from swe_eval.storage import Conflict, SQLiteRepository


def profile(**overrides):
    return ModelProfile.model_validate({"id": "test-profile", "upstream_id": "channel-a", "model_id": "same-model",
        "base_url": "https://example.invalid/v1", "api_key_env": "TEST_INFERENCE_KEY", **overrides})


def completion(content="SUBMIT", usage=None):
    return {"choices": [{"message": {"content": content}}], "usage": usage}


class ConfigurationTests(unittest.TestCase):
    def test_profiles_keep_same_model_separate(self):
        first = profile()
        second = profile(id="other-profile", upstream_id="channel-b", base_url="https://other.invalid/v1")
        self.assertEqual(first.model_id, second.model_id)
        self.assertNotEqual(model_snapshot(first), model_snapshot(second))
        self.assertNotIn("api_key_env", first.public())
        self.assertNotIn("base_url", first.public())

    def test_endpoint_change_changes_snapshot(self):
        self.assertNotEqual(model_snapshot(profile()), model_snapshot(profile(base_url="https://changed.invalid/v1")))

    def test_reject_unsupported_reasoning(self):
        with self.assertRaises(ValidationError):
            profile(reasoning_effort="high")

    def test_reasoning_capability(self):
        self.assertEqual(profile(reasoning_effort="high", capabilities={"reasoning_effort": True}).reasoning_effort, "high")

    def test_no_secrets_in_url(self):
        for url in ("https://key@example.invalid/v1", "https://a:b@example.invalid/v1", "https://example.invalid/?key=secret"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                profile(base_url=url)

    def test_http_requires_opt_in(self):
        with self.assertRaises(ValidationError):
            profile(base_url="http://localhost:8080/v1")
        self.assertTrue(profile(base_url="http://localhost:8080/v1", allow_http=True).allow_http)

    def test_no_unknown_configuration(self):
        with self.assertRaises(ValidationError):
            profile(api_key="do-not-store-keys-here")

    def test_missing_key_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            resolve_key(profile())

    def test_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            keyfile = Path(directory) / "key"
            keyfile.write_text("test-secret\n")
            self.assertEqual(resolve_key(profile(api_key_env=None, api_key_file=str(keyfile))), "test-secret")

    def test_duplicate_profile_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(json.dumps([profile().model_dump(), profile().model_dump()]))
            with self.assertRaises(ValueError):
                load_models(path)


class ProviderTests(unittest.TestCase):
    def provider(self, response, **overrides):
        self.calls = []
        self.metrics = Metrics()
        self.persisted = 0
        def persist():
            self.persisted += 1
        def transport(url, key, body, timeout):
            self.calls.append((url, key, body, timeout))
            if isinstance(response, Exception):
                raise response
            return response
        return OpenAICompatibleProvider(profile(**overrides), "test-secret", self.metrics,
                                         remaining=lambda: 12, persist=persist, transport=transport)

    def test_request_limits_and_default_compatibility(self):
        provider = self.provider(completion())
        provider.complete([{"role": "user", "content": "fix it", "extra": {"secret": "never-send"}}])
        url, key, body, timeout = self.calls[0]
        self.assertEqual(url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(timeout, 12)
        self.assertEqual(body["max_tokens"], 4096)
        self.assertNotIn("reasoning_effort", body)
        self.assertNotIn("tools", body)
        self.assertNotIn("extra", body["messages"][0])
        self.assertEqual(self.metrics.model_requests, 1)

    def test_usage_unknown_is_not_zero(self):
        provider = self.provider(completion())
        provider.complete([])
        self.assertIsNone(self.metrics.total_tokens)
        self.assertIsNone(self.metrics.cost)
        self.assertFalse(self.metrics.usage_complete)

    def test_usage_and_cost(self):
        provider = self.provider(completion(usage={"prompt_tokens": 100, "completion_tokens": 50,
            "total_tokens": 150, "completion_tokens_details": {"reasoning_tokens": 20}}),
            pricing={"input_per_million": 2, "output_per_million": 8})
        provider.complete([])
        provider.complete([])
        self.assertEqual(self.metrics.total_tokens, 300)
        self.assertEqual(self.metrics.reasoning_tokens, 40)
        self.assertAlmostEqual(self.metrics.cost, 0.0012)

    def test_unknown_reasoning_remains_unknown(self):
        provider = self.provider(completion(usage={"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}))
        provider.complete([])
        self.assertIsNone(self.metrics.reasoning_tokens)
        self.assertEqual(self.metrics.total_tokens, 8)

    def test_cost_becomes_unknown_if_later_usage_is_missing(self):
        provider = self.provider(completion(usage={"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}),
                                 pricing={"input_per_million": 2, "output_per_million": 8})
        provider.complete([])
        self.assertIsNotNone(self.metrics.cost)
        provider.transport = lambda *args: completion()
        provider.complete([])
        self.assertIsNone(self.metrics.cost)
        self.assertIsNone(self.metrics.total_tokens)

    def test_inflight_request_never_persists_incomplete_cost_as_complete(self):
        provider = self.provider(completion(usage={"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}),
                                 pricing={"input_per_million": 2, "output_per_million": 8})
        snapshots = []
        provider.persist = lambda: snapshots.append(self.metrics.model_dump())
        provider.complete([])
        provider.complete([])
        self.assertEqual(snapshots[2]["model_requests"], 2)
        self.assertIsNone(snapshots[2]["total_tokens"])
        self.assertIsNone(snapshots[2]["cost"])
        self.assertFalse(snapshots[2]["usage_complete"])
        self.assertEqual(snapshots[3]["total_tokens"], 16)

    def test_request_budget(self):
        provider = self.provider(completion(), max_model_calls=1)
        provider.complete([])
        with self.assertRaises(BudgetExceeded):
            provider.complete([])
        self.assertEqual(len(self.calls), 1)

    def test_unknown_usage_stops_total_budget(self):
        provider = self.provider(completion(), max_total_tokens=100)
        provider.complete([])
        with self.assertRaises(BudgetExceeded):
            provider.complete([])

    def test_total_budget_and_output_cap(self):
        provider = self.provider(completion(usage={"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10}),
                                 max_total_tokens=15)
        provider.complete([])
        provider.complete([])
        self.assertEqual(self.calls[1][2]["max_tokens"], 5)
        with self.assertRaises(BudgetExceeded):
            provider.complete([])

    def test_context_budget(self):
        provider = self.provider(completion(), max_context_chars=1000)
        with self.assertRaises(BudgetExceeded):
            provider.complete([{"role": "user", "content": "a" * 2000}])
        self.assertEqual(self.metrics.model_requests, 0)

    def test_no_retry_on_api_error(self):
        provider = self.provider(CompatibilityError("unsupported capability"))
        with self.assertRaises(CompatibilityError):
            provider.complete([])
        self.assertEqual(self.metrics.api_errors, 1)
        self.assertEqual(self.metrics.model_requests, 1)
        self.assertIsNone(self.metrics.total_tokens)

    def test_malformed_response_fails(self):
        provider = self.provider({"unexpected": True})
        with self.assertRaises(CompatibilityError):
            provider.complete([])

    def test_native_tools_and_reasoning(self):
        provider = self.provider(completion(), reasoning_effort="low", capabilities={"action_format": "native_tools",
                                  "reasoning_effort": True, "output_token_parameter": "max_completion_tokens"})
        provider.complete([])
        body = self.calls[0][2]
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertIn("max_completion_tokens", body)
        self.assertEqual(len(body["tools"]), 2)
        self.assertFalse(body["parallel_tool_calls"])

    def test_actions_require_execution_or_submit(self):
        self.assertEqual(parse_action({"content": "```bash\nls\n```"}, "text"), {"command": "ls"})
        self.assertEqual(parse_action({"content": "SUBMIT"}, "text"), {"submit": True})
        for content in ("I fixed it", "", "```bash\nls\n```\n```bash\npwd\n```", "SUBMIT because done"):
            with self.subTest(content=content), self.assertRaises(ActionFormatError):
                parse_action({"content": content}, "text")

    def test_native_action_validation(self):
        message = {"tool_calls": [{"id": "call_1", "function": {"name": "bash", "arguments": '{"command":"ls"}'}}]}
        self.assertEqual(parse_action(message, "native_tools")["command"], "ls")
        message["tool_calls"][0]["function"]["name"] = "host_exec"
        with self.assertRaises(ActionFormatError):
            parse_action(message, "native_tools")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "runs.sqlite3"
        self.repo = SQLiteRepository(self.path, Redactor(["exact-server-secret"]))
        self.repo.initialize()
        self.benchmark = LocalBenchmark()

    def create(self):
        return enqueue(self.repo, self.benchmark, {"test-profile": profile()}, "intervals-001", "test-profile")

    def test_completed_survives_restart(self):
        record = self.create()
        self.repo.acquire("worker", 30)
        self.repo.claim("worker")
        self.repo.transition(record["id"], RunState.EVALUATING)
        self.repo.save_metrics(record["id"], Metrics(resolved=False, test_result="failed"))
        self.repo.transition(record["id"], RunState.COMPLETED)
        reopened = SQLiteRepository(self.path)
        reopened.initialize()
        self.assertEqual(reopened.get(record["id"])["state"], "completed")
        self.assertFalse(reopened.get(record["id"])["metrics"]["resolved"])

    def test_invalid_transition(self):
        record = self.create()
        with self.assertRaises(Conflict):
            self.repo.transition(record["id"], RunState.COMPLETED)

    def test_atomic_single_claim(self):
        self.create()
        self.create()
        self.repo.acquire("worker", 30)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.repo.claim("worker"), range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_multiple_workers_cannot_acquire(self):
        self.assertTrue(self.repo.acquire("first", 30))
        self.assertFalse(self.repo.acquire("second", 30))
        with self.assertRaises(Conflict):
            self.repo.claim("second")

    def test_expired_worker_cannot_resurrect_lease(self):
        self.repo.acquire("expired", 30)
        with self.repo.connect(write=True) as db:
            db.execute("UPDATE worker_lock SET expires_at=0")
        self.assertFalse(self.repo.heartbeat("expired", 30))
        with self.assertRaises(Conflict):
            self.repo.claim("expired")

    def test_structured_redaction_handles_escaped_secrets(self):
        secret = 'credential-with-"quote'
        self.repo.redact = Redactor([secret])
        run_id = self.create()["id"]
        self.repo.save_metrics(run_id, Metrics(execution_metadata={"response": secret}))
        result = self.repo.get(run_id)
        self.assertEqual(result["metrics"]["execution_metadata"]["response"], "[REDACTED]")

    def test_recovery_does_not_repeat_paid_evaluation(self):
        record = self.create()
        self.repo.acquire("old", 30)
        self.repo.claim("old")
        with self.repo.connect(write=True) as db:
            db.execute("UPDATE worker_lock SET expires_at=0")
        self.assertTrue(self.repo.acquire("new", 30))
        self.assertEqual(self.repo.recover("new"), [record["id"]])
        self.assertEqual(self.repo.get(record["id"])["error"], "worker_interrupted")
        self.assertIsNone(self.repo.claim("new"))

    def test_cancel_queued_and_active(self):
        queued = self.create()
        self.assertEqual(self.repo.cancel(queued["id"])["state"], "cancelled")
        active = self.create()
        self.repo.acquire("worker", 30)
        self.repo.claim("worker")
        result = self.repo.cancel(active["id"])
        self.assertEqual(result["state"], "preparing")
        self.assertTrue(result["cancel_requested"])

    def test_logs_and_patch_are_retrievable_and_redacted(self):
        run_id = self.create()["id"]
        self.repo.log(run_id, "test", "Bearer exact-server-secret and exact-server-secret")
        logs = self.repo.logs(run_id)
        self.assertNotIn("exact-server-secret", logs[-1]["message"])
        self.assertEqual(self.repo.logs(run_id, logs[-1]["seq"]), [])
        self.repo.save_patch(run_id, "diff --git a/a b/a\n")
        self.assertEqual(self.repo.patch(run_id), "diff --git a/a b/a\n")
        with self.assertRaises(ValueError):
            self.repo.save_patch(run_id, "exact-server-secret")
        self.assertNotIn("exact-server-secret", self.path.read_bytes().decode(errors="ignore"))

    def test_public_run_hides_test_commands(self):
        result = public_run(self.create())
        self.assertNotIn("test_commands", result["task"])
        self.assertNotIn("success_marker", result["task"])
        self.assertNotIn("api_key_env", result["model"])

    def test_parent_for_explicit_retry(self):
        first = self.create()
        second = enqueue(self.repo, self.benchmark, {"test-profile": profile()}, "intervals-001", "test-profile",
                         parent_id=first["id"])
        self.assertEqual(second["parent_id"], first["id"])


class BenchmarkTests(unittest.TestCase):
    def test_snapshot_commit_and_known_patch_with_real_git(self):
        # Git manipulates trusted source bytes; benchmark Python is never executed here.
        import shutil
        benchmark = LocalBenchmark()
        task = benchmark.get_task("intervals-001")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(benchmark.source_path(task), root / "repository")
            env = {"PATH": os.environ["PATH"], "HOME": directory,
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_AUTHOR_DATE": "1704067200 +0000", "GIT_COMMITTER_DATE": "1704067200 +0000"}
            def git(*args, stdin=None):
                result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=root / "repository",
                                        env=env, input=stdin, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                return result.stdout
            git("init", "-b", "main")
            git("add", "--all")
            git("-c", "user.name=SWE Eval", "-c", "user.email=fixture@swe-eval.invalid",
                "-c", "commit.gpgsign=false", "commit", "-m", "Trusted benchmark baseline")
            self.assertEqual(git("rev-parse", "HEAD").decode().strip(), task.base_commit)
            fix = (benchmark.tasks[task.id][1] / "known_good.patch").read_bytes()
            git("apply", "--check", "--index", "-", stdin=fix)
            git("apply", "--index", "-", stdin=fix)
            self.assertIn(b"+        if merged and start <=", git("diff", task.base_commit))

    def test_discovery_and_pinned_commit(self):
        benchmark = LocalBenchmark()
        task = benchmark.get_task("intervals-001")
        self.assertEqual(task.base_commit, snapshot_commit(benchmark.source_path(task)))
        self.assertEqual(task.dataset_version, "1.0.0")
        self.assertTrue(task.issue)

    def test_agent_archive_contains_no_hidden_tests_or_fix(self):
        benchmark = LocalBenchmark()
        task = benchmark.get_task("intervals-001")
        with tarfile.open(fileobj=io.BytesIO(benchmark.source_archive(task))) as archive:
            self.assertEqual(set(archive.getnames()), {"intervals.py", "test_public.py", "README.md"})
        self.assertNotIn("test_commands", task.public())

    def test_snapshot_tampering_and_symlinks_are_rejected(self):
        benchmark = LocalBenchmark()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a").write_text("one")
            initial = snapshot_commit(root)
            (root / "a").write_text("two")
            self.assertNotEqual(initial, snapshot_commit(root))
            (root / "link").symlink_to(root / "a")
            with self.assertRaises(ValueError):
                snapshot_commit(root)

    def test_empty_directories_do_not_change_git_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.py").write_text("# trusted bytes, never executed\n")
            initial = snapshot_commit(root)
            (root / "empty").mkdir()
            self.assertEqual(initial, snapshot_commit(root))


class SandboxTests(unittest.TestCase):
    def test_creation_security_flags(self):
        calls = []
        def record(args, **kwargs):
            calls.append(args)
            return CommandResult(0, "sha256:fixture\n")
        task = LocalBenchmark().get_task("intervals-001")
        with patch("swe_eval.sandbox.run_process", side_effect=record):
            sandbox = DockerSandbox("docker", "a" * 32, "b" * 32, task)
            sandbox.close()
        create = calls[0]
        for flag in ("--network=none", "--read-only", "--user=10001:10001", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges:true", "--memory=512m", "--pids-limit=64", "--pull=never"):
            self.assertIn(flag, create)
        self.assertNotIn("--privileged", create)
        self.assertFalse(any("docker.sock" in item or item in {"-v", "--volume", "--mount"} for item in create))

    def test_cli_output_bound(self):
        result = run_process([sys.executable, "-c", "print('a' * 100000)"], timeout=5, max_output=100)
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.output), 100)

    def test_cli_absolute_deadline(self):
        start = time.monotonic()
        with self.assertRaises(ExecutionTimeout):
            run_process([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.2)
        self.assertLess(time.monotonic() - start, 3)


if __name__ == "__main__":
    unittest.main()

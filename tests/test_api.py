from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HAS_API = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None


@unittest.skipUnless(HAS_API, "install requirements-core.lock and requirements-test.lock for API tests")
class APITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from swe_eval.api import create_app
        from swe_eval.config import Settings

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        models = root / "models.json"
        models.write_text(json.dumps([{"id": "primary", "upstream_id": "channel-a", "model_id": "6.1-sol",
            "base_url": "https://example.invalid/v1", "api_key_env": "TEST_INFERENCE_KEY"}]))
        self.settings = Settings(root / "data", models, "test-admin-token-with-32-characters")
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": f"Bearer {self.settings.admin_token}"}

    def test_health_and_authentication(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        for url in ("/api/v1/tasks", "/api/v1/models", "/api/v1/runs", "/api/v1/runs/unknown/logs"):
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/runs", json={"task_id": "intervals-001", "model_profile_id": "primary"}).status_code, 401)

    def test_discovery(self):
        self.assertEqual(self.client.get("/api/v1/tasks", headers=self.headers).json()["items"][0]["id"], "intervals-001")
        model = self.client.get("/api/v1/models", headers=self.headers).json()["items"][0]
        self.assertEqual(model["model_id"], "6.1-sol")
        self.assertNotIn("api_key_env", model)

    def test_run_durability_artifacts_and_cancel(self):
        response = self.client.post("/api/v1/runs", headers=self.headers,
                                    json={"task_id": "intervals-001", "model_profile_id": "primary"})
        self.assertEqual(response.status_code, 202)
        run_id = response.json()["id"]
        self.assertEqual(response.json()["state"], "queued")
        self.assertIsNone(response.json()["metrics"]["resolved"])
        self.assertTrue(self.client.get(f"/api/v1/runs/{run_id}/logs", headers=self.headers).json()["items"])
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}/patch", headers=self.headers).text, "")
        self.assertEqual(len(self.client.get("/api/v1/runs", headers=self.headers).json()["items"]), 1)
        self.assertEqual(self.client.post(f"/api/v1/runs/{run_id}/cancel", headers=self.headers).json()["state"], "cancelled")
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}", headers=self.headers).json()["state"], "cancelled")

    def test_unknown_tasks_and_runs(self):
        self.assertEqual(self.client.post("/api/v1/runs", headers=self.headers,
            json={"task_id": "untrusted-url", "model_profile_id": "primary"}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/runs/unknown", headers=self.headers).status_code, 404)

    def test_limits_and_no_arbitrary_execution_inputs(self):
        self.assertEqual(self.client.get("/api/v1/runs?limit=10000", headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/runs", headers=self.headers,
            json={"task_id": "intervals-001", "model_profile_id": "primary", "command": "host command"}).status_code, 422)

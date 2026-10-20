"""Checks actual installed mini APIs without requiring Docker or inference."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest

from swe_eval.agent import MiniModel, verify_mini_api
from swe_eval.providers import OpenAICompatibleProvider
from swe_eval.schema import Metrics, ModelProfile


@unittest.skipUnless(importlib.util.find_spec("minisweagent") is not None, "mini-SWE-agent is not installed")
class MiniContractTests(unittest.TestCase):
    def test_installed_default_agent_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = directory
            agent_class, format_error, limits_exceeded, version = verify_mini_api()
            profile = ModelProfile(id="contract", upstream_id="none", model_id="none",
                                   base_url="https://unused.invalid/v1", allow_no_api_key=True)
            metrics = Metrics()
            provider = OpenAICompatibleProvider(profile, "", metrics, remaining=lambda: 10, persist=lambda: None,
                transport=lambda *args: {"choices": [{"message": {"content": "SUBMIT"}}]})
            model = MiniModel(provider, profile, format_error, limits_exceeded)

            class SubmitOnlyEnvironment:
                def execute(self, action, cwd=""):
                    self.assert_submit(action)
                    return {"submitted": True}

                @staticmethod
                def assert_submit(action):
                    if action != {"submit": True}:
                        raise AssertionError("unexpected command in protocol-only contract test")

                def get_template_vars(self):
                    return {}

                def serialize(self):
                    return {}

            agent = agent_class(model, SubmitOnlyEnvironment(), system_template="Test protocol only",
                                instance_template="{{ task }}", step_limit=2, cost_limit=0,
                                wall_time_limit_seconds=10, output_path=None)
            self.assertEqual(agent.run(task="submit")["exit_status"], "Submitted")
            self.assertEqual(metrics.model_requests, 1)
            self.assertEqual(version, "2.4.6")

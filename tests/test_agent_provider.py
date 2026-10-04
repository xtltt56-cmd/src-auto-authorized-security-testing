import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src_auto.agent_provider import AgentModel, configured_model


class AgentProviderTests(unittest.TestCase):
    def context(self):
        return {"references": ["entry"], "capabilities": ["inspect_headers", "finish"], "observations": []}

    def test_local_structured_output_and_actual_usage(self):
        calls = []
        def request(path, payload):
            calls.append((path, payload))
            return {"response": "{}", "prompt_eval_count": 12, "eval_count": 4}
        result = AgentModel(SimpleNamespace(model="test-model", _request=request)).decide(self.context())
        self.assertEqual(calls[0][0], "/api/generate")
        self.assertFalse(calls[0][1]["think"])
        self.assertEqual(calls[0][1]["format"]["properties"]["action"]["enum"], ["inspect_headers", "finish"])
        self.assertEqual(result["input_tokens"] + result["output_tokens"], 16)
        self.assertFalse(result["usage_estimated"])

    def test_missing_usage_is_conservative_not_zero(self):
        model = AgentModel(SimpleNamespace(model="test-model", _request=lambda *args: {"response": "{}"}))
        result = model.decide(self.context())
        self.assertTrue(result["usage_estimated"])
        self.assertGreater(result["input_tokens"], 0)

    def test_cloud_gate_precedes_config_and_credentials(self):
        with patch("src_auto.agent_provider.load_mapping", side_effect=AssertionError("must not load")):
            with self.assertRaisesRegex(ValueError, "remote_ai_disabled_for_session"):
                configured_model(Path("."), "deepseek", False, True)

    def test_local_endpoint_and_timeout_are_bounded(self):
        config = {"lanes": {"primary": {"endpoint": "http://127.0.0.1:11434", "model": "test-model", "timeout_seconds": 999}}}
        with patch("src_auto.agent_provider.load_mapping", return_value=config):
            self.assertEqual(configured_model(Path("."), "local").provider.timeout_seconds, 120)
            config["lanes"]["primary"]["endpoint"] = "https://example.org"
            with self.assertRaisesRegex(ValueError, "local_model_endpoint_not_allowed"):
                configured_model(Path("."), "local")

    def test_remote_payload_does_not_allow_provider_fallback(self):
        payloads = []
        def post(payload):
            payloads.append(payload)
            return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
        provider = SimpleNamespace(model="test-model", provider_name="openrouter", _post=post)
        self.assertFalse(AgentModel(provider, local=False).decide(self.context())["usage_estimated"])
        self.assertFalse(payloads[0]["provider"]["allow_fallbacks"])
        self.assertEqual(payloads[0]["provider"]["data_collection"], "deny")
        self.assertEqual(json.loads(payloads[0]["messages"][1]["content"])["references"], ["entry"])


if __name__ == "__main__": unittest.main()

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src_auto.agent_provider import AgentModel, configured_model


class AgentProviderTests(unittest.TestCase):
    def test_full_business_feedback_fits_limit_without_hashes_or_private_fields(self):
        payloads = []
        def post(value):
            payloads.append(value)
            return {'choices': [{'message': {'content': '{}'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}
        rows = [dict(id='o'+str(i), action='compare_business_object', reference='object-00'+str(i), validated=True,
                     fingerprints={role: 'a'*64 for role in ('account-a', 'account-b', 'administrator', 'anonymous')},
                     statuses={'account-a': 200}, baselineValid=True, unexpectedRoles=['account-b'], candidate=True,
                     private_debug='DO_NOT_SEND_PRIVATE_'*500) for i in range(1,7)]
        model = AgentModel(SimpleNamespace(model='deepseek-flash', provider_name='deepseek', _post=post), local=False)
        model.decide(dict(mode='business-assessment', references=['entry']+['object-00'+str(i) for i in range(1,7)],
                          capabilities=['finish'], observations=rows, permissions={'allObjectReferencesRequired': True}))
        text = payloads[0]['messages'][1]['content']
        self.assertNotIn('DO_NOT_SEND_PRIVATE', text)
        self.assertNotIn('fingerprints', text)
        self.assertIn('unexpectedRoles', text)
        self.assertIn('o6', text)

    def test_six_local_route_feedbacks_fit_bounded_model_context(self):
        provider = SimpleNamespace(model='deepseek-flash', provider_name='deepseek', _post=lambda payload: {
            'choices': [{'message': {'content': '{}'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2}})
        observations = [dict(id='o{}'.format(i), action='inspect_local_route', reference='route-{:03d}'.format(i),
            path='/api/route{}'.format(i), method='GET', status_code=200, response_bytes_read=100,
            header_presence={key: False for key in ('content-security-policy', 'x-content-type-options', 'x-frame-options', 'referrer-policy', 'permissions-policy', 'strict-transport-security')},
            summary='批准路由已真实检查；仅保存响应元数据', candidate=False, confirmed=False,
            category='readonly-observation', raw_body_retained=False, header_values_retained=False,
            body_truncated=False, redirects=0, status='ok', candidateCount=0, request_id='request-001') for i in range(1, 7)]
        context = dict(mode='local-web-assessment', lab='owned-web', capabilities=['finish', 'request_human_review'],
                       references=['entry'] + ['route-{:03d}'.format(i) for i in range(1, 7)],
                       permissions={'routeReferences': ['route-{:03d}'.format(i) for i in range(1, 7)], 'requiredRouteCount': 6},
                       observations=observations)
        for passive in (False, True):
            if passive:
                context['permissions'].update(passiveRequired=True)
                for row in observations:
                    row['discovery'] = dict(approved_paths=['/api/route2'], blocked_counts={'path_excluded': 1}, link_limit_reached=False)
                observations.append(dict(id='o7', action='analyze_passive_capture', reference='entry', status='ok', advisoryCount=1,
                    coverage=dict(messages=6, raw_body_retained=False, body_rules_enabled=False, discovered_approved_paths=['/api/route2'], blocked_link_count=6)))
            result = AgentModel(provider, local=False).decide(context)
            self.assertFalse(result['usage_estimated'])

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

    def test_deepseek_agent_disables_thinking_and_uses_json_decisions(self):
        payloads = []
        def post(payload):
            payloads.append(payload)
            return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        model = AgentModel(SimpleNamespace(model="deepseek-flash", provider_name="deepseek", _post=post), local=False)
        model.decide(self.context())
        self.assertEqual(payloads[0]["thinking"], {"type": "disabled"})
        self.assertEqual(payloads[0]["temperature"], 0)
        self.assertEqual(payloads[0]["response_format"], {"type": "json_object"})


if __name__ == "__main__": unittest.main()

import json
import os
import unittest
from unittest.mock import patch

from src_auto.remote_ai import (
    DeepSeekProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ZhipuProvider,
    RemoteProviderError,
    RemoteReviewRequest,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class RemoteAITests(unittest.TestCase):
    def test_saved_key_loader_runs_only_after_consent_and_runtime_gates(self):
        from unittest.mock import Mock
        loader = Mock(return_value='synthetic-key')
        provider = DeepSeekProvider(endpoint='https://api.deepseek.com/chat/completions',
                                    model='deepseek-flash', key_env='UNIT_KEY_NOT_SET',
                                    key_loader=loader, allow_remote_llm=True)
        with patch.dict(os.environ, {'SRC_AUTO_DEEPSEEK_CONSENT': 'disabled'}):
            with self.assertRaises(RemoteProviderError): provider._key()
        loader.assert_not_called()
        with patch.dict(os.environ, {'SRC_AUTO_DEEPSEEK_CONSENT': 'enabled'}):
            self.assertEqual(provider._key(), 'synthetic-key')
        loader.assert_called_once()

    def setUp(self):
        self._consent = patch.dict(
            os.environ,
            {
                "SRC_AUTO_REMOTE_AI_CONSENT": "enabled",
                "SRC_AUTO_DEEPSEEK_CONSENT": "enabled",
            },
            clear=False,
        )
        self._consent.start()
        self.addCleanup(self._consent.stop)
        self.finding = {
            "title": "Possible token leak",
            "url": "https://user:password@example.test/path?token=secret#fragment",
            "parameter": "redirect",
            "severity": "medium",
            "evidence": "Authorization: Bearer x-token; Authorization: Basic basic-secret; cookie=session=secret; token=secret",
        }

    def test_deepseek_denied_without_startup_consent_before_network(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request)
            return FakeResponse({})

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "unit-test-secret", "SRC_AUTO_DEEPSEEK_CONSENT": "disabled"},
            clear=False,
        ):
            with self.assertRaises(RemoteProviderError) as blocked:
                DeepSeekProvider(
                    endpoint="https://api.deepseek.com/chat/completions",
                    model="deepseek-v4-flash",
                    key_env="DEEPSEEK_API_KEY",
                    allow_remote_llm=True,
                    urlopen_fn=fake_urlopen,
                ).review(self.finding)
        self.assertEqual(str(blocked.exception), "remote_ai_disabled_for_session")
        self.assertEqual(calls, [])

    def test_remote_request_redacts_credentials_queries_and_secrets(self):
        request = RemoteReviewRequest.from_finding(self.finding)
        encoded = json.dumps(request.payload, ensure_ascii=False).lower()
        self.assertEqual(request.payload["url"], "https://example.test/path")
        self.assertNotIn("password", encoded)
        self.assertNotIn("x-token", encoded)
        self.assertNotIn("basic-secret", encoded)
        self.assertNotIn("session=secret", encoded)
        self.assertEqual(len(request.digest), 64)
        self.assertEqual(request.digest, RemoteReviewRequest.from_finding(self.finding).digest)

    def test_deepseek_request_uses_manual_json_review_contract(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "disposition": "candidate",
                                        "confidence": 0.8,
                                        "reason": "Evidence needs manual verification.",
                                        "suggested_checks": ["repeat a read-only request"],
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                }
            )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-secret"}, clear=False):
            result = DeepSeekProvider(
                endpoint="https://api.deepseek.com/chat/completions",
                model="deepseek-v4-flash",
                key_env="DEEPSEEK_API_KEY",
                timeout_seconds=7,
                max_input_tokens=2000,
                max_output_tokens=256,
                allow_remote_llm=True,
                urlopen_fn=fake_urlopen,
            ).review(self.finding)
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], "deepseek-v4-flash")
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(result["output_tokens"], 20)
        request, timeout = calls[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertFalse(payload["stream"])
        self.assertEqual(timeout, 7)

    def test_openai_responses_request_disables_storage_and_tools(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request)
            return FakeResponse(
                {
                    "output_text": json.dumps(
                        {
                            "disposition": "manual_review",
                            "confidence": 0.5,
                            "reason": "Human confirmation is required.",
                            "suggested_checks": [],
                        }
                    ),
                    "usage": {"input_tokens": 12, "output_tokens": 8},
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-openai-secret"}, clear=False):
            result = OpenAIProvider(
                endpoint="https://api.openai.com/v1/responses",
                model="gpt-5.6-luna",
                key_env="OPENAI_API_KEY",
                timeout_seconds=9,
                max_input_tokens=2000,
                max_output_tokens=256,
                allow_remote_llm=True,
                urlopen_fn=fake_urlopen,
            ).review(self.finding)
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["model"], "gpt-5.6-luna")
        request = calls[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tools"], [])
        self.assertEqual(payload["max_output_tokens"], 256)
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")

    def test_zhipu_uses_openai_compatible_manual_json_contract(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen['url'] = request.full_url
            seen['payload'] = json.loads(request.data.decode('utf-8'))
            seen['authorization'] = request.headers.get('Authorization')
            return FakeResponse({
                'choices': [{'message': {'content': json.dumps({
                    'disposition': 'manual_review',
                    'confidence': 0.61,
                    'reason': 'needs operator verification',
                    'suggested_checks': ['compare authorized objects'],
                })}}],
                'usage': {'prompt_tokens': 40, 'completion_tokens': 12},
            })

        with patch.dict(os.environ, {
            'ZHIPU_API_KEY': 'unit-test-zhipu-secret',
            'SRC_AUTO_ZHIPU_CONSENT': 'enabled',
        }, clear=False):
            result = ZhipuProvider(
                endpoint='https://open.bigmodel.cn/api/paas/v4/chat/completions',
                model='glm-5.3-flash',
                key_env='ZHIPU_API_KEY',
                consent_env='SRC_AUTO_ZHIPU_CONSENT',
                allow_remote_llm=True,
                urlopen_fn=fake_urlopen,
            ).review(self.finding)

        self.assertEqual(seen['url'], 'https://open.bigmodel.cn/api/paas/v4/chat/completions')
        self.assertEqual(seen['payload']['model'], 'glm-5.3-flash')
        self.assertEqual(seen['payload']['response_format'], {'type': 'json_object'})
        self.assertEqual(seen['payload']['thinking'], {'type': 'enabled'})
        self.assertEqual(seen['authorization'], 'Bearer unit-test-zhipu-secret')
        self.assertEqual(result['provider'], 'zhipu')

    def test_openrouter_ox_alpha_uses_private_manual_json_contract(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "disposition": "manual_review",
                                        "confidence": 0.6,
                                        "reason": "Human verification is required.",
                                        "suggested_checks": ["repeat one read-only request"],
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 18, "completion_tokens": 9},
                }
            )

        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "unit-test-openrouter-secret",
                "SRC_AUTO_OPENROUTER_CONSENT": "enabled",
            },
            clear=False,
        ):
            result = OpenRouterProvider(
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                model="stealth/ox-alpha",
                key_env="OPENROUTER_API_KEY",
                consent_env="SRC_AUTO_OPENROUTER_CONSENT",
                timeout_seconds=11,
                max_input_tokens=2000,
                max_output_tokens=256,
                allow_remote_llm=True,
                urlopen_fn=fake_urlopen,
            ).review(self.finding)
        self.assertEqual(result["provider"], "openrouter")
        self.assertEqual(result["model"], "stealth/ox-alpha")
        request, timeout = calls[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(payload["model"], "stealth/ox-alpha")
        self.assertEqual(payload["provider"]["data_collection"], "deny")
        self.assertEqual(payload["reasoning"]["effort"], "low")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertFalse(payload["stream"])
        self.assertEqual(timeout, 11)

    def test_openrouter_unknown_disposition_fails_safe_to_manual_review(self):
        def fake_urlopen(request, timeout):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "disposition": "not_applicable",
                                        "confidence": 0.2,
                                        "reason": "Synthetic connectivity input is not a finding.",
                                        "suggested_checks": [],
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 6},
                }
            )

        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "unit-test-openrouter-secret",
                "SRC_AUTO_OPENROUTER_CONSENT": "enabled",
            },
            clear=False,
        ):
            result = OpenRouterProvider(
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                model="stealth/ox-alpha",
                key_env="OPENROUTER_API_KEY",
                consent_env="SRC_AUTO_OPENROUTER_CONSENT",
                allow_remote_llm=True,
                urlopen_fn=fake_urlopen,
            ).review(self.finding)
        self.assertEqual(result["disposition"], "manual_review")

    def test_missing_key_and_invalid_output_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RemoteProviderError):
                DeepSeekProvider(
                    endpoint="https://api.deepseek.com/chat/completions",
                    model="deepseek-v4-flash",
                    key_env="DEEPSEEK_API_KEY",
                    allow_remote_llm=True,
                ).review(self.finding)

        def invalid_urlopen(request, timeout):
            return FakeResponse({"choices": [{"message": {"content": "not-json"}}]})

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-secret"}, clear=False):
            with self.assertRaises(RemoteProviderError):
                DeepSeekProvider(
                    endpoint="https://api.deepseek.com/chat/completions",
                    model="deepseek-v4-flash",
                    key_env="DEEPSEEK_API_KEY",
                    allow_remote_llm=True,
                    urlopen_fn=invalid_urlopen,
                ).review(self.finding)

    def test_disabled_provider_and_input_limit_never_contact_network(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request)
            return FakeResponse({})

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only-key"}, clear=False):
            with self.assertRaises(RemoteProviderError) as disabled:
                DeepSeekProvider(
                    endpoint="https://api.deepseek.com/chat/completions",
                    model="deepseek-v4-flash",
                    key_env="DEEPSEEK_API_KEY",
                    enabled=False,
                    allow_remote_llm=True,
                    urlopen_fn=fake_urlopen,
                ).review(self.finding)
            with self.assertRaises(RemoteProviderError) as limited:
                DeepSeekProvider(
                    endpoint="https://api.deepseek.com/chat/completions",
                    model="deepseek-v4-flash",
                    key_env="DEEPSEEK_API_KEY",
                    max_input_tokens=1,
                    allow_remote_llm=True,
                    urlopen_fn=fake_urlopen,
                ).review(self.finding)
        self.assertEqual(str(disabled.exception), "provider_disabled")
        self.assertEqual(str(limited.exception), "remote_input_token_limit_exceeded")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

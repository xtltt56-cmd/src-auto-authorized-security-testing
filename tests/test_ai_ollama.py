import json
import unittest
from urllib.error import URLError

from src_auto.ai import AITriage, ModelRouter, OllamaProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class OllamaTests(unittest.TestCase):
    def test_provider_health_and_triage_use_json_and_minimal_fields(self):
        calls = []

        def fake_urlopen(request, timeout=0):
            calls.append((request.full_url, json.loads(request.data.decode("utf-8")) if request.data else None))
            if request.full_url.endswith("/api/tags"):
                return FakeResponse({"models": [{"name": "codex-balanced:20b"}]})
            return FakeResponse({"response": '{"disposition":"candidate","confidence":0.91,"reason":"model_observation"}'})

        provider = OllamaProvider("http://127.0.0.1:11434", "codex-balanced:20b", urlopen_fn=fake_urlopen)
        self.assertTrue(provider.health())
        result = provider.triage(
            {
                "title": "Header issue",
                "url": "https://example.com/path?token=secret",
                "parameter": "q",
                "severity": "low",
                "evidence": "token=secret; X-Test absent",
            }
        )
        self.assertEqual(result["disposition"], "candidate")
        self.assertAlmostEqual(result["confidence"], 0.91)
        generate_payload = calls[1][1]
        prompt = json.dumps(generate_payload, ensure_ascii=False)
        self.assertNotIn("secret", prompt)
        self.assertIn("Header issue", prompt)

    def test_ai_triage_falls_back_when_ollama_is_unavailable(self):
        def failing_urlopen(request, timeout=0):
            raise URLError("ollama offline")

        router = ModelRouter(
            {
                "default_lane": "primary",
                "lanes": {
                    "primary": {
                        "provider": "ollama",
                        "model": "codex-balanced:20b",
                        "endpoint": "http://127.0.0.1:11434",
                    }
                },
            },
            urlopen_fn=failing_urlopen,
        )
        result = AITriage(router).classify({"severity": "low", "evidence": "observation"})
        self.assertEqual(result["disposition"], "candidate")
        self.assertEqual(result["reason"], "ollama_fallback")


if __name__ == "__main__":
    unittest.main()

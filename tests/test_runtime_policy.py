import unittest

from src_auto.ai import ModelRouter
from src_auto.runtime_policy import RuntimePolicy


class RuntimePolicyTests(unittest.TestCase):
    def test_exact_local_allowlist_and_concurrency(self):
        policy = RuntimePolicy.from_mapping(
            {
                "AI_PROVIDER": "local",
                "LOCAL_LLM_ONLY": True,
                "ALLOW_REMOTE_LLM": False,
                "allowed_hosts": ["localhost", "127.0.0.1"],
                "allowed_ports": [3000],
                "max_concurrency": 5,
            }
        )
        self.assertTrue(policy.local_llm_only)
        self.assertFalse(policy.allow_remote_llm)
        self.assertEqual(policy.max_concurrency, 5)
        self.assertTrue(policy.decide_url("http://127.0.0.1:3000")[0])
        self.assertTrue(policy.decide_url("http://localhost:3000/api/Users")[0])

    def test_allowlist_rejects_external_subdomain_and_port(self):
        policy = RuntimePolicy.from_mapping(
            {
                "AI_PROVIDER": "local",
                "LOCAL_LLM_ONLY": True,
                "ALLOW_REMOTE_LLM": False,
                "allowed_hosts": ["localhost", "127.0.0.1"],
                "allowed_ports": [3000],
            }
        )
        for url in (
            "http://shop.localhost:3000/",
            "http://127.0.0.1:3001/",
            "https://example.com/",
            "http://user:pass@localhost:3000/",
            "file:///etc/passwd",
            "http://127.0.0.1:3000/\nX-Bad: value",
        ):
            self.assertFalse(policy.decide_url(url)[0], url)

    def test_remote_llm_configuration_is_internally_consistent(self):
        with self.assertRaises(ValueError):
            RuntimePolicy.from_mapping(
                {"AI_PROVIDER": "local", "LOCAL_LLM_ONLY": True, "ALLOW_REMOTE_LLM": True}
            )
        with self.assertRaises(ValueError):
            RuntimePolicy.from_mapping(
                {"AI_PROVIDER": "remote", "LOCAL_LLM_ONLY": True, "ALLOW_REMOTE_LLM": False}
            )

    def test_model_router_blocks_nonlocal_route_when_policy_is_local_only(self):
        router = ModelRouter(
            {
                "runtime_policy": {
                    "AI_PROVIDER": "local",
                    "LOCAL_LLM_ONLY": True,
                    "ALLOW_REMOTE_LLM": False,
                },
                "lanes": {"primary": {"provider": "remote", "model": "remote-test", "estimated_cost": 1}},
            }
        )
        route = router.route("triage")
        self.assertEqual(route.provider, "remote")
        self.assertIsNone(router.provider_for(route))


if __name__ == "__main__":
    unittest.main()

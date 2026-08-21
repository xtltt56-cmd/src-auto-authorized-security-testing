import tempfile
import unittest
from pathlib import Path

from src_auto.scope import ScopePolicy
from src_auto.scope_resolver import ScopeResolver


class ResolverTests(unittest.TestCase):
    def test_resolver_only_normalizes_explicit_rules_and_never_confirms(self):
        snapshot = {
            "target_id": "acme",
            "vendor": "acme",
            "source_url": "https://example.invalid/rules",
            "root_domains": ["Example.COM"],
            "allowed_hosts": ["www.example.com"],
            "excluded_hosts": ["login.example.com"],
            "allowed_ports": [443],
        }
        candidate = ScopeResolver().resolve(snapshot)
        self.assertFalse(candidate["confirmed"])
        self.assertFalse(candidate["allow_network_contact"])
        self.assertEqual(ScopePolicy.from_mapping(candidate).root_domains, ["example.com"])

    def test_resolver_writes_candidate_inside_requested_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = ScopeResolver().write_candidate(Path(temp), {"target_id": "x", "root_domains": ["x.test"]})
            self.assertTrue(path.exists())
            self.assertIn("scope_candidate", path.name)


if __name__ == "__main__":
    unittest.main()

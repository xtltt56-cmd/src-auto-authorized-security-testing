import unittest

from src_auto.scope import ScopeGuard, ScopePolicy


def policy(confirmed=True):
    return ScopePolicy.from_mapping(
        {
            "target_id": "local-lab",
            "root_domains": ["localhost"],
            "allowed_hosts": ["localhost", "127.0.0.1"],
            "excluded_hosts": ["admin.localhost"],
            "allowed_ports": [80, 8000, 8765],
            "confirmed": confirmed,
            "allow_network_contact": confirmed,
        }
    )


class ScopeGuardTests(unittest.TestCase):
    def test_exact_and_subdomain_are_allowed_after_confirmation(self):
        guard = ScopeGuard(policy())
        self.assertTrue(guard.decide("http://localhost/").allowed)
        self.assertTrue(guard.decide("http://api.localhost:8765/v1").allowed)

    def test_unconfirmed_scope_fails_closed(self):
        decision = ScopeGuard(policy(False)).decide("http://localhost/")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "scope_not_confirmed")

    def test_third_party_and_excluded_host_are_denied(self):
        guard = ScopeGuard(policy())
        self.assertFalse(guard.decide("https://cdn.example.net/app.js").allowed)
        self.assertFalse(guard.decide("http://admin.localhost/").allowed)

    def test_redirect_outside_scope_is_denied(self):
        guard = ScopeGuard(policy())
        decision = guard.check_redirect("http://localhost/", "https://evil.example/")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "host_not_in_scope")

    def test_candidate_cannot_grant_permission(self):
        candidate = policy(False)
        candidate.allow_network_contact = True
        self.assertFalse(ScopeGuard(candidate).decide("http://localhost/").allowed)


if __name__ == "__main__":
    unittest.main()

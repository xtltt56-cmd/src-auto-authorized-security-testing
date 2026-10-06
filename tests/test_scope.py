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
    def test_confirmation_flags_must_be_real_booleans(self):
        for field in ("confirmed", "allow_network_contact"):
            for value in ("false", "true", 1, 0, None):
                document = dict(policy().canonical())
                document[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ScopePolicy.from_mapping(document)

    def test_empty_ports_do_not_grant_all_ports(self):
        document = dict(policy().canonical(), allowed_ports=[])
        self.assertFalse(ScopeGuard(ScopePolicy.from_mapping(document)).decide("http://localhost:8765/").allowed)

    def test_explicit_zero_port_is_not_treated_as_default_port(self):
        decision = ScopeGuard(policy()).decide("http://localhost:0/")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "invalid_port")

    def test_relative_redirect_is_resolved_before_scope_check(self):
        decision = ScopeGuard(policy()).check_redirect("http://localhost:8765/start", "/health")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.url, "http://localhost:8765/health")

    def test_control_characters_and_empty_userinfo_are_denied(self):
        guard = ScopeGuard(policy())
        for url in ("http://@localhost/", "http://localhost/\n", "http://localhost/\\other"):
            with self.subTest(url=url):
                self.assertFalse(guard.decide(url).allowed)

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

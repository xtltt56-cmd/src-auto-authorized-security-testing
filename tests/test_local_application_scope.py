import unittest
from datetime import datetime, timedelta, timezone

from src_auto.scope import ScopeGuard, ScopePolicy


NOW = datetime(2026, 10, 6, 4, 0, tzinfo=timezone.utc)


def local_scope_document(port=8765, now=NOW):
    return {
        "schema_version": 2, "target_type": "local_web", "target_id": "owned-web",
        "origin": "http://127.0.0.1:{}".format(port),
        "confirmed": True, "allow_network_contact": True, "automation_allowed": True,
        "allowed_paths": ["/", "/api/health", "/api/admin/status"],
        "excluded_paths": ["/api/admin"], "allowed_methods": ["GET", "HEAD"],
        "window_start": (now - timedelta(minutes=5)).isoformat(),
        "window_end": (now + timedelta(minutes=5)).isoformat(),
        "authorization_note": "Operator-owned synthetic Web fixture only",
        "profile_id": "readonly-baseline-v1",
        "limits": {"concurrency": 1, "request_limit": 10, "task_timeout_seconds": 60,
                   "request_timeout_seconds": 3, "response_limit_bytes": 1024,
                   "output_limit_bytes": 16384},
    }


class LocalApplicationScopeTests(unittest.TestCase):
    def guard(self, **updates):
        return ScopeGuard(ScopePolicy.from_mapping(dict(local_scope_document(), **updates)))

    def test_exact_local_origin_and_approved_path(self):
        guard = self.guard()
        self.assertEqual(guard.policy.target_type, "local_web")
        self.assertTrue(guard.decide("http://127.0.0.1:8765/api/health", method="HEAD", now=NOW).allowed)
        for url in ("https://127.0.0.1:8765/", "http://127.0.0.1:8766/", "http://localhost:8765/",
                    "http://127.0.0.2:8765/", "http://example.test:8765/"):
            with self.subTest(url=url):
                self.assertFalse(guard.decide(url, now=NOW).allowed)

    def test_methods_paths_and_exclusions_are_enforced(self):
        guard = self.guard()
        for path, method in (("/api/admin/status", "GET"), ("/api/health/other", "GET"),
                             ("/api/health", "POST"), ("/api/reset", "GET")):
            with self.subTest(path=path, method=method):
                self.assertFalse(guard.decide("http://127.0.0.1:8765" + path, method=method, now=NOW).allowed)

    def test_time_window_checked_on_every_decision(self):
        guard = self.guard()
        for at in (NOW - timedelta(hours=1), NOW + timedelta(hours=1)):
            self.assertFalse(guard.decide("http://127.0.0.1:8765/", now=at).allowed)
        self.assertFalse(guard.decide("http://127.0.0.1:8765/", now=NOW.replace(tzinfo=None)).allowed)

    def test_ambiguous_or_sensitive_url_shapes_are_rejected(self):
        guard = self.guard()
        for path in ("/api/%68ealth", "/api/../api/health", "//api/health", "/api/health?token=x",
                     "/api/health#fragment", "/api/health;other", "/api/health\\x", "/api/health\t"):
            with self.subTest(path=path):
                self.assertFalse(guard.decide("http://127.0.0.1:8765" + path, now=NOW).allowed)

    def test_redirect_is_joined_and_rechecked(self):
        guard = self.guard()
        self.assertTrue(guard.check_redirect("http://127.0.0.1:8765/", "/api/health", now=NOW).allowed)
        for destination in ("//example.test/", "/api/admin/status", "http://127.0.0.1:8766/"):
            self.assertFalse(guard.check_redirect("http://127.0.0.1:8765/", destination, now=NOW).allowed)

    def test_security_fields_affect_approval_digest_and_round_trip(self):
        document = local_scope_document()
        policy = ScopePolicy.from_mapping(document)
        self.assertEqual(policy.digest(), ScopePolicy.from_mapping(policy.canonical()).digest())
        for field, value in (("allowed_paths", ["/"]), ("excluded_paths", ["/api"]),
                             ("allowed_methods", ["HEAD"]), ("automation_allowed", False),
                             ("authorization_note", "different approval"),
                             ("window_end", (NOW + timedelta(hours=1)).isoformat()),
                             ("limits", dict(document["limits"], request_limit=11))):
            changed = dict(document, **{field: value})
            with self.subTest(field=field):
                self.assertNotEqual(policy.digest(), ScopePolicy.from_mapping(changed).digest())

    def test_local_contract_rejects_incomplete_or_ambiguous_permissions(self):
        for field, value in (("origin", "http://localhost:8765"), ("origin", "http://192.168.1.1:8765"),
                             ("origin", "http://127.0.0.1:8765/path"), ("origin", "http://127.0.0.1"),
                             ("allowed_paths", []), ("allowed_paths", ["/*"]),
                             ("allowed_methods", ["POST"]), ("confirmed", "false"),
                             ("window_end", "2026-10-06T12:00:00"), ("unknown_permission", True),
                             ("limits", dict(local_scope_document()["limits"], request_limit=True)),
                             ("limits", dict(local_scope_document()["limits"], concurrency=2))):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                ScopePolicy.from_mapping(dict(local_scope_document(), **{field: value}))

    def test_candidate_and_automation_disabled_remain_blocked(self):
        for update in ({"confirmed": False}, {"allow_network_contact": False}, {"automation_allowed": False}):
            self.assertFalse(self.guard(**update).decide("http://127.0.0.1:8765/", now=NOW).allowed)

    def test_version_and_legacy_permission_fields_cannot_be_silently_ignored(self):
        for update in ({"schema_version": 3}, {"target_type": "native_app"},
                       {"allowed_ports": []}, {"root_domains": ["localhost"]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                ScopePolicy.from_mapping(dict(local_scope_document(), **update))

    def test_ipv6_loopback_is_explicit_and_not_a_hostname_alias(self):
        guard = self.guard(origin="http://[::1]:8765")
        self.assertTrue(guard.decide("http://[::1]:8765/", now=NOW).allowed)
        self.assertFalse(guard.decide("http://127.0.0.1:8765/", now=NOW).allowed)


if __name__ == "__main__":
    unittest.main()

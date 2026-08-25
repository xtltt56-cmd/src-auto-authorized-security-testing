import json
import tempfile
import unittest
from pathlib import Path


class DefensePlanningTests(unittest.TestCase):
    def test_confirmed_owned_domain_builds_bounded_observation_plan(self):
        from src_auto.defense import DefenseAsset, build_defense_plan

        asset = DefenseAsset.from_mapping(
            {
                "asset_id": "company-web",
                "domain": "Example.COM.",
                "authorization_source": "内部资产清单 #42",
                "confirmed_owned": True,
                "allow_automated_observation": True,
            }
        )
        plan = build_defense_plan(asset)
        self.assertEqual(asset.domain, "example.com")
        self.assertEqual(plan["mode"], "defense_observation")
        self.assertEqual(plan["rate_limit_per_second"], 1)
        self.assertEqual(plan["steps"], ["dns_snapshot", "tls_snapshot", "http_headers", "asset_diff", "log_review"])
        self.assertNotIn("exploit", str(plan).lower())
        self.assertNotIn("brute", str(plan).lower())

    def test_unconfirmed_or_wildcard_domain_is_rejected(self):
        from src_auto.defense import DefenseAsset, DefenseError, build_defense_plan

        with self.assertRaisesRegex(DefenseError, "wildcard_not_allowed"):
            DefenseAsset.from_mapping({"asset_id": "x", "domain": "*.example.com"})
        asset = DefenseAsset.from_mapping({"asset_id": "x", "domain": "example.com"})
        with self.assertRaisesRegex(DefenseError, "ownership_confirmation_required"):
            build_defense_plan(asset)

    def test_snapshot_diff_contains_metadata_only(self):
        from src_auto.defense import compare_defense_snapshots

        before = {"dns": {"A": ["192.0.2.1"]}, "tls": {"issuer": "CA1"}, "body": "secret-old"}
        after = {"dns": {"A": ["192.0.2.2"]}, "tls": {"issuer": "CA2"}, "body": "secret-new"}
        diff = compare_defense_snapshots(before, after)
        self.assertIn("$.dns.A[0]", diff["changed_paths"])
        self.assertIn("$.tls.issuer", diff["changed_paths"])
        self.assertNotIn("secret-old", str(diff))
        self.assertNotIn("secret-new", str(diff))


class SecurityLogAnalysisTests(unittest.TestCase):
    def test_jsonl_log_summary_is_bounded_and_redacted(self):
        from src_auto.log_analysis import analyse_jsonl_security_log

        events = [
            {"timestamp": "2026-08-23T01:00:00Z", "status": 200, "path": "/", "ip": "192.0.2.10"},
            {"timestamp": "2026-08-23T01:00:01Z", "status": 401, "path": "/login", "ip": "192.0.2.11", "authorization": "Bearer secret"},
            {"timestamp": "2026-08-23T01:00:02Z", "status": 403, "path": "/admin", "ip": "192.0.2.11"},
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "access.jsonl"
            path.write_text("\n".join(json.dumps(item) for item in events), encoding="utf-8")
            report = analyse_jsonl_security_log(path, max_events=10)
        self.assertEqual(report["event_count"], 3)
        self.assertEqual(report["status_classes"]["4xx"], 2)
        self.assertEqual(report["top_paths"][0][0], "/")
        self.assertNotIn("Bearer", str(report))
        self.assertNotIn("192.0.2.11", str(report))
        self.assertTrue(report["manual_review_required"])

    def test_log_reader_rejects_unbounded_request(self):
        from src_auto.log_analysis import LogAnalysisError, analyse_jsonl_security_log

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "access.jsonl"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(LogAnalysisError, "max_events_out_of_range"):
                analyse_jsonl_security_log(path, max_events=1000000)


if __name__ == "__main__":
    unittest.main()

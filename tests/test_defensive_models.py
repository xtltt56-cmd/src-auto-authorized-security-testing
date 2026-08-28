import json
import tempfile
import unittest
from pathlib import Path


class DefensiveModelTests(unittest.TestCase):
    def test_owned_asset_profile_and_asset_change_are_metadata_only(self):
        from src_auto.defense import AssetChange, OwnedAssetProfile

        profile = OwnedAssetProfile.from_mapping(
            {
                "asset_id": "owned-site",
                "domain": "Example.COM.",
                "authorization_source": "inventory-7",
                "confirmed_owned": True,
                "allow_automated_observation": True,
            }
        )
        self.assertEqual(profile.domain, "example.com")
        change = AssetChange(path="$.tls.issuer", change_type="changed")
        self.assertEqual(change.change_type, "changed")
        self.assertNotIn("secret", str(change).lower())

    def test_parse_and_summarize_supported_json_logs_hash_clients(self):
        from src_auto.log_analysis import DefensiveEvent, parse_defensive_log, summarize_defensive_events

        events = [
            {"source": "nginx", "status": 200, "path": "/" , "ip": "192.0.2.10"},
            {"source": "wazuh", "status": 403, "path": "/admin", "ip": "192.0.2.11", "authorization": "Bearer secret"},
            {"source": "zeek", "status": 500, "uri": "/api", "src_ip": "192.0.2.11"},
            {"source": "suricata", "event_type": "alert", "url": "https://example.test/x?token=secret", "src_ip": "192.0.2.12"},
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(item) for item in events), encoding="utf-8")
            parsed = parse_defensive_log(path, max_events=10, project_root=Path(temp))
        self.assertEqual(len(parsed), 4)
        self.assertTrue(all(isinstance(item, DefensiveEvent) for item in parsed))
        summary = summarize_defensive_events(parsed)
        self.assertTrue(summary["manual_review_required"])
        self.assertIn("4xx", summary["status_classes"])
        self.assertNotIn("192.0.2.11", json.dumps(summary, ensure_ascii=False))
        self.assertNotIn("secret", json.dumps(summary, ensure_ascii=False))

    def test_log_path_must_stay_under_project_root(self):
        from src_auto.log_analysis import LogAnalysisError, parse_defensive_log

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            root.mkdir()
            outside = Path(temp) / "outside.jsonl"
            outside.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(LogAnalysisError, "log_path_outside_project"):
                parse_defensive_log(outside, project_root=root)


if __name__ == "__main__":
    unittest.main()

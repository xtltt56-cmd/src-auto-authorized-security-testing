import tempfile
import unittest
from pathlib import Path

from src_auto.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite3")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_asset_fingerprint_and_incremental_diff(self):
        first = self.store.create_run("local-lab", "scope-a", "local")
        self.store.snapshot_assets(first, [{"host": "localhost", "port": 8765, "url": "http://localhost:8765/"}])
        second = self.store.create_run("local-lab", "scope-a", "local")
        self.store.snapshot_assets(
            second,
            [
                {"host": "localhost", "port": 8765, "url": "http://localhost:8765/"},
                {"host": "api.localhost", "port": 8765, "url": "http://api.localhost:8765/"},
            ],
        )
        diff = self.store.diff_assets(first, second)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(len(diff["removed"]), 0)
        self.assertEqual(len(diff["unchanged"]), 1)

    def test_finding_dedup_uses_stable_fingerprint(self):
        run_id = self.store.create_run("local-lab", "scope-a", "local")
        finding = {
            "run_id": run_id,
            "title": "Missing security header",
            "url": "http://localhost:8765/",
            "parameter": "",
            "severity": "low",
            "evidence": "X-Content-Type-Options absent",
        }
        first = self.store.insert_finding(finding)
        second = self.store.insert_finding(dict(finding))
        self.assertTrue(first.inserted)
        self.assertFalse(second.inserted)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(len(self.store.list_findings(run_id)), 1)

    def test_duplicate_finding_remains_visible_in_each_run(self):
        first_run = self.store.create_run("local-lab", "scope-a", "local")
        second_run = self.store.create_run("local-lab", "scope-a", "local")
        finding = {
            "title": "Missing security header",
            "url": "http://localhost:8765/",
            "severity": "low",
            "evidence": "header absent",
        }
        finding["run_id"] = first_run
        self.store.insert_finding(finding)
        finding["run_id"] = second_run
        self.store.insert_finding(finding)
        self.assertEqual(len(self.store.list_findings(first_run)), 1)
        self.assertEqual(len(self.store.list_findings(second_run)), 1)
        self.assertEqual(self.store.list_findings(second_run)[0]["run_id"], second_run)

    def test_checkpoint_round_trip(self):
        run_id = self.store.create_run("local-lab", "scope-a", "local")
        self.store.save_checkpoint(run_id, "crawl", {"cursor": 3})
        self.assertEqual(self.store.load_checkpoint(run_id, "crawl"), {"cursor": 3})

    def test_spend_and_submission_audit_are_persistent(self):
        run_id = self.store.create_run("local-lab", "scope-a", "local")
        self.store.record_spend(0.25, "ollama_triage", run_id)
        self.store.record_submission("abc123", "accepted", 50.0, 12.0)
        summary = self.store.spend_summary()
        self.assertAlmostEqual(summary["total"], 0.25)
        self.assertEqual(summary["by_category"]["ollama_triage"], 0.25)
        self.assertEqual(self.store.list_submissions()[0]["status"], "accepted")

    def test_remote_ai_review_audit_is_persistent_and_separate(self):
        run_id = self.store.create_run("local-lab", "scope-a", "local")
        finding = {
            "run_id": run_id,
            "title": "Missing security header",
            "url": "http://localhost:8765/",
            "parameter": "",
            "severity": "low",
            "evidence": "header absent",
        }
        inserted = self.store.insert_finding(finding)
        review_id = self.store.insert_ai_review(
            {
                "run_id": run_id,
                "finding_fingerprint": inserted.fingerprint,
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "payload_digest": "a" * 64,
                "disposition": "manual_review",
                "confidence": 0.5,
                "reason": "Needs human verification.",
                "suggested_checks": ["repeat read-only request"],
                "input_tokens": 10,
                "output_tokens": 5,
                "estimated_cost_usd": 0.001,
            }
        )
        self.assertGreater(review_id, 0)
        reviews = self.store.list_ai_reviews(run_id=run_id)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["provider"], "deepseek")
        self.assertEqual(reviews[0]["suggested_checks"], ["repeat read-only request"])
        summary = self.store.ai_review_summary()
        self.assertEqual(summary["count"], 1)
        self.assertAlmostEqual(summary["estimated_cost_usd"], 0.001)


if __name__ == "__main__":
    unittest.main()

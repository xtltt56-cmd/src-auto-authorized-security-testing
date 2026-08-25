import json
import tempfile
import unittest
from pathlib import Path

from tools.run_autonomous_validation import (
    build_discovery_metrics,
    is_loopback_url,
    redact_text,
    safe_artifact_path,
)


class AutonomousValidationUnitTests(unittest.TestCase):
    def test_only_loopback_urls_are_accepted(self):
        self.assertTrue(is_loopback_url("http://127.0.0.1:3000/"))
        self.assertTrue(is_loopback_url("http://localhost:3000/"))
        self.assertFalse(is_loopback_url("http://192.168.1.10:3000/"))
        self.assertFalse(is_loopback_url("https://authorized.example/"))

    def test_redaction_removes_secrets_and_bounds_output(self):
        value = "Authorization: Bearer abc123 sk-testtoken1234 password=hello"
        redacted = redact_text(value)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("sk-testtoken1234", redacted)
        self.assertNotIn("hello", redacted)
        self.assertLessEqual(len(redacted), 4096)

    def test_artifact_paths_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inside = safe_artifact_path(root, root / "validation" / "report.json")
            self.assertEqual(inside, (root / "validation" / "report.json").resolve())
            with self.assertRaises(ValueError):
                safe_artifact_path(root, root.parent / "outside.json")

    def test_discovery_metrics_use_observable_values_and_unknowns(self):
        document = {
            "target_url": "http://127.0.0.1:3000/",
            "scan_metadata": {
                "discovered_urls": [
                    "http://127.0.0.1:3000/",
                    "http://127.0.0.1:3000/main.js",
                    "http://127.0.0.1:3000/rest/user/query?q=x",
                ],
                "external_urls_excluded": ["https://example.com/"],
            },
        }
        metrics = build_discovery_metrics(document)
        self.assertEqual(metrics["url_count"], 3)
        self.assertEqual(metrics["javascript_url_count"], 1)
        self.assertEqual(metrics["api_like_url_count"], 1)
        self.assertEqual(metrics["query_url_count"], 1)
        self.assertEqual(metrics["external_excluded_count"], 1)
        self.assertIsNone(metrics["html_route_count"])

    def test_metrics_document_is_json_serializable(self):
        metrics = build_discovery_metrics({"scan_metadata": {"discovered_urls": []}})
        json.dumps(metrics, ensure_ascii=False)
        self.assertEqual(metrics["remote_ai_calls"], 0)
        self.assertEqual(metrics["remote_ai_cost_cny"], 0.0)


if __name__ == "__main__":
    unittest.main()

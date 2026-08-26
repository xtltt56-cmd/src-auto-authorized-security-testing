import json
import tempfile
import unittest
from pathlib import Path

from src_auto.local_regression import (
    RegressionCase,
    evaluate_expectations,
    load_regression_cases,
    redact_regression_headers,
    safe_case_path,
)
from src_auto.cli import build_parser


class LocalRegressionTests(unittest.TestCase):
    def test_inventory_contains_only_bounded_non_destructive_cases(self):
        root = Path(__file__).parents[1]
        cases = load_regression_cases(root / "config" / "validation" / "local_regression_cases.json")
        self.assertGreaterEqual(len(cases), 9)
        self.assertEqual(
            {item.case_id for item in cases if item.lab_id == "business-api"},
            {
                "business-api-health-surface",
                "business-api-openapi-public-surface",
                "business-api-readonly-order-surface",
            },
        )
        self.assertTrue(all(not item.destructive for item in cases))
        self.assertTrue(all(item.path.startswith("/") for item in cases))
        self.assertTrue(all("http://" not in item.path and "https://" not in item.path for item in cases))

    def test_loader_rejects_absolute_or_destructive_case(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cases.json"
            path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "bad",
                                "lab_id": "dvwa",
                                "kind": "probe",
                                "method": "GET",
                                "path": "https://example.invalid/",
                                "destructive": True,
                                "expected": {"status_in": [200]},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_regression_cases(path)

    def test_safe_case_path_rejects_traversal_and_external_urls(self):
        self.assertEqual(safe_case_path("/WebGoat/start.mvc"), "/WebGoat/start.mvc")
        for value in ("https://example.invalid/", "//example.invalid/", "/../login.php", ""):
            with self.assertRaises(ValueError):
                safe_case_path(value)

    def test_expectations_return_bounded_evidence_without_body(self):
        case = RegressionCase(
            case_id="demo",
            lab_id="dvwa",
            kind="probe",
            method="GET",
            path="/login.php",
            query={},
            auth="none",
            expected={"status_in": [200], "body_contains": ["Login"], "body_size_min": 10},
            destructive=False,
            description="demo",
        )
        result = evaluate_expectations(case, {"status": 200, "body": "<title>Login</title>", "location": ""})
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("body", result)
        self.assertEqual(result["matched_assertions"], 3)

    def test_expectations_fail_closed_on_unexpected_redirect(self):
        case = RegressionCase(
            case_id="demo",
            lab_id="dvwa",
            kind="probe",
            method="GET",
            path="/login.php",
            query={},
            auth="none",
            expected={"status_in": [200], "location_not_contains": ["example.invalid"]},
            destructive=False,
            description="demo",
        )
        result = evaluate_expectations(
            case,
            {"status": 302, "body": "", "location": "http://example.invalid/out"},
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("status_in", result["failed_assertions"])
        self.assertIn("location_not_contains", result["failed_assertions"])

    def test_expectations_mark_policy_blocked_redirect_as_blocked(self):
        case = RegressionCase(
            case_id="demo",
            lab_id="dvwa",
            kind="auth-boundary",
            method="GET",
            path="/login.php",
            query={},
            auth="none",
            expected={"status_in": [302]},
            destructive=False,
            description="demo",
        )
        result = evaluate_expectations(
            case,
            {"status": 302, "body": "", "location": "<non-loopback-url>", "blocked_reason": "redirect_not_allowlisted"},
        )
        self.assertEqual(result["status"], "BLOCKED_SCOPE")

    def test_sensitive_headers_are_redacted(self):
        result = redact_regression_headers(
            {"Set-Cookie": "JSESSIONID=secret", "Authorization": "Bearer secret", "Content-Type": "text/html"}
        )
        self.assertEqual(result["set-cookie"], "<redacted>")
        self.assertEqual(result["authorization"], "<redacted>")
        self.assertEqual(result["content-type"], "text/html")

    def test_cli_exposes_local_regression_profile(self):
        args = build_parser().parse_args(
            ["local-regression", "--local-only", "--repeat-rounds", "1", "--lab", "dvwa", "--case", "dvwa-auth-boundary", "--json"]
        )
        self.assertEqual(args.command, "local-regression")
        self.assertTrue(args.local_only)
        self.assertEqual(args.repeat_rounds, 1)
        self.assertEqual(args.labs, ["dvwa"])
        self.assertEqual(args.case_ids, ["dvwa-auth-boundary"])


if __name__ == "__main__":
    unittest.main()

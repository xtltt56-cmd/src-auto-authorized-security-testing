import unittest

from tools.run_local_lab_validation import (
    adjudicate_zap_finding,
    build_lab_score,
    discovery_control_record,
    expected_control_cases,
    render_local_lab_report,
    schema_surface_control_record,
    schema_control_record,
    summarize_rounds,
)


class LocalLabValidationTests(unittest.TestCase):
    def test_juice_shop_control_candidate_is_true_but_not_bounty_ready(self):
        finding = {
            "title": "Content Security Policy (CSP) Header Not Set",
            "endpoint": "http://127.0.0.1:3000/",
            "evidence": "",
            "severity": "medium",
        }
        record = adjudicate_zap_finding("juice-shop", finding)
        self.assertEqual(record["status"], "TRUE_POSITIVE")
        self.assertEqual(record["expected_case_id"], "csp-header-control")
        self.assertFalse(record["submission_ready"])

    def test_low_value_informational_candidate_is_false_positive_for_bounty(self):
        finding = {
            "title": "Modern Web Application",
            "endpoint": "http://127.0.0.1:3000/",
            "evidence": "script marker",
            "severity": "info",
        }
        record = adjudicate_zap_finding("juice-shop", finding)
        self.assertEqual(record["status"], "FALSE_POSITIVE")
        self.assertFalse(record["submission_ready"])

    def test_unknown_candidate_remains_unverified(self):
        record = adjudicate_zap_finding(
            "dvwa",
            {"title": "Unknown Alert", "endpoint": "http://127.0.0.1:8081/", "evidence": "x", "severity": "medium"},
        )
        self.assertEqual(record["status"], "NOT_VERIFIED")

    def test_dvwa_known_header_controls_are_adjudicated_as_non_bounty_controls(self):
        record = adjudicate_zap_finding(
            "dvwa",
            {
                "title": "X-Content-Type-Options Header Missing",
                "endpoint": "http://127.0.0.1:8081/",
                "evidence": "header absent",
                "severity": "low",
            },
        )
        self.assertEqual(record["status"], "TRUE_POSITIVE")
        self.assertEqual(record["expected_case_id"], "dvwa-x-content-type-control")
        self.assertFalse(record["submission_ready"])

    def test_dvwa_clickjacking_control_is_adjudicated(self):
        record = adjudicate_zap_finding(
            "dvwa",
            {
                "title": "Missing Anti-clickjacking Header",
                "endpoint": "http://127.0.0.1:8081/",
                "evidence": "X-Frame-Options absent",
                "severity": "medium",
            },
        )
        self.assertEqual(record["status"], "TRUE_POSITIVE")
        self.assertEqual(record["expected_case_id"], "dvwa-clickjacking-control")

    def test_lab_score_keeps_control_and_bounty_results_separate(self):
        records = [
            {
                "title": "CSP",
                "endpoint": "http://127.0.0.1:3000/",
                "status": "TRUE_POSITIVE",
                "expected_case_id": "csp-header-control",
                "evidence": "absent",
                "baseline": "absent",
                "reproduction": "repeatable",
                "impact": "hardening",
                "submission_ready": False,
                "reviewer": "local-acceptance",
            }
        ]
        score = build_lab_score("juice-shop", records)
        self.assertEqual(score["control_metrics"]["precision"], 1.0)
        self.assertEqual(score["bounty_ready_count"], 0)

    def test_round_summary_reports_stability_without_claiming_accuracy(self):
        result = summarize_rounds([
            {"finding_count": 5, "discovery": {"api_url_count": 2}},
            {"finding_count": 5, "discovery": {"api_url_count": 2}},
            {"finding_count": 6, "discovery": {"api_url_count": 3}},
        ])
        self.assertEqual(result["finding_count_min"], 5)
        self.assertEqual(result["finding_count_max"], 6)
        self.assertEqual(result["finding_count_variance"], 0.222222)
        self.assertEqual(result["accuracy_status"], "NOT_INFERRED")

    def test_webgoat_health_surface_is_a_non_bounty_control(self):
        self.assertEqual(expected_control_cases("webgoat")[0]["case_id"], "webgoat-health-surface")
        record = discovery_control_record(
            "webgoat",
            {
                "status": "COMPLETED",
                "target": "http://127.0.0.1:8082/WebGoat/actuator/health",
                "network_contact": True,
            },
        )
        self.assertIsNotNone(record)
        self.assertEqual(record["expected_case_id"], "webgoat-health-surface")
        self.assertFalse(record["submission_ready"])

    def test_vampi_schema_smoke_is_a_non_bounty_api_control(self):
        cases = expected_control_cases("vampi")
        self.assertEqual([item["case_id"] for item in cases], ["vampi-openapi-surface", "vampi-readonly-schema-smoke"])
        record = schema_control_record(
            "vampi",
            {
                "status": "POSSIBLE_SCHEMA_CONTRACT_ISSUES",
                "schema_url": "http://127.0.0.1:8083/openapi.json",
                "report_path": "D:/project/validation/vampi/schemathesis.junit.xml",
            },
        )
        self.assertEqual(record["status"], "TRUE_POSITIVE")
        self.assertEqual(record["expected_case_id"], "vampi-readonly-schema-smoke")
        self.assertFalse(record["submission_ready"])
        surface = schema_surface_control_record("vampi", {"status": "POSSIBLE_SCHEMA_CONTRACT_ISSUES", "schema_url": "http://127.0.0.1:8083/openapi.json"})
        self.assertEqual(surface["expected_case_id"], "vampi-openapi-surface")

    def test_human_report_renderer_keeps_bounty_metric_separate(self):
        report = render_local_lab_report(
            {
                "status": "AUTHORIZED_LOCAL_VALIDATION_READY",
                "mode": "local-only",
                "target_count": 1,
                "labs": {
                    "webgoat": {
                        "status": "READY",
                        "target": "http://127.0.0.1:8082/",
                        "rounds": [
                            {"finding_count": 0, "discovery": {"api_url_count": 0, "auth_surface_count": 0}, "score": {"precision": 1.0, "recall": 1.0, "f1": 1.0}}
                        ],
                        "score": {"true_positive": 1, "false_positive": 0, "false_negative": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0, "bounty_ready_count": 0},
                    }
                },
                "p0": {"scope_escape": 0, "external_targets_contacted": 0, "remote_ai_calls": 0, "secret_leakage": 0, "crash": 0},
                "bounty_ready_count": 0,
                "submission_status": "NO_AUTO_SUBMISSION",
            }
        )
        self.assertIn("本地四靶场最终验收报告", report)
        self.assertIn("WebGoat", report)
        self.assertIn("bounty_ready_count=0", report)
        self.assertIn("不是补天赏金漏洞命中率", report)


if __name__ == "__main__":
    unittest.main()

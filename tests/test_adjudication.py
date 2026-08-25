import unittest

from src_auto.adjudication import (
    ALLOWED_ADJUDICATION_STATUSES,
    adjudicate_finding,
    benchmark_metrics,
    validate_adjudication_record,
)


class AdjudicationTests(unittest.TestCase):
    def test_true_positive_requires_reproduction_and_impact(self):
        record = adjudicate_finding(
            {
                "title": "CSP Header Not Set",
                "endpoint": "http://127.0.0.1:3000/",
                "status": "TRUE_POSITIVE",
                "expected_case_id": "csp-header-control",
                "evidence": "Content-Security-Policy absent",
                "baseline": "header absent on baseline request",
                "reproduction": "repeat GET returned 200 without CSP",
                "impact": "browser hardening control absent",
                "submission_ready": False,
                "reviewer": "local-acceptance",
            }
        )
        self.assertEqual(record["status"], "TRUE_POSITIVE")
        self.assertIn(record["status"], ALLOWED_ADJUDICATION_STATUSES)
        validate_adjudication_record(record)

    def test_possible_or_false_positive_may_explain_lack_of_reproduction(self):
        record = adjudicate_finding(
            {
                "title": "Modern Web Application",
                "endpoint": "http://127.0.0.1:3000/",
                "status": "FALSE_POSITIVE",
                "expected_case_id": "",
                "evidence": "Angular marker",
                "baseline": "not applicable",
                "reproduction": "no security impact",
                "impact": "informational fingerprint only",
                "submission_ready": False,
                "reviewer": "local-acceptance",
            }
        )
        validate_adjudication_record(record)
        self.assertEqual(record["status"], "FALSE_POSITIVE")

    def test_benchmark_metrics_report_control_precision_and_bounty_readiness_separately(self):
        records = [
            adjudicate_finding({
                "title": "CSP Header Not Set", "endpoint": "http://127.0.0.1:3000/", "status": "TRUE_POSITIVE", "expected_case_id": "csp-header-control",
                "evidence": "absent", "baseline": "same", "reproduction": "repeatable", "impact": "hardening",
                "submission_ready": False, "reviewer": "local-acceptance",
            }),
            adjudicate_finding({
                "title": "Timestamp", "endpoint": "http://127.0.0.1:3000/", "status": "FALSE_POSITIVE", "expected_case_id": "",
                "evidence": "fixed timestamp", "baseline": "same", "reproduction": "no impact", "impact": "info",
                "submission_ready": False, "reviewer": "local-acceptance",
            }),
        ]
        score = benchmark_metrics(records, [{"case_id": "csp-header-control", "positive": True}])
        self.assertEqual(score["true_positive"], 1)
        self.assertEqual(score["false_positive"], 1)
        self.assertEqual(score["false_negative"], 0)
        self.assertEqual(score["precision"], 0.5)
        self.assertEqual(score["recall"], 1.0)
        self.assertEqual(score["bounty_ready_count"], 0)

    def test_true_positive_without_required_evidence_is_rejected(self):
        record = adjudicate_finding({
            "title": "bad", "status": "TRUE_POSITIVE", "expected_case_id": "x",
            "evidence": "", "baseline": "", "reproduction": "", "impact": "",
            "submission_ready": True, "reviewer": "",
        })
        with self.assertRaises(ValueError):
            validate_adjudication_record(record)


if __name__ == "__main__":
    unittest.main()

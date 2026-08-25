import unittest

from src_auto.validation import (
    ALLOWED_STATUSES,
    compare_findings,
    generate_ground_truth_from_yaml,
    metrics_for,
    normalize_finding,
    validate_ground_truth,
)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.ground_truth = [
            {
                "challenge_id": "headerChallenge",
                "challenge_name": "Missing security headers",
                "category": "Security Misconfiguration",
                "difficulty": 1,
                "expected_vulnerability_type": "security header",
                "scanner_detectable": True,
                "requires_business_logic": False,
                "requires_authentication": False,
                "notes": "Safe passive check.",
            },
            {
                "challenge_id": "basketChallenge",
                "challenge_name": "Manipulate basket",
                "category": "Business Logic",
                "difficulty": 3,
                "expected_vulnerability_type": "business logic",
                "scanner_detectable": False,
                "requires_business_logic": True,
                "requires_authentication": True,
                "notes": "Manual workflow required.",
            },
        ]

    def test_ground_truth_schema_and_yaml_metadata_parser(self):
        validate_ground_truth(self.ground_truth)
        parsed = generate_ground_truth_from_yaml(
            """
---
- name: 'Missing security headers'
  category: 'Security Misconfiguration'
  difficulty: 1
  key: headerChallenge
  tags:
    - 'Security Misconfiguration'
"""
        )
        self.assertEqual(parsed[0]["challenge_id"], "headerChallenge")
        self.assertEqual(parsed[0]["challenge_name"], "Missing security headers")
        self.assertTrue(parsed[0]["scanner_detectable"])

        manual = generate_ground_truth_from_yaml(
            """
---
- name: 'Admin Section'
  category: 'Broken Access Control'
  difficulty: 2
  key: adminSectionChallenge
"""
        )
        self.assertTrue(manual[0]["requires_business_logic"])
        self.assertTrue(manual[0]["requires_authentication"])
        self.assertFalse(manual[0]["scanner_detectable"])

    def test_normalization_restricts_statuses_and_types(self):
        finding = normalize_finding(
            {
                "title": "Missing header",
                "category": "Security Misconfiguration",
                "endpoint": "http://127.0.0.1:3000/",
                "parameter": "",
                "method": "GET",
                "severity": "low",
                "confidence": "0.7",
                "evidence": "X-Test absent",
                "scanner": "passive",
            }
        )
        self.assertEqual(set(finding), {
            "title", "category", "endpoint", "parameter", "method", "severity",
            "confidence", "evidence", "scanner", "ai_analysis", "ground_truth_match", "status",
        })
        self.assertEqual(finding["status"], "NOT_VERIFIED")
        self.assertIn(finding["status"], ALLOWED_STATUSES)

    def test_compare_and_metrics_keep_business_logic_out_of_scanner_recall(self):
        findings = [
            normalize_finding(
                {
                    "title": "Missing security header",
                    "category": "Security Misconfiguration",
                    "endpoint": "http://127.0.0.1:3000/",
                    "evidence": "X-Frame-Options absent",
                    "status": "TRUE_POSITIVE",
                }
            ),
            normalize_finding(
                {
                    "title": "Unrelated warning",
                    "category": "Other",
                    "endpoint": "http://127.0.0.1:3000/health",
                    "evidence": "fixture",
                    "status": "FALSE_POSITIVE",
                }
            ),
        ]
        compared = compare_findings(findings, self.ground_truth)
        self.assertEqual(compared[0]["ground_truth_match"], "headerChallenge")
        self.assertEqual(compared[1]["ground_truth_match"], "")
        metrics = metrics_for(compared, self.ground_truth)
        self.assertEqual(metrics["true_positive"], 1)
        self.assertEqual(metrics["false_positive"], 1)
        self.assertEqual(metrics["false_negative"], 0)
        self.assertEqual(metrics["scanner_detectable_count"], 1)
        self.assertAlmostEqual(metrics["scanner_detectable_recall"], 1.0)

    def test_zero_denominators_are_explicit(self):
        metrics = metrics_for([], [])
        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)
        self.assertEqual(metrics["f1"], 0.0)
        self.assertEqual(metrics["scanner_detectable_recall"], 0.0)


if __name__ == "__main__":
    unittest.main()

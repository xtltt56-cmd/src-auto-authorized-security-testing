import json
import unittest
from pathlib import Path

from src_auto.ai import ModelRouter
from src_auto.agent_provider import configured_model
from src_auto.config import load_mapping
from tools.validate_local_model_selection import cases, grade
from tools.validate_local_model_loop import grade_loop

ROOT = Path(__file__).resolve().parents[1]


class LocalModelSelectionTests(unittest.TestCase):
    def test_all_local_lanes_use_one_model_and_preserve_cloud_gate(self):
        document = load_mapping(ROOT / "config/models.yaml")
        router = ModelRouter(document)
        routes = [router.route("triage", complexity) for complexity in ("low", "normal", "high")]
        self.assertEqual(len({x.model for x in routes}), 1)
        self.assertTrue(all(x.provider == "ollama" and x.endpoint == "http://127.0.0.1:11434" for x in routes))
        self.assertEqual(configured_model(ROOT, "local").provider.model, routes[0].model)
        self.assertFalse(document["remote_api"]["enabled"])

    def test_requested_memory_limit_preserves_other_policy_limits(self):
        policy = load_mapping(ROOT / "config/policy.yaml")
        self.assertEqual(policy["profile"], "balanced")
        self.assertEqual(policy["max_memory_gb"], 30)
        self.assertEqual(policy["max_cpu_percent"], 70)

    def test_grader_rejects_foreign_evidence_and_premature_finish(self):
        context = {"references": ["entry"], "observations": [{"id": "o1"}]}
        value = {"action": "finish", "reference": "entry", "evidence": ["o99"], "reason": "测试"}
        with self.assertRaisesRegex(ValueError, "foreign_evidence"):
            grade(json.dumps(value), context, {"finish"}, "entry")
        value["evidence"] = []
        self.assertEqual(grade(json.dumps(value), context, {"finish"}, "entry"), (False, "missing_evidence"))

    def test_grader_does_not_accept_every_schema_valid_action(self):
        context = {"references": ["entry"], "observations": []}
        value = {"action": "finish", "reference": "entry", "evidence": [], "reason": "测试"}
        self.assertFalse(grade(json.dumps(value), context, {"inspect_api_schema"}, "entry")[0])
        self.assertEqual(len(cases()), 6)

    def test_loop_grader_requires_selected_private_object_coverage(self):
        row = {"state": "completed", "steps": 3, "modelCalls": 4, "requests": 5,
               "candidates": 0, "confirmed": False, "submissionReady": False,
               "observations": [{"action": "compare_object_authorization", "reference": "case-16",
                                 "status": "ok", "access": "public", "statuses": [200, 200, 200],
                                 "candidate": False}]}
        self.assertFalse(grade_loop(row, "case-11", 0))
        row["observations"][0].update(reference="case-11", access="private", statuses=[200, 403, 403])
        self.assertTrue(grade_loop(row, "case-11", 0))
        row["submissionReady"] = True
        self.assertFalse(grade_loop(row, "case-11", 0))


if __name__ == "__main__":
    unittest.main()

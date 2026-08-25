import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src_auto import cli
from src_auto.target_review import review_target_selection


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TargetReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT))
        self.root = Path(self.temp_root.name)

    def tearDown(self):
        self.temp_root.cleanup()

    def _write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _scope(self, host="127.0.0.1", port=3000, confirmed=True, allow=True):
        return self._write_json(
            "scope.json",
            {
                "target_id": "review-test",
                "root_domains": [],
                "allowed_hosts": [host],
                "excluded_hosts": [],
                "allowed_ports": [port],
                "confirmed": confirmed,
                "allow_network_contact": allow,
            },
        )

    def _plan(self, url="http://127.0.0.1:3000/"):
        return self._write_json(
            "plan.json",
            {
                "name": "manual-review-test",
                "operator": "test-operator",
                "authorization_note": "local mock only",
                "manual_execution_confirmed": True,
                "target_urls": [url],
                "sequence": ["httpx"],
                "commands": {
                    "httpx": ["-silent", "-u", url, "--header", "Authorization: SECRET_SHOULD_NOT_PRINT"]
                },
            },
        )

    def test_confirmed_local_selection_is_offline_and_digestable(self):
        scope = self._scope()
        plan = self._plan()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network must not be used")):
            result = review_target_selection(PROJECT_ROOT, scope, plan, confirm_selection=True)
        self.assertEqual(result["status"], "selection_reviewed")
        self.assertFalse(result["network_contact"])
        self.assertEqual(result["target_count"], 1)
        self.assertEqual(result["targets"][0]["kind"], "loopback")
        self.assertRegex(result["scope_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["plan_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["next_step"], "run-live --execute-live")

    def test_selection_requires_a_separate_human_confirmation(self):
        result = review_target_selection(PROJECT_ROOT, self._scope(), self._plan(), confirm_selection=False)
        self.assertEqual(result["status"], "awaiting_selection")
        self.assertFalse(result["network_contact"])
        self.assertEqual(result["reason"], "confirm_selection_required")

    def test_nonlocal_mock_review_never_contacts_target(self):
        scope = self._scope(host="authorized.example", port=443)
        plan = self._plan("https://authorized.example/health")
        with patch("urllib.request.urlopen", side_effect=AssertionError("nonlocal target must not be contacted")):
            result = review_target_selection(PROJECT_ROOT, scope, plan, confirm_selection=True)
        self.assertEqual(result["status"], "selection_reviewed")
        self.assertEqual(result["targets"][0]["kind"], "nonlocal")
        self.assertFalse(result["network_contact"])

    def test_out_of_scope_target_fails_closed(self):
        result = review_target_selection(
            PROJECT_ROOT,
            self._scope(host="127.0.0.1", port=3000),
            self._plan("http://127.0.0.1:8765/"),
            confirm_selection=True,
        )
        self.assertEqual(result["status"], "blocked_selection")
        self.assertEqual(result["reason"], "port_not_in_scope")
        self.assertFalse(result["network_contact"])
        self.assertFalse(result["targets"][0]["allowed"])

    def test_unconfirmed_scope_fails_closed(self):
        result = review_target_selection(
            PROJECT_ROOT,
            self._scope(confirmed=False, allow=False),
            self._plan(),
            confirm_selection=True,
        )
        self.assertEqual(result["status"], "blocked_scope")
        self.assertEqual(result["reason"], "scope_confirmation_required")
        self.assertFalse(result["network_contact"])

    def test_scope_and_plan_must_be_inside_project(self):
        plan = self._plan()
        outside_scope = PROJECT_ROOT.parent / "target-review-scope-must-not-be-created.json"
        result = review_target_selection(PROJECT_ROOT, outside_scope, plan, confirm_selection=True)
        self.assertEqual(result["status"], "blocked_scope")
        self.assertEqual(result["reason"], "scope_outside_project_root")

        scope = self._scope()
        outside_plan = PROJECT_ROOT.parent / "target-review-plan-must-not-be-created.json"
        result = review_target_selection(PROJECT_ROOT, scope, outside_plan, confirm_selection=True)
        self.assertEqual(result["status"], "blocked_plan")
        self.assertEqual(result["reason"], "plan_outside_project_root")

    def test_cli_json_and_human_outputs_are_safe(self):
        scope = self._scope()
        plan = self._plan()
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = cli.main(
                [
                    "target-review",
                    "--scope",
                    str(scope),
                    "--plan",
                    str(plan),
                    "--confirm-selection",
                    "--json",
                ]
            )
        self.assertEqual(exit_code, 0)
        document = json.loads(output.getvalue())
        self.assertEqual(document["status"], "selection_reviewed")
        self.assertFalse(document["network_contact"])

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = cli.main(
                [
                    "target-review",
                    "--scope",
                    str(scope),
                    "--plan",
                    str(plan),
                    "--confirm-selection",
                    "--human",
                ]
            )
        self.assertEqual(exit_code, 0)
        human = output.getvalue()
        self.assertIn("人工目标审阅", human)
        self.assertIn("run-live --execute-live", human)
        self.assertNotIn("SECRET_SHOULD_NOT_PRINT", human)


if __name__ == "__main__":
    unittest.main()

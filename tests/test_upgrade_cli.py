import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src_auto import cli


PROJECT_ROOT = Path(__file__).parents[1]


class UpgradeCliTests(unittest.TestCase):
    def _run(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(argv)
        return code, json.loads(stream.getvalue())

    def test_parser_exposes_offline_comparison_and_defense_commands(self):
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["api-compare", "--owner", "a", "--peer", "b", "--anonymous", "c", "--output", "d", "--json"]).command, "api-compare")
        self.assertEqual(parser.parse_args(["defense-plan", "--asset", "a", "--output", "b", "--json"]).command, "defense-plan")
        self.assertEqual(parser.parse_args(["log-review", "--input", "a", "--output", "b", "--json"]).command, "log-review")

    def test_api_comparison_is_project_local_and_redacts_bodies(self):
        validation = PROJECT_ROOT / "validation"
        with tempfile.TemporaryDirectory(dir=str(validation)) as temp:
            root = Path(temp)
            (root / "owner.json").write_text(json.dumps({"status_code": 200, "headers": {}, "body": {"id": "1", "secret": "owner-secret"}}), encoding="utf-8")
            (root / "peer.json").write_text(json.dumps({"status_code": 200, "headers": {}, "body": {"id": "1", "secret": "peer-secret"}}), encoding="utf-8")
            (root / "anon.json").write_text(json.dumps({"status_code": 401, "headers": {}, "body": {}}), encoding="utf-8")
            output = root / "result.json"
            code, payload = self._run(["api-compare", "--owner", str(root / "owner.json"), "--peer", str(root / "peer.json"), "--anonymous", str(root / "anon.json"), "--output", str(output), "--json"])
            document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(document["disposition"], "candidate_broken_object_authorization")
        self.assertNotIn("owner-secret", str(document))
        self.assertNotIn("peer-secret", str(document))

    def test_defense_plan_and_log_review_never_contact_network(self):
        validation = PROJECT_ROOT / "validation"
        with tempfile.TemporaryDirectory(dir=str(validation)) as temp:
            root = Path(temp)
            asset = root / "asset.json"
            asset.write_text(json.dumps({"asset_id": "owned-site", "domain": "example.com", "authorization_source": "inventory", "confirmed_owned": True, "allow_automated_observation": True}), encoding="utf-8")
            plan = root / "plan.json"
            code, payload = self._run(["defense-plan", "--asset", str(asset), "--output", str(plan), "--json"])
            log = root / "access.jsonl"
            log.write_text(json.dumps({"status": 403, "path": "/admin", "ip": "192.0.2.44"}) + "\n", encoding="utf-8")
            report = root / "log-report.json"
            log_code, log_payload = self._run(["log-review", "--input", str(log), "--output", str(report), "--json"])
            plan_document = json.loads(plan.read_text(encoding="utf-8"))
            report_document = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertFalse(payload["network_contact"])
        self.assertEqual(plan_document["mode"], "defense_observation")
        self.assertEqual(log_code, 0)
        self.assertFalse(log_payload["network_contact"])
        self.assertNotIn("192.0.2.44", str(report_document))

    def test_surface_plan_requires_scope_and_generates_without_execution(self):
        validation = PROJECT_ROOT / "validation"
        scope = PROJECT_ROOT / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"
        with tempfile.TemporaryDirectory(dir=str(validation)) as temp:
            output = Path(temp) / "surface-plan.json"
            code, payload = self._run([
                "surface-plan", "--target-id", "local-lab", "--url", "http://127.0.0.1:3000/",
                "--scope", str(scope), "--automation-allowed", "--output", str(output), "--json",
            ])
            document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "PLAN_READY")
        self.assertFalse(payload["network_contact"])
        self.assertFalse(document["execute"])
        self.assertTrue(document["manual_execution_required"])


if __name__ == "__main__":
    unittest.main()

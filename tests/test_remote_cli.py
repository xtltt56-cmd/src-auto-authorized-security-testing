import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src_auto.cli as cli
from src_auto.cli import build_parser
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store


class RemoteCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "state.sqlite3"
        self.scope_path = cli.DEFAULT_LOCAL_SCOPE
        self.guard = ScopeGuard(ScopePolicy.from_file(self.scope_path))
        store = Store(self.db_path)
        self.run_id = store.create_run("local-lab", self.guard.policy.digest(), "local")
        self.inserted = store.insert_finding(
            {
                "run_id": self.run_id,
                "title": "Missing security header",
                "url": "http://localhost:8765/",
                "parameter": "",
                "severity": "low",
                "evidence": "header absent",
            }
        )
        store.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv):
        output = io.StringIO()
        with patch.object(cli, "DB_PATH", self.db_path), contextlib.redirect_stdout(output):
            code = cli.main(argv)
        return code, json.loads(output.getvalue())

    def test_remote_commands_are_explicit_and_provider_scoped(self):
        parser = build_parser()
        preview = parser.parse_args(
            ["remote-preview", "--run-id", "run-1", "--finding-id", "1", "--provider", "deepseek"]
        )
        self.assertEqual(preview.command, "remote-preview")
        self.assertEqual(preview.provider, "deepseek")
        triage = parser.parse_args(
            [
                "remote-triage",
                "--run-id",
                "run-1",
                "--finding-id",
                "1",
                "--provider",
                "deepseek",
                "--confirm-external",
                "--confirm-digest",
                "a" * 64,
            ]
        )
        self.assertTrue(triage.confirm_external)
        self.assertEqual(triage.confirm_digest, "a" * 64)

    def test_remote_status_command_exists(self):
        args = build_parser().parse_args(["remote-status"])
        self.assertEqual(args.command, "remote-status")

    def test_preview_is_network_free_and_digest_bound(self):
        with patch("src_auto.cli._remote_provider", side_effect=AssertionError("preview must not build a sender")):
            code, value = self._run(
                [
                    "remote-preview",
                    "--run-id",
                    self.run_id,
                    "--finding-id",
                    str(self.inserted.row_id),
                    "--provider",
                    "deepseek",
                    "--scope",
                    str(self.scope_path),
                ]
            )
        self.assertEqual(code, 0)
        self.assertFalse(value["network_contact"])
        self.assertEqual(len(value["payload_digest"]), 64)
        self.assertNotIn("Authorization", json.dumps(value))

    def test_triage_requires_confirmation_before_provider_lookup(self):
        with patch("src_auto.cli._remote_provider", side_effect=AssertionError("confirmation gate bypassed")):
            code, value = self._run(
                [
                    "remote-triage",
                    "--run-id",
                    self.run_id,
                    "--finding-id",
                    str(self.inserted.row_id),
                    "--provider",
                    "deepseek",
                    "--scope",
                    str(self.scope_path),
                    "--confirm-digest",
                    "a" * 64,
                ]
            )
        self.assertEqual(code, 3)
        self.assertEqual(value["reason"], "confirm_external_required")
        self.assertFalse(value["network_contact"])

    def test_digest_mismatch_blocks_without_provider_lookup(self):
        with patch("src_auto.cli._remote_provider", side_effect=AssertionError("digest gate bypassed")):
            code, value = self._run(
                [
                    "remote-triage",
                    "--run-id",
                    self.run_id,
                    "--finding-id",
                    str(self.inserted.row_id),
                    "--provider",
                    "deepseek",
                    "--scope",
                    str(self.scope_path),
                    "--confirm-external",
                    "--confirm-digest",
                    "a" * 64,
                ]
            )
        self.assertEqual(code, 3)
        self.assertEqual(value["reason"], "payload_digest_mismatch")
        self.assertFalse(value["network_contact"])

    def test_successful_triage_persists_a_separate_review(self):
        preview_code, preview = self._run(
            [
                "remote-preview",
                "--run-id",
                self.run_id,
                "--finding-id",
                str(self.inserted.row_id),
                "--provider",
                "deepseek",
                "--scope",
                str(self.scope_path),
            ]
        )
        self.assertEqual(preview_code, 0)

        class FakeProvider:
            def review(self, finding):
                return {
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "disposition": "manual_review",
                    "confidence": 0.4,
                    "reason": "Human verification required.",
                    "suggested_checks": ["repeat a read-only request"],
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "estimated_cost_usd": 0.00002,
                }

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only-key"}, clear=False), patch(
            "src_auto.cli._remote_provider", return_value=FakeProvider()
        ):
            code, value = self._run(
                [
                    "remote-triage",
                    "--run-id",
                    self.run_id,
                    "--finding-id",
                    str(self.inserted.row_id),
                    "--provider",
                    "deepseek",
                    "--scope",
                    str(self.scope_path),
                    "--confirm-external",
                    "--confirm-digest",
                    preview["payload_digest"],
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(value["network_contact"])
        store = Store(self.db_path)
        try:
            reviews = store.list_ai_reviews(run_id=self.run_id)
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0]["provider"], "deepseek")
            self.assertEqual(store.list_findings(self.run_id)[0]["status"], "candidate")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()

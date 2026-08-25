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
from src_auto.runtime_policy import RuntimePolicy
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store


class RemoteCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "state.sqlite3"
        self.scope_path = cli.DEFAULT_LOCAL_SCOPE
        self.guard = ScopeGuard(ScopePolicy.from_file(self.scope_path))
        self.remote_runtime = RuntimePolicy.from_mapping(
            {
                "AI_PROVIDER": "local",
                "LOCAL_LLM_ONLY": False,
                "ALLOW_REMOTE_LLM": True,
                "allowed_hosts": ["localhost", "127.0.0.1"],
                "allowed_ports": [3000],
            }
        )
        self._consent = patch.dict(
            os.environ,
            {
                "SRC_AUTO_REMOTE_AI_CONSENT": "enabled",
                "SRC_AUTO_DEEPSEEK_CONSENT": "enabled",
            },
            clear=False,
        )
        self._consent.start()
        self.addCleanup(self._consent.stop)
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
        with patch.object(cli, "DB_PATH", self.db_path), patch.object(
            cli, "_runtime_policy", return_value=self.remote_runtime
        ), contextlib.redirect_stdout(output):
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
        openrouter = parser.parse_args(
            ["remote-preview", "--run-id", "run-1", "--finding-id", "1", "--provider", "openrouter"]
        )
        self.assertEqual(openrouter.provider, "openrouter")

    def test_remote_status_command_exists(self):
        args = build_parser().parse_args(["remote-status"])
        self.assertEqual(args.command, "remote-status")

    def test_remote_status_json_mode_remains_machine_readable(self):
        code, value = self._run(["remote-status", "--json"])
        self.assertEqual(code, 0)
        self.assertIn("providers", value)
        self.assertFalse(value["providers"]["deepseek"]["network_contact"])
        self.assertTrue(value["startup_consent_required"])
        self.assertTrue(value["providers"]["deepseek"]["session_consent"])

    def test_startup_consent_overlays_remote_runtime_only_for_current_session(self):
        with patch.dict(
            os.environ,
            {"SRC_AUTO_REMOTE_AI_CONSENT": "disabled", "SRC_AUTO_DEEPSEEK_CONSENT": "disabled"},
            clear=False,
        ):
            denied = cli._runtime_policy()
        self.assertTrue(denied.local_llm_only)
        self.assertFalse(denied.allow_remote_llm)

        with patch.dict(
            os.environ,
            {"SRC_AUTO_REMOTE_AI_CONSENT": "enabled", "SRC_AUTO_DEEPSEEK_CONSENT": "enabled"},
            clear=False,
        ):
            enabled = cli._runtime_policy()
        self.assertFalse(enabled.local_llm_only)
        self.assertTrue(enabled.allow_remote_llm)
        self.assertEqual(enabled.ai_provider, "remote")

        with patch.dict(
            os.environ,
            {
                "SRC_AUTO_REMOTE_AI_CONSENT": "disabled",
                "SRC_AUTO_DEEPSEEK_CONSENT": "disabled",
                "SRC_AUTO_OPENAI_CONSENT": "disabled",
                "SRC_AUTO_OPENROUTER_CONSENT": "enabled",
            },
            clear=False,
        ):
            openrouter_enabled = cli._runtime_policy()
        self.assertFalse(openrouter_enabled.local_llm_only)
        self.assertTrue(openrouter_enabled.allow_remote_llm)

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

    def test_triage_denied_by_startup_consent_before_provider_lookup(self):
        with patch.dict(
            os.environ,
            {"SRC_AUTO_REMOTE_AI_CONSENT": "disabled", "SRC_AUTO_DEEPSEEK_CONSENT": "disabled"},
            clear=False,
        ), patch("src_auto.cli._remote_provider", side_effect=AssertionError("consent gate bypassed")):
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
        self.assertEqual(value["reason"], "remote_ai_disabled_for_session")
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

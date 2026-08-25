import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src_auto.cli as cli
from src_auto.runtime_policy import RuntimePolicy


class JuiceShopCLITests(unittest.TestCase):
    def setUp(self):
        self.runtime = RuntimePolicy.from_mapping(
            {
                "AI_PROVIDER": "local",
                "LOCAL_LLM_ONLY": True,
                "ALLOW_REMOTE_LLM": False,
                "allowed_hosts": ["127.0.0.1", "localhost"],
                "allowed_ports": [3000],
            }
        )

    def _run(self, argv):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(cli, "DB_PATH", Path(temp) / "state.sqlite3"), patch.object(
                cli, "_runtime_policy", return_value=self.runtime
            ), contextlib.redirect_stdout(output):
                code = cli.main(argv)
        return code, json.loads(output.getvalue())

    def _run_human(self, argv):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(cli, "DB_PATH", Path(temp) / "state.sqlite3"), patch.object(
                cli, "_runtime_policy", return_value=self.runtime
            ), patch.object(output, "isatty", return_value=True), contextlib.redirect_stdout(output):
                code = cli.main(argv)
        return code, output.getvalue()

    def test_status_never_contacts_a_non_local_target(self):
        with patch.object(cli, "probe_local_target", side_effect=AssertionError("must be blocked before probe")):
            code, value = self._run(["juice-shop-status", "--url", "https://example.com/"])
        self.assertEqual(code, 3)
        self.assertEqual(value["reason"], "host_not_allowlisted")
        self.assertFalse(value["network_contact"])

    def test_status_reports_reachable_local_service(self):
        with patch.object(
            cli,
            "probe_local_target",
            return_value={"status": "reachable", "http_status": 200, "network_contact": True},
        ), patch.object(cli, "local_dependency_status", return_value={"docker_available_on_path": False}):
            code, value = self._run(["juice-shop-status"])
        self.assertEqual(code, 0)
        self.assertEqual(value["status"], "reachable")
        self.assertFalse(value["dependency"]["docker_available_on_path"])

    def test_status_human_mode_prints_simplified_chinese_summary(self):
        with patch.object(
            cli,
            "probe_local_target",
            return_value={
                "status": "reachable",
                "http_status": 200,
                "network_contact": True,
                "title": "OWASP Juice Shop",
            },
        ), patch.object(cli, "local_dependency_status", return_value={"docker_available_on_path": True}):
            code, output = self._run_human(["juice-shop-status"])
        self.assertEqual(code, 0)
        self.assertIn("本地 OWASP Juice Shop", output)
        self.assertIn("状态：可访问", output)

    def test_json_mode_adds_chinese_explanations_without_renaming_fields(self):
        code, value = self._run(["juice-shop-zap", "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(value["status"], "blocked_confirmation")
        self.assertEqual(value["status_zh"], "需要人工确认")
        self.assertEqual(value["reason"], "confirm_local_required")
        self.assertEqual(value["reason_zh"], "需要明确确认本机靶场")

    def test_parser_accepts_explicit_output_modes(self):
        human = cli.build_parser().parse_args(["juice-shop-status", "--human"])
        machine = cli.build_parser().parse_args(["juice-shop-status", "--json"])
        self.assertTrue(human.human)
        self.assertFalse(human.json_output)
        self.assertTrue(machine.json_output)
        self.assertFalse(machine.human)

    def test_help_text_is_simplified_chinese(self):
        help_text = cli.build_parser().format_help()
        self.assertIn("显示帮助并退出", help_text)
        self.assertIn("授权范围门控", help_text)

    def test_baseline_rejects_output_outside_project_root(self):
        code, value = self._run(["juice-shop-baseline", "--out-dir", "C:\\outside"])
        self.assertEqual(code, 3)
        self.assertEqual(value["reason"], "output_outside_project_root")
        self.assertFalse(value["network_contact"])

    def test_zap_requires_explicit_local_confirmation(self):
        code, value = self._run(["juice-shop-zap"])
        self.assertEqual(code, 3)
        self.assertEqual(value["reason"], "confirm_local_required")
        self.assertFalse(value["network_contact"])

    def test_zap_artifact_contains_chinese_explanations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out_dir = root / "validation"
            report = {
                "@version": "2.17.0",
                "site": [
                    {
                        "@name": "http://127.0.0.1:3000",
                        "alerts": [
                            {
                                "pluginid": "10038",
                                "name": "Content Security Policy (CSP) Header Not Set",
                                "riskcode": "2",
                                "confidence": "3",
                                "instances": [{"uri": "http://127.0.0.1:3000/", "method": "GET"}],
                            }
                        ],
                    }
                ],
            }

            def fake_zap(project_root, target_url, output_path, timeout=300):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(report), encoding="utf-8")
                return {"status": "completed", "returncode": 0, "report_path": str(output_path)}

            with patch.object(cli, "PROJECT_ROOT", root), patch.object(
                cli, "probe_local_target", return_value={"status": "reachable", "network_contact": True}
            ), patch.object(cli, "run_zap_quick_scan", side_effect=fake_zap):
                code, value = self._run(
                    [
                        "juice-shop-zap",
                        "--confirm-local",
                        "--scope",
                        str(Path(__file__).parents[1] / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"),
                        "--out-dir",
                        str(out_dir),
                    ]
                )
            self.assertEqual(code, 0)
            artifact = json.loads((out_dir / "zap_findings.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["status_zh"], "存在待人工复核的可能项")
            self.assertEqual(artifact["reason_zh"], "需要人工复核后才能确认")


if __name__ == "__main__":
    unittest.main()

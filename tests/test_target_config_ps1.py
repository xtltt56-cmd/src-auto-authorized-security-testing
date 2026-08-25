import json
import os
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
TARGET_CONFIG_SCRIPT = PROJECT_ROOT / "tools" / "target_config.ps1"


def _quote(value):
    return "'{}'".format(str(value).replace("'", "''"))


def _run_powershell(command):
    environment = os.environ.copy()
    for name in list(environment):
        if name.upper() == "PSMODULEPATH":
            del environment[name]
    user_profile = environment.get("USERPROFILE", r"C:\Users\lenovo")
    system_root = environment.get("SystemRoot", r"C:\Windows")
    environment["PSModulePath"] = ";".join(
        [
            str(Path(user_profile) / "Documents" / "WindowsPowerShell" / "Modules"),
            r"C:\Program Files\WindowsPowerShell\Modules",
            str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"),
        ]
    )
    return subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=str(PROJECT_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


class TargetConfigPowerShellTests(unittest.TestCase):
    def setUp(self):
        self.test_root = PROJECT_ROOT / "validation" / "test-gui-config"
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self.test_root.exists():
            for path in sorted(self.test_root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()

    def _draft(self, **overrides):
        draft = {
            "target_id": "demo-target",
            "vendor": "Demo Vendor",
            "authorization_source": "platform ticket DEMO-1",
            "target_url": "https://app.example.com/",
            "root_domains": ["example.com"],
            "allowed_hosts": ["app.example.com"],
            "excluded_hosts": [],
            "allowed_ports": [443],
            "test_window": "operator-confirmed window",
            "operator": "operator",
            "confirmed": False,
            "allow_network_contact": False,
            "manual_execution_confirmed": False,
        }
        draft.update(overrides)
        return draft

    def _invoke(self, expression):
        command = ". {script}; {expression}".format(
            script=_quote(TARGET_CONFIG_SCRIPT), expression=expression
        )
        return _run_powershell(command)

    def test_valid_draft_is_accepted(self):
        draft = json.dumps(self._draft(), ensure_ascii=False)
        result = self._invoke(
            "$draft = ConvertFrom-Json -InputObject {draft}; "
            "Test-TargetDraft -Draft $draft | ConvertTo-Json -Compress".format(
                draft=_quote(draft)
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])

    def test_invalid_url_reasons_are_explicit(self):
        cases = (
            ("http://app.example.com/", "target_url_must_use_https"),
            ("https://other.example.com/", "target_host_not_allowed"),
            ("https://user:pass@app.example.com/?x=1#fragment", "target_url_must_be_clean"),
        )
        for url, reason in cases:
            with self.subTest(reason=reason):
                draft = json.dumps(self._draft(target_url=url), ensure_ascii=False)
                result = self._invoke(
                    "$draft = ConvertFrom-Json -InputObject {draft}; "
                    "Test-TargetDraft -Draft $draft | ConvertTo-Json -Compress".format(
                        draft=_quote(draft)
                    )
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                document = json.loads(result.stdout)
                self.assertFalse(document["valid"])
                self.assertIn(reason, document["errors"])

    def test_write_target_config_stays_inside_project_and_defaults_to_unconfirmed(self):
        draft = json.dumps(self._draft(), ensure_ascii=False)
        result = self._invoke(
            "$draft = ConvertFrom-Json -InputObject {draft}; "
            "$result = Write-TargetConfig -Draft $draft -ProjectRoot {root}; "
            "$result | ConvertTo-Json -Compress".format(
                draft=_quote(draft), root=_quote(self.test_root)
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        paths = json.loads(result.stdout)
        scope = Path(paths["scope_path"])
        plan = Path(paths["plan_path"])
        self.assertTrue(str(scope).lower().startswith(str(self.test_root).lower()))
        self.assertTrue(scope.exists())
        self.assertTrue(plan.exists())
        scope_document = json.loads(scope.read_text(encoding="utf-8"))
        plan_document = json.loads(plan.read_text(encoding="utf-8"))
        self.assertFalse(scope_document["confirmed"])
        self.assertFalse(scope_document["allow_network_contact"])
        self.assertFalse(plan_document["manual_execution_confirmed"])


if __name__ == "__main__":
    unittest.main()

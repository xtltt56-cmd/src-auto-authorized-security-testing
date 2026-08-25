import os
import subprocess
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
HELPER = PROJECT_ROOT / "tools" / "deepseek_secret.ps1"
SAVE_SCRIPT = PROJECT_ROOT / "tools" / "save_deepseek_key.ps1"


def _ps_quote(value: Path) -> str:
    return "'{}'".format(str(value).replace("'", "''"))


def _run_powershell(command: str) -> subprocess.CompletedProcess:
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


class DeepSeekSecretTests(unittest.TestCase):
    def test_dpapi_helper_is_utf8_bom_encoded(self):
        self.assertTrue(HELPER.exists(), "DPAPI helper must exist")
        self.assertTrue(
            HELPER.read_bytes().startswith(b"\xef\xbb\xbf"),
            "Windows PowerShell 5.1 needs a UTF-8 BOM for project scripts",
        )

    def test_dpapi_round_trip_stays_encrypted_and_project_bound(self):
        fixture = "dummy-deepseek-key-not-real"
        test_dir = PROJECT_ROOT / "validation" / "test-secrets"
        test_dir.mkdir(parents=True, exist_ok=True)
        secret_path = test_dir / "{}.dpapi".format(uuid.uuid4().hex)
        self.addCleanup(lambda: secret_path.unlink(missing_ok=True))
        command = (
            ". {helper}; "
            "$secure = ConvertTo-SecureString '{fixture}' -AsPlainText -Force; "
            "Protect-DeepSeekKey -SecureKey $secure -Path {secret} -ProjectRoot {root}; "
            "$plain = Unprotect-DeepSeekKey -Path {secret} -ProjectRoot {root}; "
            "$secure.Dispose(); [Console]::Out.Write($plain)"
        ).format(
            helper=_ps_quote(HELPER),
            fixture=fixture,
            secret=_ps_quote(secret_path),
            root=_ps_quote(PROJECT_ROOT),
        )
        result = _run_powershell(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, fixture)
        encrypted = secret_path.read_text(encoding="utf-8-sig")
        self.assertNotIn(fixture, encrypted)
        self.assertGreater(len(encrypted.strip()), len(fixture))

    def test_dpapi_rejects_path_outside_project(self):
        outside = Path(r"C:\Windows\Temp\src-auto-outside.dpapi")
        command = (
            ". {helper}; "
            "$secure = ConvertTo-SecureString 'dummy-not-real' -AsPlainText -Force; "
            "Protect-DeepSeekKey -SecureKey $secure -Path {outside} -ProjectRoot {root}"
        ).format(
            helper=_ps_quote(HELPER),
            outside=_ps_quote(outside),
            root=_ps_quote(PROJECT_ROOT),
        )
        result = _run_powershell(command)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("deepseek_secret_path_outside_project", result.stderr)

    def test_save_interface_is_hidden_dpapi_only_and_ignored(self):
        self.assertTrue(SAVE_SCRIPT.exists(), "save interface must exist")
        self.assertTrue(SAVE_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf"))
        content = SAVE_SCRIPT.read_text(encoding="utf-8-sig")
        self.assertIn("Read-Host", content)
        self.assertIn("-AsSecureString", content)
        self.assertIn("Protect-DeepSeekKey", content)
        self.assertIn("config\\secrets\\deepseek_api_key.dpapi", content)
        self.assertNotIn("setx", content.lower())
        self.assertNotIn("DEEPSEEK_API_KEY =", content)
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("config/secrets/", gitignore)


if __name__ == "__main__":
    unittest.main()

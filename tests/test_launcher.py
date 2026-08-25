import unittest
from pathlib import Path


class LauncherTests(unittest.TestCase):
    def test_deepseek_ping_is_utf8_bom_encoded_for_windows_powershell(self):
        path = Path(__file__).parents[1] / "tools" / "deepseek_ping.ps1"
        self.assertTrue(
            path.read_bytes().startswith(b"\xef\xbb\xbf"),
            "Windows PowerShell 5.1 needs a UTF-8 BOM to parse the Chinese DeepSeek check",
        )

    def test_launcher_is_utf8_bom_encoded_for_windows_powershell(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        self.assertTrue(
            path.read_bytes().startswith(b"\xef\xbb\xbf"),
            "Windows PowerShell 5.1 needs a UTF-8 BOM to parse Chinese launcher text",
        )

    def test_launcher_suppresses_powershell_progress_redraw(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8")
        self.assertIn(
            "$ProgressPreference = 'SilentlyContinue'",
            content,
            "Invoke-WebRequest progress redraws Chinese launcher output in Windows Terminal",
        )

    def test_one_click_launcher_is_manual_and_local_only(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8")
        self.assertIn("ollama", content.lower())
        self.assertIn("src_auto new", content)
        self.assertIn("src_auto run", content)
        self.assertNotIn("schtasks", content.lower())
        self.assertNotIn("New-ScheduledTask", content)
        self.assertIn("local-lab", content)
        self.assertIn("Start-Process", content)
        self.assertIn("11434", content)
        self.assertIn("仅本机回环靶场", content)
        self.assertIn("正在执行四靶场本地验收", content)
        self.assertIn("run_local_regression.py", content)
        self.assertIn("PYTHONIOENCODING", content)
        self.assertIn("Read-Host", content)
        self.assertIn("SRC_AUTO_DEEPSEEK_CONSENT", content)
        self.assertIn("remote_ai_disabled_for_session", content)
        self.assertIn("需要新的 DEEPSEEK_API_KEY", content)
        self.assertIn("-AsSecureString", content)
        self.assertIn("仅当前启动会话", content)
        self.assertNotIn("setx deepseek_api_key", content.lower())

    def test_launcher_loads_dpapi_key_only_after_affirmative_consent(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("config\\secrets\\deepseek_api_key.dpapi", content)
        self.assertIn("deepseek_secret.ps1", content)
        self.assertIn("Unprotect-DeepSeekKey", content)
        self.assertIn("加密密钥解密失败", content)
        consent = content.index("$deepSeekAnswer =")
        affirmative = content.index("if($deepSeekAnswer -in")
        decrypt = content.index("Unprotect-DeepSeekKey")
        disabled = content.index("remote_ai_disabled_for_session")
        self.assertLess(consent, affirmative)
        self.assertLess(affirmative, decrypt)
        self.assertLess(decrypt, disabled)

    def test_one_click_launcher_starts_only_loopback_juice_shop(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8").lower()
        compose = (path.parent / "docker-compose.local-labs.yml").read_text(encoding="utf-8").lower()
        self.assertIn("dockerdesktop", content)
        self.assertIn("juice shop", content)
        self.assertIn("dvwa", content)
        self.assertIn("127.0.0.1:3000:3000", compose)
        self.assertIn("127.0.0.1:8081:80", compose)
        self.assertIn("webgoat", content)
        self.assertIn("127.0.0.1:8082:8080", compose)
        self.assertIn("vampi", content)
        self.assertIn("127.0.0.1:8083:5000", compose)
        self.assertIn("restart:", compose)
        self.assertIn("run_local_lab_validation.py", content)
        self.assertNotIn("-p 0.0.0.0", content + compose)


if __name__ == "__main__":
    unittest.main()

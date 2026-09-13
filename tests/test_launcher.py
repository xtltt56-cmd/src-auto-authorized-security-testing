import unittest
import json
from pathlib import Path


class LauncherTests(unittest.TestCase):
    def test_deepseek_uses_official_stable_model_id_and_separate_display_name(self):
        root = Path(__file__).parents[1]
        config = json.loads((root / "config" / "models.yaml").read_text(encoding="utf-8"))
        deepseek = config["remote_providers"]["deepseek"]
        self.assertEqual(deepseek["model"], "deepseek-v4-flash")
        self.assertEqual(deepseek["models_endpoint"], "https://api.deepseek.com/models")
        self.assertEqual(deepseek["catalog_aliases"], ["deepseek-v4-flash", "deepseek-flash"])
        self.assertIn("DeepSeek V4 Flash", deepseek["display_name"])
        self.assertNotIn("v4.1", deepseek["model"].lower())

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

    def test_launcher_sets_python_utf8_before_gui_dispatch(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8-sig")
        gui_dispatch = content.index("if(-not $RunLocalLab)")
        python_encoding = content.index("$env:PYTHONIOENCODING = 'utf-8'")
        self.assertLess(
            python_encoding,
            gui_dispatch,
            "the GUI branch must inherit UTF-8 before src_auto_gui.ps1 is invoked",
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
        self.assertIn("正在执行五靶场本地验收", content)
        self.assertIn("run_local_regression.py", content)
        self.assertIn("PYTHONIOENCODING", content)
        self.assertIn("Read-Host", content)
        self.assertIn("SRC_AUTO_DEEPSEEK_CONSENT", content)
        self.assertIn("remote_ai_disabled_for_session", content)
        self.assertIn("需要新的 DEEPSEEK_API_KEY", content)
        self.assertIn("-AsSecureString", content)
        self.assertIn("仅当前启动会话", content)
        self.assertNotIn("setx deepseek_api_key", content.lower())
        self.assertIn("Join-Path $env:LOCALAPPDATA 'Programs\\Ollama\\ollama.exe'", content)
        self.assertNotIn("C:\\Users\\lenovo", content)

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

    def test_ping_reuses_saved_dpapi_key_only_after_consent_and_validates_model_catalog(self):
        path = Path(__file__).parents[1] / "tools" / "deepseek_ping.ps1"
        content = path.read_text(encoding="utf-8-sig")
        consent = content.index("$answer =")
        decrypt = content.index("Unprotect-DeepSeekKey")
        request = content.index("[System.Net.WebRequest]::Create($ModelsEndpoint)")
        self.assertLess(consent, decrypt)
        self.assertLess(decrypt, request)
        self.assertIn("$ModelId = 'deepseek-v4-flash'", content)
        self.assertIn("$CatalogAliases = @('deepseek-v4-flash', 'deepseek-flash')", content)
        self.assertIn("$ids -contains $_", content)
        self.assertIn("config\\secrets\\deepseek_api_key.dpapi", content)

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

    def test_one_click_launcher_includes_deterministic_business_api_lab(self):
        path = Path(__file__).parents[1] / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8").lower()
        compose = (path.parent / "docker-compose.local-labs.yml").read_text(encoding="utf-8").lower()
        self.assertIn("business-api", content)
        self.assertIn("127.0.0.1:8084:8084", compose)
        self.assertIn("业务 api", content)
        self.assertIn("五靶场", content)


if __name__ == "__main__":
    unittest.main()

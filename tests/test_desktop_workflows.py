import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
GUI_SCRIPT = PROJECT_ROOT / "tools" / "src_auto_gui.ps1"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


class DesktopWorkflowContractTests(unittest.TestCase):
    def test_figma_v2_navigation_and_real_handlers_are_present(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for label in (
            "工作台",
            "本地靶场",
            "目标与授权",
            "会话与任务",
            "代理与 API 复核",
            "发现与报告",
            "蓝队被动分析",
            "AI 与工具",
            "审计与设置",
            "立即停止",
        ):
            self.assertIn(label, content)
        for handler in (
            "Show-SessionTaskWindow",
            "Show-ProxyApiReviewWindow",
            "Show-FindingsWindow",
            "Show-DefenseObservationWindow",
            "Open-AISettings",
            "Show-AuditSettingsWindow",
        ):
            self.assertIn("function " + handler, content)
            self.assertIn(handler, content)

    def test_figma_manifest_is_checked_into_project(self):
        manifest = PROJECT_ROOT / "design" / "frontend-mockups" / "2026-08-26-figma-v2" / "manifest.json"
        self.assertTrue(manifest.is_file())
        self.assertIn("manual-confirmation-only", manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

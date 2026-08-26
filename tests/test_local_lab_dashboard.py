import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
GUI_SCRIPT = PROJECT_ROOT / "tools" / "src_auto_gui.ps1"


class LocalLabDashboardContractTests(unittest.TestCase):
    def test_dashboard_includes_fourth_business_api_and_safe_actions(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for text in (
            "business-api",
            "127.0.0.1:8084",
            "启动本地靶场",
            "停止本地靶场",
            "打开回环页面",
            "运行本地验证",
            "状态：",
            "验证进度",
            "不会连接真实目标",
        ):
            self.assertIn(text, content)

    def test_dashboard_actions_are_loopback_orchestration_only(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig").lower()
        self.assertNotIn("--execute-live", content)
        self.assertNotIn("run-live", content)
        self.assertNotIn("invoke-webrequest", content)


if __name__ == "__main__":
    unittest.main()

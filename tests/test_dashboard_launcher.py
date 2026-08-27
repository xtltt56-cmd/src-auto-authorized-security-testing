import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class DashboardLauncherTests(unittest.TestCase):
    def test_dashboard_launcher_is_present_and_loopback_only(self):
        path = PROJECT_ROOT / "tools" / "start_dashboard.ps1"
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("127.0.0.1", content)
        self.assertIn("dashboard", content.lower())
        self.assertIn("node-v22.23.0-win-x64", content)
        self.assertNotIn("0.0.0.0", content)
        self.assertNotIn("https://", content.lower())
        self.assertNotIn("http://", content.lower().replace("http://127.0.0.1", ""))

    def test_dashboard_launcher_does_not_overwrite_runtime_data(self):
        path = PROJECT_ROOT / "tools" / "start_dashboard.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("dist", content.lower())
        self.assertIn("npm", content.lower())
        self.assertNotIn("Remove-Item", content)
        self.assertNotIn("git reset", content.lower())
        self.assertNotIn("config\\secrets", content.lower())

    def test_start_system_has_explicit_dashboard_switch_before_legacy_gui(self):
        path = PROJECT_ROOT / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("[switch]$Dashboard", content)
        self.assertIn("[switch]$LegacyGui", content)
        dashboard_branch = content.index("$Dashboard")
        legacy_branch = content.index("src_auto_gui.ps1")
        self.assertLess(dashboard_branch, legacy_branch)
        self.assertIn("start_dashboard.ps1", content)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


class LauncherTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

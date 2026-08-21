import tempfile
import unittest
from pathlib import Path

from src_auto.controls import BudgetGovernor, DiskGuard, StopController


class ControlsTests(unittest.TestCase):
    def test_budget_governor_enforces_daily_and_monthly_limits(self):
        budget = BudgetGovernor(monthly_limit=10.0, daily_limit=4.0)
        self.assertTrue(budget.can_spend(4.0))
        budget.record(3.5, "triage")
        self.assertFalse(budget.can_spend(1.0))
        self.assertEqual(budget.status()["spent"], 3.5)

    def test_disk_guard_warns_then_blocks(self):
        values = iter([79.0, 85.0, 91.0])
        guard = DiskGuard("D:/SRC-Auto", used_gb_fn=lambda _: next(values))
        self.assertTrue(guard.check()["allowed"])
        self.assertTrue(guard.check()["warning"])
        self.assertFalse(guard.check()["allowed"])

    def test_stop_controller_is_manual_and_reversible(self):
        with tempfile.TemporaryDirectory() as temp:
            controller = StopController(Path(temp) / "STOP")
            self.assertFalse(controller.requested())
            controller.request()
            self.assertTrue(controller.requested())
            controller.clear()
            self.assertFalse(controller.requested())


if __name__ == "__main__":
    unittest.main()

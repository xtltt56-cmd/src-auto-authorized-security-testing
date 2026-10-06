import tempfile
import unittest
from pathlib import Path

from src_auto.agent_cloud_budget import DeepSeekAgentBudget
from src_auto.store import Store


CONFIG = {"cloud_enabled": True, "default_provider": "deepseek",
          "peak_input_cny_per_million": 2, "peak_output_cny_per_million": 8}
PROVIDER = {"enabled": True, "manual_only": True, "model": "deepseek-flash",
            "endpoint": "https://api.deepseek.com/chat/completions"}


class AgentCloudBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def budget(self, daily=10, monthly=100):
        return DeepSeekAgentBudget(self.root, CONFIG, PROVIDER,
                                  {"daily_ai_budget_yuan": daily, "monthly_ai_budget_yuan": monthly})

    def test_reservation_survives_restart_and_blocks_before_next_call(self):
        budget = self.budget(daily=.1)
        self.assertAlmostEqual(budget.reserve("test-run"), .064)
        with self.assertRaisesRegex(RuntimeError, "cloud_budget_limit"):
            self.budget(daily=.1).reserve("test-run")
        store = Store(self.root / "data/src_auto.sqlite3")
        try:
            self.assertAlmostEqual(store.spend_summary()["total"], .064)
        finally:
            store.close()

    def test_month_limit_includes_preexisting_project_spend(self):
        store = Store(self.root / "data/src_auto.sqlite3")
        store.record_spend(.05, "existing-project-spend")
        store.close()
        with self.assertRaisesRegex(RuntimeError, "cloud_budget_limit"):
            self.budget(monthly=.1).reserve("test-run")

    def test_unknown_usage_and_prices_fail_conservatively(self):
        budget = self.budget()
        self.assertAlmostEqual(budget.estimate(1000, 100, False), .0028)
        self.assertAlmostEqual(budget.estimate(0, 0, True), .064)
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DeepSeekAgentBudget(self.root, dict(CONFIG, peak_output_cny_per_million=value), PROVIDER, {})
        with self.assertRaises(ValueError):
            DeepSeekAgentBudget(self.root, CONFIG, dict(PROVIDER, model="unpriced-model"), {})

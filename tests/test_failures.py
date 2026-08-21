import tempfile
import unittest
from pathlib import Path

from src_auto.ai import AITriage, ModelRouter
from src_auto.models import ToolResult
from src_auto.controls import BudgetGovernor, ResourceGuard, StopController
from src_auto.pipeline import PipelineRunner
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store


def confirmed_scope():
    return ScopeGuard(
        ScopePolicy.from_mapping(
            {
                "target_id": "local",
                "root_domains": ["localhost"],
                "allowed_hosts": ["localhost"],
                "allowed_ports": [8765],
                "confirmed": True,
                "allow_network_contact": True,
            }
        )
    )


class FailureTests(unittest.TestCase):
    def test_external_run_blocks_unconfirmed_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            candidate = ScopeGuard(
                ScopePolicy.from_mapping({"target_id": "x", "allowed_hosts": ["localhost"], "confirmed": False})
            )
            run_id = store.create_run("x", candidate.policy.digest(), "real")
            result = PipelineRunner(store, candidate, root).run_external(run_id, [])
            self.assertEqual(result["status"], "blocked_scope")
            self.assertEqual(store.get_run(run_id)["status"], "blocked_scope")
            store.close()

    def test_manual_stop_then_resume_local_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            run_id = store.create_run("local", confirmed_scope().policy.digest(), "local")
            stopper = StopController(root / "STOP")
            stopper.request()
            runner = PipelineRunner(store, confirmed_scope(), root, stop_controller=stopper)
            fixture = {"assets": [], "findings": []}
            self.assertEqual(runner.run_local(run_id, fixture)["status"], "stopped")
            stopper.clear()
            self.assertEqual(runner.run_local(run_id, fixture)["status"], "completed")
            store.close()

    def test_resource_gate_pauses_before_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            run_id = store.create_run("local", confirmed_scope().policy.digest(), "local")
            resource = ResourceGuard(metrics_fn=lambda: (95, 21))
            result = PipelineRunner(store, confirmed_scope(), root, resource_guard=resource).run_local(run_id, {"assets": []})
            self.assertEqual(result["status"], "paused_resource")
            store.close()

    def test_ai_budget_gate_falls_back_to_manual_review(self):
        budget = BudgetGovernor(monthly_limit=0, daily_limit=0)
        router = ModelRouter({"lanes": {"primary": {"provider": "remote", "model": "test", "estimated_cost": 1}}})
        triage = AITriage(router, budget)
        result = triage.classify({"severity": "low", "evidence": "observation"})
        self.assertEqual(result["disposition"], "manual_review")
        self.assertEqual(result["reason"], "budget_limit_exceeded")

    def test_invalid_scope_port_is_rejected(self):
        with self.assertRaises(ValueError):
            ScopePolicy.from_mapping({"target_id": "bad", "allowed_ports": [70000]})

    def test_external_sequence_requires_explicit_execute_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            scope = confirmed_scope()
            run_id = store.create_run("local", scope.policy.digest(), "real")
            calls = []

            class FakeAdapter:
                def __init__(self, name):
                    self.name = name

                def run(self, args, scope_guard, target_urls=None):
                    calls.append(self.name)
                    return ToolResult(self.name, "completed", 0)

            adapters = {name: FakeAdapter(name) for name in ["bbot", "subfinder", "httpx", "katana", "nuclei", "zap", "reconftw"]}
            waiting = PipelineRunner(store, scope, root).run_external(run_id, ["http://localhost:8765/"], adapters=adapters)
            self.assertEqual(waiting["status"], "awaiting_adapter")
            self.assertEqual(calls, [])
            result = PipelineRunner(store, scope, root).run_external(
                run_id, ["http://localhost:8765/"], adapters=adapters, execute=True
            )
            self.assertEqual(result["status"], "completed_tools")
            self.assertEqual(calls, ["bbot", "subfinder", "httpx", "katana", "nuclei", "zap", "reconftw"])
            store.close()


if __name__ == "__main__":
    unittest.main()

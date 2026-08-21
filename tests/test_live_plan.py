import tempfile
import unittest
from pathlib import Path

from src_auto.live_plan import LivePlanError, validate_live_plan
from src_auto.models import ToolResult
from src_auto.pipeline import PipelineRunner
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store


class LivePlanTests(unittest.TestCase):
    def test_valid_plan_is_normalized_and_digest_is_stable(self):
        plan = {
            "name": "reviewed-http-observation",
            "operator": "tester",
            "authorization_note": "ticket-123",
            "manual_execution_confirmed": True,
            "target_urls": ["http://localhost:8765/"],
            "sequence": ["httpx", "katana"],
            "commands": {
                "httpx": ["-silent", "-no-color", "-u", "http://localhost:8765/"],
                "katana": ["-silent", "-u", "http://localhost:8765/", "-d", "1"],
            },
        }
        first = validate_live_plan(plan)
        second = validate_live_plan(dict(plan))
        self.assertEqual(first["sequence"], ["httpx", "katana"])
        self.assertEqual(first["plan_digest"], second["plan_digest"])

    def test_plan_requires_manual_identity_and_rejects_shell_or_dangerous_args(self):
        base = {
            "name": "plan",
            "operator": "tester",
            "authorization_note": "ticket-123",
            "manual_execution_confirmed": True,
            "target_urls": ["http://localhost:8765/"],
            "sequence": ["httpx"],
            "commands": {"httpx": ["-u", "http://localhost:8765/"]},
        }
        missing_identity = dict(base)
        missing_identity["operator"] = ""
        with self.assertRaises(LivePlanError):
            validate_live_plan(missing_identity)
        shell = dict(base)
        shell["commands"] = {"httpx": ["-u", "http://localhost:8765/; whoami"]}
        with self.assertRaises(LivePlanError):
            validate_live_plan(shell)
        dangerous = dict(base)
        dangerous["commands"] = {"httpx": ["--dos", "http://localhost:8765/"]}
        with self.assertRaises(LivePlanError):
            validate_live_plan(dangerous)
        unconfirmed = dict(base)
        unconfirmed["manual_execution_confirmed"] = False
        self.assertFalse(validate_live_plan(unconfirmed)["manual_execution_confirmed"])

    def test_external_runner_accepts_only_explicit_plan_sequence_and_args(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            scope = ScopeGuard(
                ScopePolicy.from_mapping(
                    {
                        "target_id": "local",
                        "allowed_hosts": ["localhost"],
                        "allowed_ports": [8765],
                        "confirmed": True,
                        "allow_network_contact": True,
                    }
                )
            )
            run_id = store.create_run("local", scope.policy.digest(), "real")
            calls = []

            class FakeAdapter:
                def __init__(self, name):
                    self.name = name

                def run(self, args, scope_guard, target_urls=None):
                    calls.append((self.name, list(args), list(target_urls or [])))
                    return ToolResult(self.name, "completed", 0)

            adapters = {name: FakeAdapter(name) for name in ["httpx", "katana"]}
            result = PipelineRunner(store, scope, root).run_external(
                run_id,
                ["http://localhost:8765/"],
                adapters=adapters,
                execute=True,
                sequence=["httpx", "katana"],
                tool_args={"httpx": ["-silent"], "katana": ["-d", "1"]},
            )
            self.assertEqual(result["status"], "completed_tools")
            self.assertEqual(calls[0][0:2], ("httpx", ["-silent"]))
            self.assertEqual(calls[1][0:2], ("katana", ["-d", "1"]))
            store.close()

    def test_external_runner_honors_manual_stop_before_starting_a_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite3")
            scope = ScopeGuard(
                ScopePolicy.from_mapping(
                    {
                        "target_id": "local",
                        "allowed_hosts": ["localhost"],
                        "allowed_ports": [8765],
                        "confirmed": True,
                        "allow_network_contact": True,
                    }
                )
            )
            run_id = store.create_run("local", scope.policy.digest(), "real")
            (root / "STOP").write_text("stop requested\n", encoding="utf-8")
            calls = []

            class FakeAdapter:
                def run(self, args, scope_guard, target_urls=None):
                    calls.append(True)
                    return ToolResult("httpx", "completed", 0)

            result = PipelineRunner(store, scope, root).run_external(
                run_id,
                ["http://localhost:8765/"],
                adapters={"httpx": FakeAdapter()},
                execute=True,
                sequence=["httpx"],
            )
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(calls, [])
            store.close()


if __name__ == "__main__":
    unittest.main()

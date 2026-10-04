import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src_auto.agent_service import AgentService
from src_auto.agent_contracts import Limits
from tests.test_agent import FakeActions, ScriptedModel, decision


class Control:
    def __init__(self):
        self._lock = threading.RLock(); self._closing = False
        self.manager = SimpleNamespace(spec=self.spec, status=lambda x: {"status": "READY"})
        self.other_work = False; self.agent = None
    def spec(self, name):
        if name != "business-api": raise ValueError("unknown_lab_id")
        return SimpleNamespace(health_url="http://127.0.0.1:8084/health")
    def lifecycle(self): return {"activeWork": self.other_work or bool(self.agent and self.agent.active)}


class AgentServiceTests(unittest.TestCase):
    def setUp(self):
        resource = patch("src_auto.agent_service.WindowsResources", return_value=SimpleNamespace(check=lambda: {"allowed": True, "known": True}))
        resource.start(); self.addCleanup(resource.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / "config/policy.yaml").write_text("{}", encoding="utf-8")
        self.control = Control(); self.factory_calls = 0
        def factory(*args):
            self.factory_calls += 1
            return ScriptedModel([decision("inspect_headers"), decision("finish", evidence=["o1"])])
        self.service = AgentService(self.root, self.control, model_factory=factory, action_factory=lambda *args, **kwargs: FakeActions())
        self.control.agent = self.service
        self.request = {"labId": "business-api", "mode": "candidate-review", "provider": "local"}
    def tearDown(self):
        self.service.close()
        deadline = time.monotonic() + 3
        while self.service.active and time.monotonic() < deadline: time.sleep(.01)
        self.tmp.cleanup()

    def test_session_starts_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "agent_disabled"): self.service.start(self.request, False)
        self.assertEqual(self.factory_calls, 0)
    def test_cloud_cannot_load_factory_without_both_gates(self):
        self.service.set_enabled(True)
        for remote, allow in ((False, True), (True, False)):
            with self.assertRaises(ValueError): self.service.start(dict(self.request, provider="deepseek", allowCloud=allow), remote)
        self.assertEqual(self.factory_calls, 0)
    def test_cloud_loop_stays_closed_until_cost_controls_are_validated(self):
        self.service.set_enabled(True)
        with self.assertRaisesRegex(ValueError, "cloud_agent_not_validated"):
            self.service.start(dict(self.request, provider="deepseek", allowCloud=True), True)
        self.assertEqual(self.factory_calls, 0)
    def test_extra_command_and_url_rejected(self):
        for key in ("url", "command", "apiKey", "scope"):
            with self.subTest(key=key), self.assertRaises(ValueError): self.service.start(dict(self.request, **{key: "bad"}), False)
    def test_existing_work_blocks_agent(self):
        self.service.set_enabled(True); self.control.other_work = True
        with self.assertRaisesRegex(RuntimeError, "agent_operation_conflict"): self.service.start(self.request, False)
    def test_not_ready_blocks(self):
        self.service.set_enabled(True); self.control.manager.status = lambda x: {"status": "STOPPED"}
        with self.assertRaisesRegex(RuntimeError, "lab_not_ready"): self.service.start(self.request, False)
    def test_unknown_cancel_does_not_modify_history(self):
        with self.assertRaisesRegex(ValueError, "agent_not_running"): self.service.cancel_run("foreign")
        self.assertEqual(self.service.history.list(), [])
    def test_close_rejects_new_work(self):
        self.control._closing = True
        with self.assertRaisesRegex(RuntimeError, "dashboard_closing"): self.service.set_enabled(True)

    def test_other_service_sees_active_owner_and_cannot_start(self):
        self.service.history.create("business-api", "candidate-review", "local", Limits(), FakeActions())
        other = AgentService(self.root, Control(), model_factory=lambda *args: self.fail("must not load model"), action_factory=lambda *args, **kwargs: FakeActions())
        try:
            other.set_enabled(True)
            self.assertTrue(other.active)
            self.assertIsNotNone(other.snapshot(False)["activeId"])
            with self.assertRaisesRegex(RuntimeError, "agent_operation_conflict"): other.start(self.request, False)
        finally:
            other.close()
            row = self.service.history.list()[0]
            self.service.history.update(row["id"], state="cancelled")
    def test_cancel_no_next_tool_after_model_returns(self):
        started, release = threading.Event(), threading.Event()
        class BlockingModel:
            def decide(self, context):
                started.set(); release.wait(3)
                return {"text": decision("inspect_headers"), "input_tokens": 20, "output_tokens": 20}
        self.service.model_factory = lambda *args: BlockingModel()
        self.service.set_enabled(True)
        result = self.service.start(self.request, False)
        self.assertTrue(started.wait(2))
        self.service.cancel_run(result["id"]); release.set()
        deadline = time.monotonic() + 3
        while self.service.active and time.monotonic() < deadline: time.sleep(.01)
        row = self.service.history.get(result["id"])
        self.assertEqual(row["state"], "cancelled")
        self.assertEqual(row["steps"], 0)


if __name__ == "__main__": unittest.main()

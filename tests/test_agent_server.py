import json
import threading
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src_auto.dashboard_server import create_server, build_service
from tests.test_dashboard_server import FakeService


class FakeAgent:
    def __init__(self): self.calls = []
    def snapshot(self, remote): return {"enabled": False, "remoteSessionEnabled": remote, "runs": []}
    def set_enabled(self, enabled): self.calls.append(enabled); return {"enabled": enabled}
    def start(self, document, remote): self.calls.append(document); return {"accepted": True, "id": "test"}


class AgentServerTests(unittest.TestCase):
    def setUp(self):
        service = FakeService(); service.agent = FakeAgent()
        self.agent = service.agent
        self.server = create_server(service, port=0, token="test-token", remote_ai_enabled=False)
        self.thread = threading.Thread(target=self.server.serve_forever); self.thread.start()
        self.url = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.thread.join(5); self.server.server_close()

    def post(self, path, body, authorized=True):
        headers = {"Content-Type": "application/json"}
        if authorized: headers["X-SRC-Auto-Token"] = "test-token"
        return urlopen(Request(self.url + path, data=json.dumps(body).encode(), headers=headers), timeout=3)

    def test_cloud_hard_gate_before_factory(self):
        with self.assertRaises(HTTPError) as error:
            self.post("/api/agent/start", {"labId": "business-api", "mode": "api-permissions", "provider": "deepseek", "allowCloud": True})
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.agent.calls, [])

    def test_auth_and_strict_toggle(self):
        with self.assertRaises(HTTPError) as error: self.post("/api/agent/enable", {"enabled": True}, False)
        self.assertEqual(error.exception.code, 401)
        with self.assertRaises(HTTPError) as error: self.post("/api/agent/enable", {"enabled": "yes"})
        self.assertEqual(error.exception.code, 400)
        with self.post("/api/agent/enable", {"enabled": True}) as result:
            self.assertTrue(json.load(result)["enabled"])

    def test_optional_agent_database_failure_does_not_break_standard_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            database = root / "data/agent.sqlite3"
            database.write_bytes(b"invalid-sqlite-preserve-me")
            manager = SimpleNamespace(project_root=root, specs={"business-api": SimpleNamespace()})
            with patch("src_auto.dashboard_server.LocalLabManager", return_value=manager):
                service = build_service(root, port=49000)
            try:
                self.assertIsNone(service.agent)
                self.assertEqual(service.agent_error, "agent_state_unavailable")
                self.assertFalse(service.lifecycle()["activeWork"])
                self.assertEqual(database.read_bytes(), b"invalid-sqlite-preserve-me")
            finally: service.close()


if __name__ == "__main__": unittest.main()

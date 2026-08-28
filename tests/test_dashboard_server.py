import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src_auto.dashboard_server import create_server


class FakeService:
    lab_ids = ("juice-shop", "dvwa")

    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"source": "loopback", "dependency": {"dockerReady": True}, "tasks": [], "labs": [], "events": [], "findings": [], "reports": []}

    def submit(self, lab_id, action):
        if lab_id not in self.lab_ids:
            raise ValueError("unknown_lab_id")
        self.calls.append((lab_id, action))
        return {"accepted": True, "labId": lab_id, "action": action}

    def submit_all(self, action):
        self.calls.append(("all", action))
        return {"accepted": True, "action": action}


class DashboardServerTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.server = create_server(self.service, port=0, token="test-session-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, method="GET", token=None, origin=None, body=None):
        headers = {}
        if token:
            headers["X-SRC-Auto-Token"] = token
        if origin:
            headers["Origin"] = origin
        data = None if body is None else json.dumps(body).encode("utf-8")
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, dict(exc.headers), json.loads(exc.read().decode("utf-8"))

    def test_server_binds_only_loopback_and_health_is_public(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, headers, payload = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("test-session-token", json.dumps(payload))

    def test_session_is_available_same_origin_and_cors_is_exact(self):
        status, headers, payload = self.request("/api/session", origin="http://127.0.0.1:4173")
        self.assertEqual(status, 200)
        self.assertEqual(payload["token"], "test-session-token")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://127.0.0.1:4173")
        status, _, payload = self.request("/api/session", origin="https://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "origin_not_allowed")

    def test_dashboard_and_actions_require_session_token(self):
        status, _, payload = self.request("/api/dashboard")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "invalid_session_token")
        status, _, payload = self.request("/api/dashboard", token="test-session-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "loopback")
        status, _, payload = self.request("/api/labs/dvwa/start", method="POST", token="test-session-token", body={})
        self.assertEqual(status, 202)
        self.assertTrue(payload["accepted"])
        self.assertEqual(self.service.calls, [("dvwa", "start")])

    def test_unknown_route_and_lab_fail_closed(self):
        status, _, payload = self.request("/api/labs/not-known/start", method="POST", token="test-session-token", body={})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "unknown_lab_id")
        status, _, payload = self.request("/api/labs/dvwa/shell", method="POST", token="test-session-token", body={})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "route_not_found")

    def test_rejects_oversized_or_non_json_post_body(self):
        request = Request(
            self.base + "/api/labs/dvwa/start",
            data=b"x" * 2049,
            headers={"X-SRC-Auto-Token": "test-session-token", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 413)


if __name__ == "__main__":
    unittest.main()

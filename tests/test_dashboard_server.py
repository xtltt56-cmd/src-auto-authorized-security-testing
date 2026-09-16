import json
import threading
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src_auto.dashboard_server import create_server, open_ai_provider_settings, start_docker_desktop
from src_auto.dashboard_workspace import DashboardWorkspace


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

    def submit_detection(self, lab_id):
        if lab_id not in self.lab_ids:
            raise ValueError("unknown_lab_id")
        self.calls.append((lab_id, "detect"))
        return {"accepted": True, "labId": lab_id, "action": "detect"}

    def cancel_detection(self, lab_id):
        if lab_id not in self.lab_ids:
            raise ValueError("unknown_lab_id")
        self.calls.append((lab_id, "detect-stop"))
        return {"accepted": True, "labId": lab_id, "action": "detect-stop"}


class FakeProviderSettings:
    def __init__(self): self.calls = []
    def public_status(self):
        return {'providers': [{'id': 'deepseek', 'displayName': 'DeepSeek V4.1 Flash',
                               'model': 'deepseek-flash', 'officialModel': 'deepseek-flash',
                               'keySaved': False, 'endpointHost': 'api.deepseek.com'}]}
    def save(self, provider, api_key, model):
        self.calls.append(('save', provider, api_key, model))
        return {'id': provider, 'model': model, 'keySaved': bool(api_key)}
    def test_connection(self, provider):
        self.calls.append(('test', provider))
        return {'ok': True, 'code': 'reachable_model_available'}


class DashboardServerTests(unittest.TestCase):
    def test_draft_api_persists_and_requires_authentication(self):
        from tests.test_dashboard_workspace import draft
        with tempfile.TemporaryDirectory() as temp:
            self.server.workspace = DashboardWorkspace(Path(temp))
            self.assertEqual(self.request('/api/drafts', method='POST', body=draft())[0], 401)
            status, _, result = self.request('/api/drafts', method='POST', token='test-session-token', body=draft())
            self.assertEqual(status, 201)
            self.server.workspace = DashboardWorkspace(Path(temp))
            status, _, loaded = self.request('/api/drafts', token='test-session-token')
            self.assertEqual(status, 200)
            self.assertEqual(loaded['drafts'][0]['id'], result['id'])
            self.assertEqual(self.request('/api/review', token='test-session-token')[2]['entries'][0]['status'], 'candidate_only')
            self.assertEqual(self.request('/api/artifacts')[0], 401)

    def test_full_report_download_requires_authentication_and_uses_a_safe_report_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'reports').mkdir()
            marker = 'FULL-CONTENT-AFTER-PREVIEW'
            (root / 'reports' / 'long.md').write_text('x' * 70000 + marker, encoding='utf-8')
            self.server.workspace = DashboardWorkspace(root)
            report_id = quote('reports/long.md', safe='')

            self.assertEqual(self.request('/api/reports/' + report_id)[0], 401)
            status, _, payload = self.request('/api/reports/' + report_id, token='test-session-token')
            self.assertEqual(status, 200)
            self.assertIn(marker, payload['content'])
            self.assertEqual(self.request('/api/reports/' + quote('../private.txt', safe=''), token='test-session-token')[0], 400)

    def test_artifact_summary_requires_authentication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'reports').mkdir()
            (root / 'reports' / 'one.md').write_text('one', encoding='utf-8')
            self.server.workspace = DashboardWorkspace(root)
            self.assertEqual(self.request('/api/artifacts/summary')[0], 401)
            status, _, payload = self.request('/api/artifacts/summary', token='test-session-token')
            self.assertEqual(status, 200)
            self.assertEqual(payload, {'candidateCount': 0, 'reportCount': 1})

    def test_native_dialog_uses_windows_powershell_module_path(self):
        with patch('src_auto.dashboard_server._settings_process', None), patch('src_auto.dashboard_server.subprocess.Popen') as launch:
            launch.return_value.wait.side_effect = __import__('subprocess').TimeoutExpired('dialog', 1)
            open_ai_provider_settings()
            environment = launch.call_args.kwargs['env']
            entries = [v for k, v in environment.items() if k.lower() == 'psmodulepath']
            self.assertEqual(len(entries), 1)
            self.assertIn('WindowsPowerShell', entries[0])
            self.assertNotIn('PowerShell\\7', entries[0])

    def test_inline_ai_settings_requires_token_saves_and_tests_without_returning_secret(self):
        self.server.provider_settings = FakeProviderSettings()
        self.assertEqual(self.request('/api/settings/providers')[0], 401)
        status, _, listed = self.request('/api/settings/providers', token='test-session-token')
        self.assertEqual(status, 200)
        self.assertNotIn('apiKey', json.dumps(listed))
        self.assertTrue(listed['providers'][0]['sessionEnabled'])
        status, _, saved = self.request('/api/settings/providers/deepseek', method='POST', token='test-session-token',
                                        body={'apiKey': 'synthetic-key', 'model': 'deepseek-flash'})
        self.assertEqual(status, 200)
        self.assertNotIn('synthetic-key', json.dumps(saved))
        status, _, tested = self.request('/api/settings/providers/deepseek/test', method='POST', token='test-session-token',
                                         body={'allowNetwork': True})
        self.assertEqual(status, 200)
        self.assertTrue(tested['ok'])
        self.assertEqual(self.server.provider_settings.calls,
                         [('save', 'deepseek', 'synthetic-key', 'deepseek-flash'), ('test', 'deepseek')])

    def test_inline_ai_test_requires_explicit_network_flag(self):
        self.server.provider_settings = FakeProviderSettings()
        status, _, payload = self.request('/api/settings/providers/deepseek/test', method='POST',
                                          token='test-session-token', body={})
        self.assertEqual(status, 400)
        self.assertEqual(payload['error'], 'network_consent_required')

    def test_inline_ai_test_is_hard_blocked_when_session_denied_remote_ai(self):
        self.server.provider_settings = FakeProviderSettings()
        self.server.remote_ai_session_enabled = False
        status, _, payload = self.request('/api/settings/providers/deepseek/test', method='POST',
                                          token='test-session-token', body={'allowNetwork': True})
        self.assertEqual(status, 403)
        self.assertEqual(payload['error'], 'remote_ai_disabled_for_session')
        self.assertEqual(self.server.provider_settings.calls, [])

    def test_docker_desktop_start_requires_token_and_has_no_user_path(self):
        with patch('src_auto.dashboard_server.start_docker_desktop', create=True) as launch:
            self.assertEqual(self.request('/api/dependencies/docker/start', method='POST', body={})[0], 401)
            self.assertEqual(self.request('/api/dependencies/docker/start', method='POST', token='test-session-token', body={'path': 'bad'})[0], 400)
            self.assertEqual(self.request('/api/dependencies/docker/start', method='POST', token='test-session-token', body={})[0], 202)
            launch.assert_called_once_with()

    def setUp(self):
        self.service = FakeService()
        # Tests which exercise the explicit connection checkbox run in an
        # explicitly enabled synthetic session; production defaults to denied.
        self.server = create_server(self.service, port=0, token="test-session-token", remote_ai_enabled=True)
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
            with urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, dict(exc.headers), json.loads(exc.read().decode("utf-8"))

    def test_server_binds_only_loopback_and_health_is_public(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, headers, payload = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "src-auto-dashboard-api")
        self.assertTrue(payload["loopbackOnly"])
        self.assertTrue(payload["remoteAiSessionEnabled"])
        self.assertGreater(payload["processId"], 0)
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

    def test_detection_routes_require_token_and_accept_only_fixed_local_labs(self):
        self.assertEqual(self.request("/api/labs/juice-shop/detect", method="POST", body={})[0], 401)
        status, _, payload = self.request(
            "/api/labs/juice-shop/detect", method="POST", token="test-session-token", body={}
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["action"], "detect")
        status, _, payload = self.request(
            "/api/labs/juice-shop/detect-stop", method="POST", token="test-session-token", body={}
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["action"], "detect-stop")
        self.assertEqual(self.service.calls, [("juice-shop", "detect"), ("juice-shop", "detect-stop")])
        status, _, payload = self.request(
            "/api/labs/not-known/detect", method="POST", token="test-session-token", body={}
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "unknown_lab_id")

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
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 413)


if __name__ == "__main__":
    unittest.main()

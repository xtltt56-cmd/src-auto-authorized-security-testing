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
        self.active = False

    def lifecycle(self):
        return {'activeWork': self.active, 'closing': False}

    def prepare_shutdown(self):
        return not self.active

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
    def test_expired_local_window_has_a_specific_public_error(self):
        from types import SimpleNamespace
        def expired(*args): raise ValueError('outside_test_window')
        self.service.agent = SimpleNamespace(local_app=SimpleNamespace(preview=expired))
        status, _, payload = self.request('/api/local-app/preview', method='POST', token='test-session-token', body={})
        self.assertEqual(status, 400)
        self.assertEqual(payload['error'], 'outside_test_window')

    def test_new_source_and_target_operations_require_session_before_body(self):
        for path in ('/api/source-audit/preview', '/api/source-audit/start', '/api/local-targets/save', '/api/local-targets/delete'):
            self.assertEqual(self.request(path, method='POST', body={})[0], 401)
        self.assertEqual(self.request('/api/local-targets')[0], 401)

    def test_business_execution_auth_and_disabled_cloud_error_are_fail_closed(self):
        from types import SimpleNamespace
        def denied(*args): raise ValueError('remote_ai_disabled_for_session')
        self.service.agent = SimpleNamespace(business=SimpleNamespace(preview=denied, start=denied))
        for action in ('preview', 'start'):
            path = '/api/business/' + action
            self.assertEqual(self.request(path, method='POST', body={})[0], 401)
            status, _, value = self.request(path, method='POST', token='test-session-token', body={})
            self.assertEqual(status, 403)
            self.assertEqual(value['error'], 'remote_ai_disabled_for_session')

    def test_business_execution_does_not_echo_unexpected_exception(self):
        from types import SimpleNamespace
        def failed(*args): raise RuntimeError('Bearer PRIVATE_TEST_SECRET')
        self.service.agent = SimpleNamespace(business=SimpleNamespace(preview=failed))
        status, _, value = self.request('/api/business/preview', method='POST', token='test-session-token', body={})
        self.assertEqual(status, 409)
        self.assertNotIn('PRIVATE_TEST_SECRET', json.dumps(value))

    def test_business_preparation_endpoints_require_session_and_cannot_execute(self):
        self.assertEqual(self.request('/api/business-preparation')[0], 401)
        for action in ('save', 'preview', 'delete', 'session-save', 'session-delete'):
            self.assertEqual(self.request('/api/business-preparation/' + action, method='POST', body={})[0], 401)
        self.assertEqual(self.request('/api/business-preparation/start', method='POST', token='test-session-token', body={})[0], 404)

    def test_business_preparation_http_round_trip_does_not_echo_credentials(self):
        from datetime import datetime, timedelta, timezone
        from src_auto.business_preparation import BusinessPreparation
        with tempfile.TemporaryDirectory(dir=str(Path(__file__).parents[1] / 'validation')) as temp:
            preparation = BusinessPreparation(Path(temp))
            self.server.business_preparation = preparation
            target = preparation.targets.save(dict(name='HTTP 合成隔离目标', kind='custom_lab', origin='http://127.0.0.1:8765',
                paths=['/objects/a'], excluded=['/reset'], method='GET', profile='readonly-baseline-v1'))
            session = dict(targetId=target['id'], targetRevision=target['revision'], name='isolated-a', role='account-a',
                headers={'Authorization': 'Bearer SYNTHETIC_HTTP_PRIVATE'}, confirmTestAccount=True,
                expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())
            status, _, saved = self.request('/api/business-preparation/session-save', method='POST', token='test-session-token', body=session)
            self.assertEqual(status, 200)
            self.assertNotIn('SYNTHETIC_HTTP_PRIVATE', json.dumps(saved))
            status, _, snapshot = self.request('/api/business-preparation', token='test-session-token')
            self.assertEqual(status, 200)
            self.assertEqual(snapshot['sessions'][0]['targetId'], target['id'])
            self.assertFalse(snapshot['executionAvailable'])
            self.assertNotIn('SYNTHETIC_HTTP_PRIVATE', json.dumps(snapshot))
            self.assertEqual(self.service.calls, [])
            session['headers'] = {'Host': 'SYNTHETIC_HTTP_PRIVATE'}
            status, _, rejected = self.request('/api/business-preparation/session-save', method='POST', token='test-session-token', body=session)
            self.assertEqual(status, 400)
            self.assertNotIn('SYNTHETIC_HTTP_PRIVATE', json.dumps(rejected))

    def test_business_preparation_failure_is_sanitized(self):
        with patch.object(self.server.business_preparation, 'save_session', side_effect=RuntimeError('SYNTHETIC_SECRET')):
            status, _, payload = self.request('/api/business-preparation/session-save', method='POST', token='test-session-token', body={})
        self.assertEqual(status, 503)
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(payload))

    def test_rejected_slow_post_does_not_wait_for_declared_body(self):
        import http.client
        import time
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=2)
        try:
            connection.putrequest('POST', '/api/local-app/preview')
            connection.putheader('Content-Length', '5000')
            connection.endheaders()
            started = time.monotonic()
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            self.assertEqual(json.loads(response.read())['error'], 'invalid_session_token')
            self.assertLess(time.monotonic() - started, 1)
        finally:
            connection.close()

    def test_rejected_post_discards_only_bounded_unread_bytes(self):
        import io
        from email.message import Message
        from unittest.mock import Mock
        from src_auto.dashboard_server import DashboardRequestHandler
        handler = object.__new__(DashboardRequestHandler)
        handler.headers = Message()
        handler.headers['Content-Length'] = '1000000'
        handler.rfile = io.BytesIO(b'x' * 1000000)
        handler.connection = Mock()
        handler.connection.gettimeout.return_value = None
        handler._discard_unread_body()
        self.assertEqual(handler.rfile.tell(), 65536)
        handler.connection.settimeout.assert_called_with(None)
        handler._body_read = True
        handler._discard_unread_body()
        self.assertEqual(handler.rfile.tell(), 65536)

    def test_local_application_routes_are_authenticated_and_session_gated(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        local_app = SimpleNamespace(preview=Mock(return_value={'networkContact': False}),
                                    start=Mock(return_value={'accepted': True, 'id': 'local-one'}))
        self.service.agent = SimpleNamespace(local_app=local_app)
        self.assertEqual(self.request('/api/local-app/preview', method='POST', body={})[0], 401)
        self.assertEqual(self.request('/api/local-app/preview', method='POST', body={}, token='test-session-token')[0], 200)
        local_app.preview.assert_called_once_with({}, True)
        self.assertEqual(self.request('/api/local-app/start', method='POST', body={'approvalId': 'one', 'confirmStart': True}, token='test-session-token')[0], 202)
        local_app.start.assert_called_once_with({'approvalId': 'one', 'confirmStart': True}, True)
        local_app.preview.side_effect = ValueError('remote_ai_disabled_for_session')
        self.assertEqual(self.request('/api/local-app/preview', method='POST', body={}, token='test-session-token')[0], 403)
        local_app.start.side_effect = OSError('PRIVATE-DATA')
        status, _, payload = self.request('/api/local-app/start', method='POST', body={}, token='test-session-token')
        self.assertEqual(status, 503)
        self.assertNotIn('PRIVATE-DATA', json.dumps(payload))

    def test_shutdown_is_authenticated_and_rejects_active_work(self):
        self.assertEqual(self.request('/api/lifecycle')[0], 401)
        self.assertEqual(self.request('/api/shutdown', method='POST', body={})[0], 401)
        self.service.active = True
        self.assertEqual(self.request('/api/shutdown', method='POST', token='test-session-token', body={})[0], 409)
        self.assertEqual(self.request('/api/shutdown', method='POST', token='test-session-token', body={'force': True})[0], 400)

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
        self.assertEqual(payload['serviceApiVersion'], 3)
        self.assertIn('business-preparation-v1', payload['capabilities'])
        self.assertRegex(payload['pythonVersion'], r'^3\.[0-9]+\.[0-9]+$')
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

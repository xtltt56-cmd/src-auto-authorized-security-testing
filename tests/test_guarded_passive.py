"""Regression contracts: no scanner egress, no private HAR data, real bounded HTTP."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src_auto.guarded_passive import (PassiveCapture, offline_plan, normalize_alerts,
                                     ZapOfflineScanner, ManagedProcess)
from src_auto.local_application import LocalApplicationError
from src_auto.scope import ScopePolicy
from tests import test_local_application as fixture


class PassiveContracts(unittest.TestCase):
    def test_oversized_har_does_not_leave_a_task_directory(self):
        with tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation')) as folder:
            root = Path(folder)
            scanner = ZapOfflineScanner(root, threading.Event(), lambda: '')
            self.capture.limit = 1
            with patch.object(scanner, 'prepare'), self.assertRaisesRegex(LocalApplicationError, 'output_limit'):
                scanner.run(self.scope, self.capture, 10)
            self.assertEqual(list(root.rglob('src-auto-passive-*')), [])

    def test_present_sanitized_headers_are_not_reported_missing(self):
        alerts = {'site': [{'alerts': [{'pluginid': '10038', 'instances': [
            {'uri': self.scope.local_web.origin + '/', 'method': 'GET'}]}]}]}
        result = normalize_alerts(alerts, self.scope, {('/', 'GET'): {'content-security-policy'}})
        self.assertEqual(result, [])

    def setUp(self):
        self.fixture = fixture.LocalApplicationHTTPTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.scope = ScopePolicy.from_mapping(self.fixture.document)
        self.capture = PassiveCapture(self.scope)

    def test_capture_drops_body_cookie_and_unreviewed_values_before_storage(self):
        result = self.capture.record(self.scope.local_web.origin + '/', 'GET', 200,
            [('Content-Type', 'text/html; charset=utf-8'), ('Set-Cookie', 'sid=PRIVATE_TOKEN'),
             ('X-Private', 'PRIVATE_TOKEN'), ('Content-Security-Policy', "nonce-PRIVATE_TOKEN")],
            b'<a href="/api/health">PRIVATE_TOKEN</a><input value="PRIVATE_TOKEN">', False)
        har = self.capture.har()
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(har))
        self.assertEqual(har['log']['entries'][0]['response']['content']['text'], '')
        self.assertEqual(result['discovery']['approved_paths'], ['/api/health'])
        self.assertEqual(har['log']['entries'][0]['response']['headers'][-1]['value'], '[value-not-retained]')

    def test_link_discovery_does_not_grant_scope_or_follow_sensitive_links(self):
        result = self.capture.record(self.scope.local_web.origin + '/', 'GET', 200,
            [('Content-Type', 'text/html')], b'''<a href="/api/health">ok</a>
            <a href="/api/reset">no</a><a href="https://other.test/private?token=PRIVATE_TOKEN">no</a>
            <a href="/api/%68ealth">no</a><a href="/api/../api/health">no</a>
            <a href="/api/health?key=PRIVATE_TOKEN">no</a><script src="/api/health"></script>''', False)
        rendered = json.dumps(result)
        self.assertEqual(result['discovery']['approved_paths'], ['/api/health'])
        self.assertEqual(sum(result['discovery']['blocked_counts'].values()), 5)
        self.assertNotIn('PRIVATE_TOKEN', rendered)
        self.assertNotIn('other.test', rendered)
        self.assertEqual(self.fixture.received, [])

    def test_har_quota_is_aggregate_and_truncation_is_explicit(self):
        self.capture.record(self.scope.local_web.origin + '/', 'GET', 200, [], b'x', True)
        self.assertTrue(self.capture.coverage()['truncated_responses'])
        self.capture.limit = 1
        with self.assertRaisesRegex(LocalApplicationError, 'output_limit'):
            self.capture.record(self.scope.local_web.origin + '/api/health', 'GET', 200, [], b'', False)

    def test_passive_plan_contains_no_network_jobs_or_request_replay(self):
        plan = offline_plan(self.scope)
        self.assertEqual([x['type'] for x in plan['jobs']], ['passiveScan-config', 'import', 'passiveScan-wait', 'report'])
        self.assertEqual(plan['jobs'][1]['parameters'], {'type': 'har', 'fileName': '/input/input.har'})
        self.assertEqual(plan['jobs'][2]['parameters']['maxDuration'], 1)
        self.assertTrue(plan['jobs'][0]['parameters']['disableAllRules'])

    def test_alerts_are_scope_checked_deduplicated_and_not_confirmed(self):
        url = self.scope.local_web.origin + '/'
        alerts = {'site': [{'alerts': [
            {'pluginid': '10020', 'riskcode': '2', 'alert': 'PRIVATE_TOKEN',
             'instances': [{'uri': url, 'method': 'GET', 'evidence': 'PRIVATE_TOKEN'}, {'uri': url, 'method': 'GET'}]},
            {'pluginid': '10020', 'instances': [{'uri': url + '?secret=PRIVATE_TOKEN', 'method': 'GET'}]},
            {'pluginid': '40018', 'instances': [{'uri': url, 'method': 'GET'}]},
        ]}]}
        result = normalize_alerts(alerts, self.scope, {('/', 'GET')})
        self.assertEqual(len(result), 1)
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(result))
        self.assertFalse(result[0]['confirmed'])
        self.assertEqual(result[0]['category'], 'configuration-advisory')

    def test_container_command_has_no_ports_host_mapping_docker_socket_or_auto_pull(self):
        with tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation')) as tmp:
            scanner = ZapOfflineScanner(Path(tmp), threading.Event(), lambda: '')
            scanner.image = 'ghcr.io/zaproxy/zaproxy@sha256:' + 'a' * 64
            scanner.docker = 'C:/trusted/docker.exe'
            args = scanner.command(Path(tmp), 'src-auto-passive-' + 'b' * 32)
            for flag in ('--network', '--pull', '--cap-drop', '--read-only', '--memory', '--cpus', '--pids-limit'):
                self.assertIn(flag, args)
            self.assertEqual(args[args.index('--network') + 1], 'none')
            self.assertEqual(args[args.index('--pull') + 1], 'never')
            self.assertFalse(any(x in args for x in ('-p', '--publish', '--privileged', '--add-host')))
            self.assertNotIn('docker.sock', ' '.join(args))


class ProcessContracts(unittest.TestCase):
    def test_cancel_timeout_output_limits_reap_owned_process(self):
        import sys
        for code, limit, expected in [('import time;time.sleep(10)', 1, 'tool_timeout'),
                                       ('print("x"*10000)', 500, 'tool_output_limit')]:
            process = ManagedProcess(threading.Event(), lambda: '')
            with self.assertRaisesRegex(LocalApplicationError, expected):
                process.run([sys.executable, '-c', code], timeout=limit if expected == 'tool_timeout' else 3,
                            output_limit=limit if expected == 'tool_output_limit' else 1000)
            self.assertIsNotNone(process.last_process.poll())

    def test_cancel_before_spawn_does_not_launch(self):
        cancel = threading.Event()
        cancel.set()
        with patch('subprocess.Popen') as popen, self.assertRaisesRegex(LocalApplicationError, 'cancelled'):
            ManagedProcess(cancel, lambda: '').run(['never-run'], timeout=1, output_limit=100)
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()

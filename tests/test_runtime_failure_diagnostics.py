"""Regression for unavailable dependencies and safe model-failure metadata."""
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src_auto.agent_runner import AgentHistory, AgentRunner
from src_auto.dashboard_control import DashboardControlService, docker_dependency_status
from src_auto.local_labs import LocalLabManager
from src_auto.remote_ai import DeepSeekProvider, RemoteProviderError
from tests.test_agent import FakeActions, ScriptedModel, decision

ROOT = Path(__file__).resolve().parents[1]


class RuntimeFailureTests(unittest.TestCase):
    def manager(self):
        return LocalLabManager(ROOT, ROOT / 'config/labs/local_labs.json', ROOT / 'docker-compose.local-labs.yml')

    def test_engine_error_is_not_container_not_found(self):
        result = SimpleNamespace(returncode=1, stdout='', stderr='error during connect: engine unavailable')
        with patch('src_auto.local_labs.subprocess.run', return_value=result):
            value = self.manager().status('juice-shop')
        self.assertEqual(value['health'], 'unavailable')
        self.assertNotEqual(value['status'], 'NOT_FOUND')

    def test_invalid_metadata_is_not_container_not_found(self):
        with patch('src_auto.local_labs.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='{broken', stderr='')):
            self.assertEqual(self.manager().status('juice-shop')['health'], 'unavailable')

    def test_five_lab_probe_has_one_timeout_not_five(self):
        with patch('src_auto.local_labs.subprocess.run', side_effect=subprocess.TimeoutExpired('docker', 3)) as run:
            values = self.manager().statuses()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(values), 5)
        self.assertTrue(all(row['health'] == 'unavailable' for row in values))

    def test_partial_batch_keeps_exact_missing_and_real_healthy(self):
        value = SimpleNamespace(returncode=1, stdout=json.dumps({'Name': '/src-auto-dvwa', 'State': 'running', 'Health': 'healthy'}),
                                stderr='Error: No such container: src-auto-juice-shop\n')
        with patch('src_auto.local_labs.subprocess.run', return_value=value):
            rows = {x['lab_id']: x for x in self.manager().statuses()}
        self.assertEqual(rows['dvwa']['status'], 'READY')
        self.assertEqual(rows['juice-shop']['status'], 'NOT_FOUND')
        self.assertEqual(rows['webgoat']['health'], 'unavailable')

    def test_dashboard_uses_one_batch_and_never_reports_unreadable_as_stopped(self):
        manager = self.manager()
        raw = [dict(lab_id=spec.lab_id, status='NOT_READY', health='unavailable') for spec in manager.specs.values()]
        with patch.object(manager, 'statuses', return_value=raw) as batch, patch.object(manager, 'status', side_effect=AssertionError('no serial probes')):
            service = DashboardControlService(manager, dependency_check=lambda: (True, 'OK'))
            try: value = service.snapshot()
            finally: service.close()
        batch.assert_called_once()
        self.assertTrue(all(row['health'] == 'unavailable' for row in value['labs']))
        self.assertTrue(all('未判断为已删除' in row['stage'] for row in value['labs']))

    def test_dependency_probe_keeps_metadata_timeout_at_three_seconds(self):
        with patch('src_auto.dashboard_control.subprocess.run', side_effect=subprocess.TimeoutExpired('docker', 3)) as call:
            self.assertFalse(docker_dependency_status()[0])
        self.assertEqual(call.call_args.kwargs['timeout'], 3)

    def test_foreign_or_duplicate_metadata_cannot_grant_ready(self):
        for names in (['/foreign'], ['/src-auto-dvwa', '/src-auto-dvwa']):
            output = '\n'.join(json.dumps(dict(Name=name, State='running', Health='healthy')) for name in names)
            with patch('src_auto.local_labs.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=output, stderr='')):
                self.assertFalse(any(x['status'] == 'READY' for x in self.manager().statuses()))

    def test_model_failure_classification_never_retains_exception_text_or_retries(self):
        expected = {'remote_http_401': 'model_auth_failed', 'remote_http_429': 'model_rate_limited',
                    'remote_request_failed': 'model_transport_failed', 'model_input_limit': 'model_input_limit',
                    'invalid_model_usage': 'model_usage_invalid', 'PRIVATE_KEY_MUST_NOT_PERSIST': 'model_unavailable'}
        for error, code in expected.items():
            with self.subTest(error=error), tempfile.TemporaryDirectory(dir=str(ROOT / 'validation')) as temp:
                calls = []
                def fail(context):
                    calls.append(1)
                    raise RuntimeError(error)
                root = Path(temp)
                row = AgentRunner(root, AgentHistory(root), SimpleNamespace(decide=fail), FakeActions(),
                                  resource_check=lambda: {'allowed': True}).run('juice-shop', 'candidate-review', threading.Event())
                self.assertEqual((row['state'], row['reason']), ('paused', 'model_unavailable'))
                self.assertEqual(row['modelFailure']['code'], code)
                self.assertFalse(row['modelFailure']['automaticRetry'])
                self.assertEqual((len(calls), row['requests'], row['steps']), (1, 0, 0))
                retained = json.dumps(row) + (root / row['reportId']).read_text(encoding='utf-8')
                self.assertNotIn('PRIVATE_KEY_MUST_NOT_PERSIST', retained)
                self.assertIn('modelFailure', retained)

    def test_cloud_response_read_is_bounded(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        amounts = []
        class HugeResponse(Response):
            def read(self, size=-1):
                amounts.append(size)
                return super().read(size)
        provider = DeepSeekProvider(endpoint='https://api.deepseek.com/chat/completions', model='deepseek-flash',
            key_env='SYNTHETIC_BOUNDED_KEY', allow_remote_llm=True, urlopen_fn=lambda *a, **k: HugeResponse(b'x' * 300000))
        with patch.dict(os.environ, {'SYNTHETIC_BOUNDED_KEY': 'synthetic-key', 'SRC_AUTO_DEEPSEEK_CONSENT': 'yes', 'SRC_AUTO_REMOTE_AI_CONSENT': 'yes'}):
            with self.assertRaisesRegex(RemoteProviderError, 'remote_response_too_large'):
                provider._post({})
        self.assertEqual(amounts, [262145])

    def test_manual_resume_clears_current_failure_but_keeps_safe_trace(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT / 'validation')) as temp:
            root = Path(temp)
            history = AgentHistory(root)
            def fail(context): raise RuntimeError('remote_http_401')
            first = AgentRunner(root, history, SimpleNamespace(decide=fail), FakeActions(),
                resource_check=lambda: {'allowed': True}).run('juice-shop', 'candidate-review', threading.Event())
            model = ScriptedModel([decision('inspect_headers'), decision('finish', evidence=['o1'])])
            second = AgentRunner(root, history, model, FakeActions(), resource_check=lambda: {'allowed': True}).run(
                'juice-shop', 'candidate-review', threading.Event(), resume_id=first['id'])
            self.assertEqual(second['state'], 'completed')
            self.assertIsNone(second.get('modelFailure'))
            self.assertEqual(second['trace'][0]['reason'], 'model_auth_failed')
            self.assertEqual(second['trace'][0]['result'], 'model-failed')

    def test_stop_during_failed_model_call_remains_cancelled_not_resumable(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT / 'validation')) as temp:
            root = Path(temp)
            cancel = threading.Event()
            def fail(context):
                cancel.set()
                raise RuntimeError('remote_request_failed')
            row = AgentRunner(root, AgentHistory(root), SimpleNamespace(decide=fail), FakeActions(),
                resource_check=lambda: {'allowed': True}).run('juice-shop', 'candidate-review', cancel)
            self.assertEqual((row['state'], row['reason'], row['modelCalls'], row['requests']),
                             ('cancelled', 'operator_stop', 1, 0))

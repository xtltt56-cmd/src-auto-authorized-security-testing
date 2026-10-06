import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_local_application as fixture
from tests.test_agent import ScriptedModel, decision
from tests.test_agent_service import Control
from src_auto.agent_service import AgentService


class LocalApplicationWorkflowTests(unittest.TestCase):
    def test_arbitrary_tool_exception_text_is_not_persisted(self):
        self.service.set_enabled(True)
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
        with patch('src_auto.local_application_workflow.LocalWebActions.execute', side_effect=RuntimeError('PRIVATE_TOOL_STDERR')):
            row = self.wait_run(self.service.local_app.start(dict(approvalId=preview['approvalId'], confirmStart=True), False)['id'])
        self.assertEqual(row['reason'], 'tool_failed')
        self.assertNotIn('PRIVATE_TOOL_STDERR', json.dumps(row))
        self.assertNotIn('PRIVATE_TOOL_STDERR', (self.root / row['reportId']).read_text(encoding='utf-8'))

    def test_agent_tool_resource_denial_is_not_hidden_as_generic_tool_failure(self):
        from src_auto.local_application import LocalApplicationError
        self.service.set_enabled(True)
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
        with patch('src_auto.local_application_workflow.LocalWebActions.execute', side_effect=LocalApplicationError('resource_limit')):
            row = self.wait_run(self.service.local_app.start(dict(approvalId=preview['approvalId'], confirmStart=True), False)['id'])
        self.assertEqual(row['reason'], 'resource_limit')
        self.assertEqual(row['trace'][-1]['reason'], 'resource_limit')
        self.assertEqual(self.fixture.received, [])

    def test_agent_resource_denial_records_the_actual_failed_sample(self):
        self.service.set_enabled(True)
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
        denied = {'allowed': False, 'known': True, 'cpu_percent': 89.0, 'memory_gb': 22.0}
        with patch('src_auto.local_application_workflow.WindowsResources.check', return_value=denied):
            row = self.wait_run(self.service.local_app.start(dict(approvalId=preview['approvalId'], confirmStart=True), False)['id'])
        self.assertEqual(row['reason'], 'resource_limit')
        self.assertEqual(row['resourceCheck'], denied)
        self.assertEqual(self.fixture.received, [])
        self.assertIn('89.0', (self.root / row['reportId']).read_text(encoding='utf-8'))

    def test_agent_passive_recipe_is_required_before_finish(self):
        self.doc['scope']['profile_id'] = 'bounded-passive-v1'
        self.service.set_enabled(True)
        for complete in (False, True):
            proposals = [decision('inspect_local_route', reference='route-001'), decision('inspect_local_route', reference='route-002')]
            if complete: proposals.append(decision('analyze_passive_capture', reference='entry'))
            proposals.append(decision('finish', evidence=['o1', 'o2', 'o3'] if complete else ['o1', 'o2']))
            self.service.model_factory = lambda *args: ScriptedModel(proposals)
            with patch('src_auto.local_application_workflow.ZapOfflineScanner.prepare'), patch('src_auto.local_application_workflow.ZapOfflineScanner.run', return_value={'status': 'completed', 'findings': [], 'scanner_target_requests': 0}) as scanner:
                approval = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
                row = self.wait_run(self.service.local_app.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)['id'])
                self.assertEqual(row['state'], 'completed' if complete else 'needs-human')
                self.assertEqual(scanner.call_count, int(complete))
                if not complete: self.assertEqual(row['reason'], 'local_web_coverage_incomplete')

    def test_passive_recipe_is_required_and_persists_real_route_coverage(self):
        self.doc['scope']['profile_id'] = 'bounded-passive-v1'
        with patch('src_auto.local_application_workflow.ZapOfflineScanner.prepare'), patch('src_auto.local_application_workflow.ZapOfflineScanner.run', return_value={'status': 'completed', 'findings': [], 'scanner_target_requests': 0}) as scanner:
            preview = self.service.local_app.preview(self.doc, False)
            result = self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
            row = self.wait_run(result['id'])
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(row['observations'][-1]['action'], 'analyze_passive_capture')
        self.assertEqual(row['passive']['scanner_target_requests'], 0)
        self.assertEqual(row['requests'], 2)
        scanner.assert_called_once()

    def setUp(self):
        self.fixture = fixture.LocalApplicationHTTPTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation'))
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        (self.root / 'config/models.yaml').write_text('{}', encoding='utf-8')
        self.control = Control()
        self.calls = 0
        def factory(*args):
            self.calls += 1
            return ScriptedModel([decision('inspect_local_route', reference='route-001'),
                                  decision('inspect_local_route', reference='route-002'),
                                  decision('finish', evidence=['o1', 'o2'])])
        self.service = AgentService(self.root, self.control, model_factory=factory)
        self.control.agent = self.service
        self.doc = {'scope': dict(self.fixture.document, allowed_paths=['/', '/api/health'], allowed_methods=['GET']),
                    'mode': 'standard', 'provider': 'none', 'allowCloud': False}
        self.resource = patch('src_auto.local_application_workflow.WindowsResources.check', return_value={'known': True, 'allowed': True})
        self.resource.start()

    def tearDown(self):
        self.service.close()
        deadline = time.monotonic() + 4
        while self.service.active and time.monotonic() < deadline:
            time.sleep(.01)
        self.resource.stop()

    def wait_run(self, key):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = self.service.history.get(key)
            if row.get('reportId'):
                return row
            time.sleep(.01)
        self.fail('local application task did not finalize')

    def test_offline_approval_standard_execution_and_linked_report(self):
        preview = self.service.local_app.preview(self.doc, False)
        self.assertEqual(self.fixture.received, [])
        self.assertFalse(preview['networkContact'])
        result = self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        row = self.wait_run(result['id'])
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(row['requests'], 2)
        self.assertEqual(row['modelCalls'], 0)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.fixture.received, [('GET', '/'), ('GET', '/api/health')])
        report = (self.root / row['reportId']).read_text(encoding='utf-8')
        self.assertIn('本机应用审查', report)
        self.assertIn('配置建议', report)
        self.assertNotIn('SYNTHETIC_PRIVATE', report)
        self.assertEqual(row['candidates'], 0)
        self.assertTrue(row['standardRunId'])
        with self.assertRaisesRegex(ValueError, 'approval_already_used'):
            self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)

    def test_agent_uses_actual_feedback_and_cannot_finish_before_coverage(self):
        self.service.set_enabled(True)
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
        result = self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        row = self.wait_run(result['id'])
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(row['modelCalls'], 3)
        self.assertEqual(row['requests'], 2)
        self.assertEqual(self.fixture.received, [('GET', '/'), ('GET', '/api/health')])
        self.assertEqual(row['candidates'], 0)
        self.assertEqual(len(row['observations']), 2)

    def test_missing_confirmation_and_disabled_cloud_never_load_model_or_connect(self):
        for cloud in (False, True):
            with self.assertRaisesRegex(ValueError, 'remote_ai_disabled_for_session'):
                self.service.local_app.preview(dict(self.doc, mode='agent', provider='deepseek', allowCloud=cloud), False)
        preview = self.service.local_app.preview(self.doc, False)
        with self.assertRaises(ValueError):
            self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': 'true'}, False)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.fixture.received, [])

    def test_changed_application_identity_blocks_before_network(self):
        preview = self.service.local_app.preview(self.doc, False)
        with patch('src_auto.local_application_workflow.listener_identity', return_value='changed-instance'):
            with self.assertRaisesRegex(ValueError, 'application_identity_changed'):
                self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        self.assertEqual(self.fixture.received, [])

    @unittest.skipUnless(os.name == 'nt', 'Windows listener identity test')
    def test_actual_windows_listener_identity_is_stable(self):
        from src_auto.local_application_workflow import listener_identity
        value = listener_identity(self.doc['scope']['origin'])
        self.assertEqual(value, listener_identity(self.doc['scope']['origin']))
        self.assertEqual(len(value), 64)

    def test_premature_model_finish_is_not_success(self):
        self.service.set_enabled(True)
        self.service.model_factory = lambda *args: ScriptedModel([
            decision('inspect_local_route', reference='route-001'), decision('finish', evidence=['o1'])])
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
        row = self.wait_run(self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)['id'])
        self.assertEqual(row['state'], 'needs-human')
        self.assertEqual(row['reason'], 'local_web_coverage_incomplete')
        self.assertEqual(self.fixture.received, [('GET', '/')])
        self.assertEqual(len(list((self.root / 'reports').rglob('*.md'))), 1)

    def test_setup_failure_does_not_leave_queued_work_or_contact(self):
        preview = self.service.local_app.preview(self.doc, False)
        with patch('src_auto.local_application_workflow.project_path', side_effect=OSError('synthetic failure')):
            with self.assertRaisesRegex(RuntimeError, 'local_application_setup_failed'):
                self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        self.assertFalse(self.service.active)
        self.assertEqual(self.service.history.list()[0]['state'], 'failed')
        self.assertEqual(self.fixture.received, [])

    def test_standard_cancellation_stops_remaining_routes_and_links_report(self):
        # Canonical approval order sorts paths; make the slow route first.
        self.doc['scope']['allowed_paths'] = ['/slow', '/zzz']
        preview = self.service.local_app.preview(self.doc, False)
        result = self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        self.assertTrue(self.fixture.started.wait(1))
        self.service.cancel_run(result['id'])
        row = self.wait_run(result['id'])
        self.assertEqual(row['state'], 'cancelled')
        self.assertEqual(row['requests'], 1)
        self.assertEqual(self.fixture.received, [('GET', '/slow')])
        self.assertEqual(row['trace'][-1]['result'], 'failed')
        self.assertTrue((self.root / row['reportId']).is_file())

    def test_queue_failure_cleans_up_owned_task_without_contact(self):
        preview = self.service.local_app.preview(self.doc, False)
        with patch.object(self.service.executor, 'submit', side_effect=RuntimeError('synthetic queue failure')):
            with self.assertRaisesRegex(RuntimeError, 'queue_unavailable'):
                self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        self.assertFalse(self.service.active)
        self.assertEqual(self.service.history.list()[0]['state'], 'failed')
        self.assertEqual(self.fixture.received, [])

    def test_standard_limits_describe_the_actual_finite_plan_not_agent_defaults(self):
        self.doc['scope']['allowed_paths'] = ['/p{}'.format(i) for i in range(9)]
        self.doc['scope']['limits']['request_limit'] = 150
        preview = self.service.local_app.preview(self.doc, False)
        row = self.wait_run(self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)['id'])
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(row['steps'], 9)
        self.assertEqual(row['limits']['max_steps'], 9)
        self.assertEqual(row['limits']['max_requests'], 150)
        self.assertEqual(row['limits']['max_model_calls'], 0)
        self.assertEqual(row['limits']['max_tokens'], 0)

    def test_partial_report_contains_actual_attempt_count(self):
        self.doc['scope']['allowed_paths'] = ['/', '/redirect-bad']
        preview = self.service.local_app.preview(self.doc, False)
        row = self.wait_run(self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)['id'])
        self.assertEqual(row['state'], 'needs-human')
        self.assertEqual(row['reason'], 'path_excluded')
        self.assertEqual(row['requests'], 2)
        self.assertNotIn(('GET', '/api/reset'), self.fixture.received)
        self.assertEqual(row['trace'][-1]['result'], 'failed')
        self.assertEqual(row['trace'][-1]['decision']['reference'], 'route-002')
        report = (self.root / row['reportId']).read_text(encoding='utf-8')
        self.assertIn('含跳转）：2', report)

    def test_session_gate_is_rechecked_before_cloud_factory_at_start(self):
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='deepseek', allowCloud=True), True)
        with self.assertRaisesRegex(ValueError, 'remote_ai_disabled_for_session'):
            self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.fixture.received, [])

    def test_identity_change_after_model_call_cannot_finish_successfully(self):
        from src_auto.local_application_workflow import listener_identity
        self.service.set_enabled(True)
        changed = [False]
        model = ScriptedModel([decision('inspect_local_route', reference='route-001'),
                               decision('inspect_local_route', reference='route-002'), decision('finish', evidence=['o1', 'o2'])])
        original_decide = model.decide
        def decide(context):
            result = original_decide(context)
            if len(context['observations']) == 2: changed[0] = True
            return result
        model.decide = decide
        self.service.model_factory = lambda *args: model
        preview = self.service.local_app.preview(dict(self.doc, mode='agent', provider='local'), False)
        with patch('src_auto.local_application_workflow.listener_identity', side_effect=lambda origin: 'changed' if changed[0] else listener_identity(origin)):
            row = self.wait_run(self.service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, False)['id'])
        self.assertEqual(row['state'], 'needs-human')
        self.assertEqual(row['reason'], 'application_identity_changed')


if __name__ == '__main__':
    unittest.main()

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src_auto.agent_service import AgentService
from src_auto.business_preparation import BusinessPreparation, ROLES
from src_auto.local_targets import LocalTargetLibrary
from src_auto.l4_lab import L4SyntheticLab, CONTROL_PATHS
from tests.test_agent import ScriptedModel, decision
from tests.test_agent_service import Control

ROOT = Path(__file__).resolve().parents[1]


class BusinessWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(ROOT / 'validation'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        (self.root / 'config/models.yaml').write_text('{}', encoding='utf-8')
        self.lab = L4SyntheticLab(self.root)
        self.lab.start()
        self.addCleanup(self.lab.close)
        self.prep = BusinessPreparation(self.root)
        self.target, self.row = self.lab.provision()
        self.control = Control()
        self.service = AgentService(self.root, self.control, model_factory=lambda *a: ScriptedModel([
            decision('compare_business_object', reference='object-001'),
            decision('compare_business_object', reference='object-002'),
            decision('validate_business_controls'), decision('finish', evidence=['o1', 'o2', 'o3'])]))
        self.control.agent = self.service
        self.addCleanup(self.service.close)
        self.resources = patch('src_auto.business_workflow.WindowsResources.check', return_value={'known': True, 'allowed': True})
        self.resources.start()
        self.addCleanup(self.resources.stop)

    def approval(self, **changes):
        now = datetime.now(timezone.utc)
        value = dict(id=self.row['id'], revision=self.row['revision'], confirmIsolation=True,
                     windowStart=(now - timedelta(seconds=30)).isoformat(), windowEnd=(now + timedelta(minutes=5)).isoformat(),
                     mode='standard', provider='none', allowCloud=False, controls=True)
        value.update(changes)
        return self.service.business.preview(value, changes.get('allowCloud', False))

    def run_approval(self, approval, remote=False):
        key = self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), remote)['id']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = self.service.history.get(key)
            if row.get('reportId') and self.service.current_id is None:
                return row
            time.sleep(.01)
        self.fail('business task did not finalize')

    def test_real_standard_positive_negative_four_roles_and_controls(self):
        approval = self.approval()
        self.assertEqual(self.lab.received, [])
        self.assertEqual(approval['requestCount'], 16)
        row = self.run_approval(approval)
        self.assertEqual(row['state'], 'completed')
        self.assertEqual((row['requests'], row['modelCalls'], row['candidates']), (16, 0, 3))
        checks = row['observations']
        self.assertTrue(checks[0]['candidate'])
        self.assertFalse(checks[1]['candidate'])
        self.assertEqual(checks[0]['unexpectedRoles'], ['account-b'])
        self.assertTrue(checks[2]['controlsValid'])
        self.assertEqual(checks[2]['candidateCount'], 2)
        report = (self.root / row['reportId']).read_text(encoding='utf-8')
        self.assertIn('四角色', report)
        self.assertIn('脚本执行未验证', report)
        persisted = json.dumps(row) + report + (self.root / 'data/agent.sqlite3').read_bytes().decode('latin1')
        for marker in self.lab.secret_markers:
            self.assertNotIn(marker, persisted)
        self.assertFalse(row['confirmed'])
        self.assertFalse(row['submissionReady'])
        with self.assertRaisesRegex(ValueError, 'approval_already_used'):
            self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)

    def test_agent_executes_and_cannot_finish_before_full_coverage(self):
        self.service.set_enabled(True)
        row = self.run_approval(self.approval(mode='agent', provider='local'))
        self.assertEqual((row['state'], row['requests'], row['modelCalls']), ('completed', 16, 4))
        self.service.model_factory = lambda *a: ScriptedModel([
            decision('compare_business_object', reference='object-001'), decision('finish', evidence=['o1'])])
        row = self.run_approval(self.approval(mode='agent', provider='local'))
        self.assertEqual(row['state'], 'needs-human')
        self.assertEqual(row['reason'], 'business_coverage_incomplete')
        self.assertEqual(row['requests'], 4)

    def test_cloud_disabled_blocks_before_model_factory_and_network(self):
        with patch.object(self.service, 'model_factory') as factory, self.assertRaisesRegex(ValueError, 'remote_ai_disabled'):
            now = datetime.now(timezone.utc)
            self.service.business.preview(dict(id=self.row['id'], revision=self.row['revision'], confirmIsolation=True,
                windowStart=(now - timedelta(seconds=1)).isoformat(), windowEnd=(now + timedelta(minutes=1)).isoformat(),
                mode='agent', provider='deepseek', allowCloud=True, controls=True), False)
        factory.assert_not_called()
        self.assertEqual(self.lab.received, [])

    def test_changed_session_target_preparation_or_instance_invalidates_approval(self):
        approval = self.approval()
        name = self.row['sessions']['account-a']
        self.prep.save_session(dict(targetId=self.target['id'], targetRevision=self.target['revision'], name=name,
            role='account-a', headers={'Authorization': 'Bearer replacement'}, confirmTestAccount=True,
            expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()))
        with self.assertRaisesRegex(ValueError, 'business_context_changed'):
            self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)
        self.assertEqual(self.lab.received, [])

    def test_stop_resources_expiry_and_request_failure_never_claim_complete(self):
        approval = self.approval()
        (self.root / 'STOP').write_text('stop', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)
        self.assertEqual(self.lab.received, [])
        (self.root / 'STOP').unlink()
        with patch('src_auto.business_workflow.WindowsResources.check', return_value={'known': True, 'allowed': False}):
            row = self.run_approval(self.approval())
        self.assertNotEqual(row['state'], 'completed')
        self.assertEqual(row['requests'], 0)

    def test_http_200_wrong_object_is_inconclusive_not_a_vulnerability(self):
        self.lab.wrong_object = True
        row = self.run_approval(self.approval(controls=False))
        self.assertEqual(row['candidates'], 0)
        self.assertTrue(all(not x['baselineValid'] for x in row['observations']))
        self.assertEqual(row['state'], 'needs-human')

    def test_redirect_never_leaks_bound_sessions_or_extends_scope(self):
        self.lab.redirect = True
        row = self.run_approval(self.approval(controls=False))
        self.assertNotEqual(row['state'], 'completed')
        self.assertEqual(row['requests'], 1)
        self.assertEqual(len(self.lab.received), 1)
        self.assertEqual(row['reason'], 'redirect_not_allowed')

    def test_controls_require_registered_program_owned_fixture(self):
        self.lab.registry_path.unlink()
        with self.assertRaisesRegex(ValueError, 'controlled_fixture_required'):
            self.approval()
        self.assertEqual(self.lab.received, [])

    def test_unknown_actions_and_parameters_cannot_reach_tools(self):
        self.service.set_enabled(True)
        self.service.model_factory = lambda *a: ScriptedModel([decision('inspect_headers')])
        row = self.run_approval(self.approval(mode='agent', provider='local'))
        self.assertNotEqual(row['state'], 'completed')
        self.assertEqual(self.lab.received, [])
        with self.assertRaises(ValueError): self.approval(command='reset')

    def test_changes_mid_task_stop_before_the_next_role(self):
        from src_auto.business_workflow import BusinessHTTP
        original = BusinessHTTP.fetch
        def mutate(client, request):
            result = original(client, request)
            self.prep.delete({'id': self.row['id']})
            return result
        with patch.object(BusinessHTTP, 'fetch', mutate):
            row = self.run_approval(self.approval(controls=False))
        self.assertEqual(row['state'], 'needs-human')
        self.assertEqual(row['reason'], 'business_context_changed')
        self.assertEqual(row['requests'], 1)

    def test_stop_mid_task_has_no_follow_up_requests(self):
        from src_auto.business_workflow import BusinessHTTP
        original = BusinessHTTP.fetch
        def stop(client, request):
            result = original(client, request)
            client.cancel.set()
            return result
        with patch.object(BusinessHTTP, 'fetch', stop):
            row = self.run_approval(self.approval(controls=False))
        self.assertEqual(row['state'], 'cancelled')
        self.assertEqual(row['requests'], 1)

    def test_agent_preserves_mid_request_context_failure_reason(self):
        from src_auto.business_workflow import BusinessHTTP
        original = BusinessHTTP.fetch
        def mutate(client, request):
            result = original(client, request)
            self.prep.delete({'id': self.row['id']})
            return result
        self.service.set_enabled(True)
        with patch.object(BusinessHTTP, 'fetch', mutate):
            row = self.run_approval(self.approval(mode='agent', provider='local', controls=False))
        self.assertEqual(row['reason'], 'business_context_changed')
        self.assertEqual(row['state'], 'needs-human')
        self.assertEqual(row['requests'], 1)

    def test_listener_identity_change_and_outside_window_block_start(self):
        approval = self.approval(controls=False)
        with patch('src_auto.business_workflow.listener_identity', return_value='different'):
            with self.assertRaisesRegex(ValueError, 'application_identity_changed'):
                self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)
        now = datetime.now(timezone.utc)
        with self.assertRaisesRegex(ValueError, 'outside_test_window'):
            self.approval(windowStart=(now-timedelta(minutes=5)).isoformat(), windowEnd=(now-timedelta(minutes=1)).isoformat())
        self.assertEqual(self.lab.received, [])

    def test_queue_failure_marks_both_task_records_failed(self):
        approval = self.approval()
        with patch.object(self.service.executor, 'submit', side_effect=RuntimeError('PRIVATE_QUEUE_ERROR')):
            with self.assertRaisesRegex(RuntimeError, 'queue_unavailable'):
                self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)
        row = self.service.history.list()[0]
        self.assertEqual(row['state'], 'failed')
        from src_auto.store import Store
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            self.assertEqual(store.conn.execute('SELECT status FROM runs WHERE run_id=?', (row['standardRunId'],)).fetchone()[0], 'failed')
        finally: store.close()
        self.assertIsNone(self.service.current_id)

    def test_false_positive_control_does_not_claim_success(self):
        from src_auto.business_workflow import BusinessHTTP
        original = BusinessHTTP._observe
        def broken_control(client, data, result):
            value = original(client, data, result)
            if '/xss/protected/' in result['path']: value['markerParsed'] = True
            return value
        with patch.object(BusinessHTTP, '_observe', broken_control):
            row = self.run_approval(self.approval())
        self.assertEqual(row['state'], 'needs-human')
        self.assertFalse(row['observations'][-1]['controlsValid'])
        self.assertEqual(row['observations'][-1]['candidateCount'], 0)

    def test_report_failure_ends_both_records_without_false_completion(self):
        from src_auto.business_workflow import project_path
        from src_auto.store import Store
        approval = self.approval(controls=False)
        def unavailable_report(root, *parts):
            if parts[0] == 'reports': raise OSError('PRIVATE_FILE_ERROR')
            return project_path(root, *parts)
        with patch('src_auto.business_workflow.project_path', side_effect=unavailable_report):
            key = self.service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), False)['id']
            deadline = time.monotonic() + 10
            while self.service.current_id is not None and time.monotonic() < deadline:
                time.sleep(.01)
        self.assertIsNone(self.service.current_id)
        row = self.service.history.get(key)
        self.assertEqual((row['state'], row['reason']), ('failed', 'business_report_failed'))
        self.assertFalse(row.get('reportId'))
        self.assertNotIn('PRIVATE_FILE_ERROR', json.dumps(row))
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            self.assertEqual(store.conn.execute('SELECT status FROM runs WHERE run_id=?', (row['standardRunId'],)).fetchone()[0], 'failed')
        finally: store.close()

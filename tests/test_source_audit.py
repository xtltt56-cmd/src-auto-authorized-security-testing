import json
import tempfile
import threading
import unittest
import time
from pathlib import Path
from unittest.mock import patch

from src_auto.source_audit import source_manifest, normalize_source_results, SourceScanner
from src_auto.agent_service import AgentService
from tests.test_agent_service import Control


class SourceAuditContracts(unittest.TestCase):
    def test_business_code_packages_named_data_and_runtime_are_included(self):
        for relative in ('src/product/data/store.py', 'src/product/runtime/worker.py', 'data/private.py'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('print(1)', encoding='utf-8')
        manifest = source_manifest(self.root, ['python'], True)
        self.assertEqual({x['path'] for x in manifest['files']}, {'app.py', 'src/product/data/store.py', 'src/product/runtime/worker.py'})
        self.assertIn({'path': 'data', 'reason': 'runtime_directory'}, manifest['exclusions'])

    def test_disk_sampling_is_bounded_but_stop_and_free_space_still_fail_closed(self):
        from src_auto.source_audit import SourceExecutionGuard
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        cancel = threading.Event()
        with patch('src_auto.source_audit.DiskGuard.check', return_value={'allowed': True, 'known': True, 'used_gb': 1}) as disk, \
             patch('src_auto.source_audit.WindowsResources.check', return_value={'allowed': True}), \
             patch('src_auto.source_audit.shutil.disk_usage', return_value=type('Usage', (), {'free': 1024**3})()):
            guard = SourceExecutionGuard(self.root, cancel, '', 1048576)
            for _ in range(100): self.assertEqual(guard(), '')
            self.assertEqual(disk.call_count, 1)
            self.assertEqual(guard(force=True), '')
            self.assertEqual(disk.call_count, 2)
            cancel.set()
            self.assertEqual(guard(), 'cancelled')
            cancel.clear()
            with patch('src_auto.source_audit.shutil.disk_usage', return_value=type('Usage', (), {'free': 0})()):
                self.assertEqual(guard(), 'blocked_disk')
            with patch('src_auto.source_audit.DiskGuard.check', return_value={'allowed': False, 'known': False}):
                self.assertEqual(guard(force=True), 'blocked_disk')

    def test_cloud_start_is_denied_without_session_and_task_consent(self):
        service = AgentService(self.root, Control())
        self.addCleanup(service.close)
        for session, document in ((False, {'allowCloud': True}), (True, {'allowCloud': 'yes'})):
            with self.assertRaises(ValueError):
                service.source_audit.start(dict(approvalId='missing', confirmStart=True, **document), session)

    def test_explicit_skip_metadata_is_kept_without_tool_messages_or_source(self):
        manifest = source_manifest(self.root, ['python'], True)
        result = normalize_source_results({'bandit': {'results': [], 'scanned': [], 'errors': 0,
            'skipped': [{'path': '/input/app.py', 'reason': 'parse_error', 'details': 'PRIVATE_SECRET'}]}}, manifest)
        self.assertEqual(result['unprocessedDetails'], [{'path': 'app.py', 'scanner': 'bandit', 'reason': 'parse_error'}])
        self.assertNotIn('PRIVATE_SECRET', json.dumps(result))

    def test_cloud_schema_failure_preserves_candidates_and_reserves_attempt(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from src_auto.agent_contracts import Limits
        from src_auto.remote_ai import RemoteProviderError
        from src_auto.store import Store
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        service = AgentService(self.root, Control())
        self.addCleanup(service.close)
        row = service.history.create('test', 'source-audit', 'deepseek', Limits(), SimpleNamespace(scope_hash='a', config_hash='b'))
        provider = Mock()
        provider.review.side_effect = RemoteProviderError('invalid_remote_disposition')
        budget = Mock()
        budget.reserve.return_value = .064
        result = dict(findings=[dict(scanner='bandit', rule_id='B602', path='app.py', line=2)])
        gate = Mock(return_value='')
        gate.started = time.monotonic()
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            service.source_audit._review(row['id'], 'run', result, provider, budget, store, gate)
            self.assertEqual(result['cloudReview']['errors'], [{'rule': 'B602', 'reason': 'remote_review_failed'}])
            self.assertEqual(result['cloudReview']['unreviewedCandidates'], 1)
            self.assertEqual(result['cloudReview']['reservedCny'], .064)
            self.assertTrue(result['cloudReview']['usageEstimated'])
            self.assertEqual(service.history.get(row['id'])['modelCalls'], 1)
            self.assertEqual(store.list_ai_reviews(), [])
            provider.review.assert_called_once()
        finally: store.close()

    def test_cloud_cancel_after_response_keeps_actual_call_and_usage_counts(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from src_auto.agent_contracts import Limits
        from src_auto.local_application import LocalApplicationError
        from src_auto.store import Store
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        service = AgentService(self.root, Control())
        self.addCleanup(service.close)
        row = service.history.create('test', 'source-audit', 'deepseek', Limits(), SimpleNamespace(scope_hash='a', config_hash='b'))
        provider = Mock()
        provider.review.return_value = dict(disposition='manual_review', input_tokens=100, output_tokens=30)
        budget = Mock()
        budget.reserve.return_value = .064
        budget.estimate.return_value = .001
        result = dict(findings=[dict(scanner='bandit', rule_id='B602', path='app.py', line=2)])
        gate = Mock(side_effect=['', 'cancelled'])
        gate.started = time.monotonic()
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            with self.assertRaises(LocalApplicationError):
                service.source_audit._review(row['id'], 'run', result, provider, budget, store, gate)
            self.assertEqual(result['modelCalls'], 1)
            self.assertEqual(service.history.get(row['id'])['tokens'], 130)
            self.assertEqual(result['cloudReview']['estimatedCny'], .001)
            self.assertEqual(result['cloudReview']['unreviewedCandidates'], 1)
            self.assertEqual(store.list_ai_reviews(), [])
            provider.review.assert_called_once()
        finally: store.close()

    def test_native_cloud_review_only_sends_rule_counts_and_persists_real_review(self):
        from types import SimpleNamespace
        from src_auto.store import Store
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        finding = dict(scanner='bandit', rule_id='B602', title='使用 shell 执行子进程', path='app.py', line=2, category='source-risk-candidate')
        (self.root / 'config/models.yaml').write_text('{}', encoding='utf-8')
        result = dict(findings=[finding], complete=True, toolErrors=0, networkMode='none')
        provider = SimpleNamespace(max_output_tokens=256, review=lambda payload: dict(disposition='manual_review', confidence=.5,
            reason='需要局部数据流复核', suggested_checks=[], provider='deepseek', model='synthetic', input_tokens=100, output_tokens=30))
        received = []
        original = provider.review
        provider.review = lambda payload: (received.append(payload), original(payload))[1]
        service = AgentService(self.root, Control(), model_factory=lambda *args: SimpleNamespace(provider=provider))
        self.addCleanup(service.close)
        with patch.object(SourceScanner, 'prepare'), patch.object(SourceScanner, 'run_source', return_value=result), \
             patch('src_auto.source_audit.WindowsResources.check', return_value={'allowed': True}), \
             patch('src_auto.source_audit.DeepSeekAgentBudget.configured') as budget:
            budget.return_value.reserve.return_value = .064
            budget.return_value.estimate.return_value = .001
            approval = service.source_audit.preview(dict(directory=str(self.root), languages=['python'], confirmRead=True, confirmSnapshot=True))
            started = service.source_audit.start(dict(approvalId=approval['approvalId'], confirmStart=True, allowCloud=True), True)
            service.executor.shutdown(wait=True)
            row = service.history.get(started['id'])
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(row['modelCalls'], 1)
        self.assertEqual(row['sourceAudit']['cloudReview']['groups'][0]['disposition'], 'manual_review')
        self.assertNotIn('app.py', json.dumps(received))
        self.assertNotIn(str(self.root), json.dumps(received))
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            self.assertEqual(len(store.list_ai_reviews(run_id=row['standardRunId'])), 1)
            self.assertTrue(all(x['status'] == 'candidate' for x in store.list_findings()))
        finally: store.close()

    def test_partial_snapshot_write_failure_does_not_keep_source_content(self):
        manifest = source_manifest(self.root, ['python'], True)
        scanner = SourceScanner(self.root, threading.Event(), lambda: '')
        original = Path.write_bytes
        def failing_write(path, content):
            original(path, content)
            raise OSError('synthetic disk failure')
        with patch.object(scanner, 'prepare'), patch.object(scanner.process, 'run', return_value=b''), patch.object(Path, 'write_bytes', failing_write):
            with self.assertRaises(OSError): scanner.run_source(manifest, threading.Event(), lambda: '')
        self.assertEqual(list((self.root / 'runs/source').rglob('*.py')), [])

    def test_unprocessed_supported_file_is_not_a_clean_completed_audit(self):
        manifest = source_manifest(self.root, ['python'], True)
        result = normalize_source_results({'bandit': {'results': [], 'scanned': [], 'errors': 0}}, manifest)
        self.assertFalse(result['complete'])
        self.assertEqual(result['unprocessedFiles'], ['app.py'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'app.py').write_text('import subprocess\nsubprocess.run("x", shell=True)\n', encoding='utf-8')
        (self.root / '.env').write_text('PRIVATE_SECRET', encoding='utf-8')
        (self.root / 'node_modules').mkdir()
        (self.root / 'node_modules/skip.js').write_text('eval(secret)', encoding='utf-8')

    def test_directory_authorization_exclusions_and_snapshot_digest(self):
        with self.assertRaisesRegex(ValueError, 'source_authorization_required'):
            source_manifest(self.root, ['python'], False)
        first = source_manifest(self.root, ['python'], True)
        self.assertEqual([x['path'] for x in first['files']], ['app.py'])
        self.assertNotIn('PRIVATE_SECRET', json.dumps(first))
        (self.root / 'app.py').write_text('print(1)', encoding='utf-8')
        self.assertNotEqual(first['digest'], source_manifest(self.root, ['python'], True)['digest'])

    def test_broad_paths_unknown_languages_and_file_quotas_fail_closed(self):
        with self.assertRaises(ValueError): source_manifest(Path(self.root.anchor), ['python'], True)
        with self.assertRaises(ValueError): source_manifest(self.root, ['bash'], True)
        with self.assertRaises(ValueError): source_manifest(self.root, ['python'], True, max_bytes=1)

    def test_results_only_approved_paths_rules_and_lines_no_code_or_keys(self):
        manifest = source_manifest(self.root, ['python'], True)
        raw = {'bandit': {'results': [{'filename': '/input/app.py', 'test_id': 'B602', 'line_number': 2,
                                     'issue_severity': 'HIGH', 'code': 'PRIVATE_SECRET', 'issue_text': 'PRIVATE_SECRET'},
                                    {'filename': '/etc/secret', 'test_id': 'B602', 'line_number': 1}], 'errors': []},
               }
        result = normalize_source_results(raw, manifest)
        self.assertEqual(result['findings'][0]['path'], 'app.py')
        self.assertNotIn('PRIVATE_SECRET', json.dumps(result))
        self.assertEqual(len(result['findings']), 1)

    def test_source_scanner_never_publishes_ports_or_mounts_original_root(self):
        scanner = SourceScanner(self.root, threading.Event(), lambda: '')
        scanner.docker, scanner.image = 'docker', 'pinned'
        args = scanner.command(self.root / 'owned-snapshot', 'src-auto-source-test')
        self.assertEqual(args[args.index('--network') + 1], 'none')
        self.assertEqual(args[args.index('--pull') + 1], 'never')
        self.assertIn('--read-only', args)
        self.assertNotIn('--publish', args)
        self.assertNotIn('host.docker.internal', ' '.join(args))

    def test_real_coordinator_queue_links_report_without_a_model(self):
        (self.root / 'config/integrations').mkdir(parents=True)
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        (self.root / 'config/integrations/source_rules.json').write_text('{}', encoding='utf-8')
        control = Control()
        def denied_model(*args): self.fail('source audit must never construct a cloud/local model')
        service = AgentService(self.root, control, model_factory=denied_model)
        control.agent = service
        self.addCleanup(service.close)
        document = dict(directory=str(self.root), languages=['python'], confirmRead=True, confirmSnapshot=True)
        result = dict(findings=[], complete=True, toolErrors=0, networkMode='none')
        with patch.object(SourceScanner, 'prepare'), patch.object(SourceScanner, 'run_source', return_value=result), patch('src_auto.source_audit.WindowsResources.check', return_value={'allowed': True}):
            approval = service.source_audit.preview(document)
            with self.assertRaises(ValueError): service.source_audit.start(dict(approvalId=approval['approvalId'], confirmStart=False))
            started = service.source_audit.start(dict(approvalId=approval['approvalId'], confirmStart=True))
            # The single-worker queue publishes reportId before database/lease
            # cleanup. A queue barrier waits for actual finalization, not just
            # report visibility; keep the inactive assertion below meaningful.
            service.executor.submit(lambda: None).result(timeout=4)
            row = service.history.get(started['id'])
            self.assertEqual(row['state'], 'completed')
            self.assertEqual(row['modelCalls'], 0)
            self.assertTrue((self.root / row['reportId']).is_file())
            self.assertNotIn('PRIVATE_SECRET', (self.root / row['reportId']).read_text(encoding='utf-8'))
            self.assertFalse(service.active)
            with self.assertRaisesRegex(ValueError, 'approval_already_used'):
                service.source_audit.start(dict(approvalId=approval['approvalId'], confirmStart=True))

    def test_file_change_after_preview_blocks_queue_and_scanner(self):
        (self.root / 'config').mkdir()
        (self.root / 'config/policy.yaml').write_text('{}', encoding='utf-8')
        service = AgentService(self.root, Control())
        self.addCleanup(service.close)
        with patch.object(SourceScanner, 'prepare'), patch.object(SourceScanner, 'run_source') as scanner, patch('src_auto.source_audit.WindowsResources.check', return_value={'allowed': True}):
            approval = service.source_audit.preview(dict(directory=str(self.root), languages=['python'], confirmRead=True, confirmSnapshot=True))
            (self.root / 'app.py').write_text('print(2)', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'source_changed_after_approval'):
                service.source_audit.start(dict(approvalId=approval['approvalId'], confirmStart=True))
            scanner.assert_not_called()
            self.assertEqual(service.history.list(), [])

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
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                row = service.history.get(started['id'])
                if row['reportId']: break
                time.sleep(.01)
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

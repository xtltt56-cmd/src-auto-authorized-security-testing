import tempfile
import unittest
from pathlib import Path

from src_auto.dashboard_workspace import DashboardWorkspace


def draft():
    return dict(projectName='测试项目', targetUrl='https://example.com/app',
                allowedHosts='example.com', allowedPorts='443', excludedPaths='/admin',
                windowStart='2026-09-12T10:00', windowEnd='2026-09-12T11:00',
                allowedMethods='GET, HEAD', concurrency='1', requestLimit='100', authorizationNote='规则编号')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = DashboardWorkspace(self.root)

    def tearDown(self): self.temp.cleanup()

    def test_draft_survives_reload_without_granting_authorization(self):
        saved = self.workspace.save_draft(draft())
        loaded = DashboardWorkspace(self.root).list_drafts()
        self.assertEqual(loaded[0]['id'], saved['id'])
        self.assertEqual(loaded[0]['draft'], draft())
        entries = self.workspace.review_targets()
        self.assertEqual(entries[0]['status'], 'candidate_only')
        self.assertFalse(entries[0]['actionable'])
        self.assertFalse(list(self.root.rglob('scope_confirmed.yaml')))

    def test_url_port_must_match_allowed_ports(self):
        value = draft(); value['allowedPorts'] = '80'
        with self.assertRaises(ValueError): self.workspace.save_draft(value)

    def test_reports_are_real_bounded_text_and_secrets_redacted(self):
        (self.root / 'reports').mkdir()
        fake_key = 'sk-or-v1-' + '12345678901234567890'
        (self.root / 'reports' / 'sample.md').write_text(
            '结果\nAuthorization: Bearer test-secret\n' + fake_key,
            encoding='utf-8',
        )
        content = self.workspace.artifacts()['reports'][0]['content']
        self.assertIn('结果', content)
        self.assertNotIn('test-secret', content)
        self.assertNotIn('12345678901234567890', content)

    def test_review_rejects_path_traversal(self):
        with self.assertRaises(ValueError): self.workspace.review_targets('../')

    def test_report_symlink_is_never_followed(self):
        outside = self.root / 'private.txt'
        outside.write_text('do-not-read', encoding='utf-8')
        (self.root / 'reports').mkdir()
        link = self.root / 'reports' / 'linked.md'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('当前 Windows 权限不允许创建符号链接')
        result = self.workspace.artifacts()
        self.assertEqual(result['reports'], [])
        self.assertTrue(result['warnings'])

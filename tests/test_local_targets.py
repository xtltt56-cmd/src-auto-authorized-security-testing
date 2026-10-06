import tempfile
import unittest
from pathlib import Path

from src_auto.local_targets import LocalTargetLibrary


class TargetLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation'))
        self.addCleanup(self.temp.cleanup)
        self.library = LocalTargetLibrary(Path(self.temp.name))
        self.draft = dict(name='合成靶场', kind='custom_lab', origin='http://127.0.0.1:8765',
                          paths=['/', '/health'], excluded=['/reset'], method='GET', profile='readonly-baseline-v1')

    def test_save_load_update_duplicate_delete_never_grants_authorization(self):
        row = self.library.save(self.draft)
        self.assertFalse(row['confirmed'])
        self.assertFalse(row['allowCloud'])
        self.assertEqual(self.library.list(), [row])
        updated = self.library.save(dict(self.draft, id=row['id'], name='更新'))
        self.assertEqual(updated['id'], row['id'])
        copied = self.library.duplicate(row['id'])
        self.assertNotEqual(copied['id'], row['id'])
        self.library.delete(row['id'])
        self.assertEqual(len(self.library.list()), 1)

    def test_external_hosts_credentials_commands_and_excluded_routes_rejected(self):
        for change in ({'origin': 'https://example.com:443'}, {'origin': 'http://localhost:8765'},
                       {'origin': 'http://user:secret@127.0.0.1:8765'}, {'paths': ['/reset']},
                       {'startup': 'anything'}, {'allowCloud': True}, {'id': '../escape'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.library.save(dict(self.draft, **change))
        self.assertEqual(self.library.list(), [])

    def test_name_does_not_save_secrets_and_changed_scope_invalidates_digest(self):
        with self.assertRaises(ValueError):
            self.library.save(dict(self.draft, name='sk-abcdefghijklmnopqrstuvwx'))
        first = self.library.save(self.draft)
        second = self.library.save(dict(self.draft, id=first['id'], paths=['/health']))
        self.assertNotEqual(first['revision'], second['revision'])

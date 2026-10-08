import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src_auto.local_targets import LocalTargetLibrary
from src_auto.business_preparation import BusinessPreparation

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('account-a', 'account-b', 'administrator', 'anonymous')


class BusinessPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(ROOT / 'validation'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.targets = LocalTargetLibrary(self.root)
        self.target_input = dict(name='隔离合成目标', kind='custom_lab', origin='http://127.0.0.1:8765',
                                 paths=['/objects/a'], excluded=['/reset'], method='GET', profile='readonly-baseline-v1')
        self.target = self.targets.save(self.target_input)
        self.service = BusinessPreparation(self.root)
        self.document = dict(targetId=self.target['id'], targetRevision=self.target['revision'],
            isolation=dict(dataLabel='synthetic-db', storageLabel='synthetic-files', resetNote='人工重置合成数据',
                           confirmIsolatedData=True, confirmTestAccounts=True, confirmNoProductionSecrets=True),
            cases=[dict(id='object-a', name='合成对象 A', path='/objects/a', owner='account-a',
                        expected={role: role in ('account-a', 'administrator') for role in ROLES})],
            sessions={})

    def test_save_is_draft_only_and_does_not_contact_targets_models_or_processes(self):
        with patch('socket.socket.connect', side_effect=AssertionError('unexpected network')), patch('subprocess.Popen', side_effect=AssertionError('unexpected process')):
            row = self.service.save(self.document)
            preview = self.service.preview({'id': row['id']})
        self.assertFalse(row['executionAuthorized'])
        self.assertFalse(preview['executionAvailable'])
        self.assertEqual(preview['networkRequests'], 0)
        self.assertEqual(preview['modelCalls'], 0)
        self.assertIn('session_required:account-a', preview['blockers'])
        self.assertEqual(self.service.snapshot()['preparations'][0]['id'], row['id'])

    def test_target_changes_or_deletion_invalidate_preparation(self):
        row = self.service.save(self.document)
        self.targets.save(dict(self.target_input, id=self.target['id'], paths=['/health']))
        result = self.service.preview({'id': row['id']})
        self.assertIn('target_changed', result['blockers'])
        self.targets.delete(self.target['id'])
        self.assertIn('target_missing', self.service.preview({'id': row['id']})['blockers'])

    def test_strict_declarations_cases_and_secret_metadata_rejected(self):
        changes = [dict(isolation=dict(self.document['isolation'], confirmIsolatedData='true')),
                   dict(isolation=dict(self.document['isolation'], confirmNoProductionSecrets=False)),
                   dict(cases=[dict(self.document['cases'][0], path='/reset')]),
                   dict(cases=[dict(self.document['cases'][0], path='/outside')]),
                   dict(cases=[dict(self.document['cases'][0], expected={'account-a': True})]),
                   dict(cases=[dict(self.document['cases'][0], expected={role: 'allow' for role in ROLES})]),
                   dict(isolation=dict(self.document['isolation'], dataLabel='sk-abcdefghijklmnopqrstuvwx')),
                   dict(startup='run something'), dict(allowCloud=True), dict(cases=[])]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.save(dict(self.document, **change))
        self.assertEqual(self.service.snapshot()['preparations'], [])

    def test_bound_session_save_and_ready_preview_never_return_credentials(self):
        names = {}
        for role in ROLES[:-1]:
            name = 'test-' + role
            self.service.save_session(dict(targetId=self.target['id'], targetRevision=self.target['revision'],
                name=name, role=role, headers={'Cookie': 'sid=synthetic-secret-' + role},
                expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(), confirmTestAccount=True))
            names[role] = name
        row = self.service.save(dict(self.document, sessions=names))
        result = self.service.preview({'id': row['id']})
        self.assertTrue(result['readyForNextStage'])
        self.assertFalse(result['executionAvailable'])
        rendered = json.dumps(self.service.snapshot(), ensure_ascii=False)
        self.assertNotIn('synthetic-secret-', rendered)
        self.assertNotIn('ciphertext', rendered)
        db = sqlite3.connect(str(self.root / 'data/src_auto.sqlite3'))
        try:
            self.assertNotIn('synthetic-secret-', db.execute('SELECT document FROM business_preparations').fetchone()[0])
        finally:
            db.close()

    def test_unconfirmed_expired_cross_target_or_injected_sessions_rejected(self):
        value = dict(targetId=self.target['id'], targetRevision=self.target['revision'], name='isolated-a',
            role='account-a', headers={'Cookie': 'sid=synthetic'},
            expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(), confirmTestAccount=True)
        for change in ({'confirmTestAccount': False}, {'role': 'anonymous'}, {'targetRevision': 'old'},
                       {'expiresAt': '2020-01-01T00:00:00Z'}, {'headers': {'Host': 'outside.test'}},
                       {'command': 'anything'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.save_session(dict(value, **change))
        self.service.save_session(value)
        other = self.targets.save(dict(self.target_input, name='另一个目标'))
        wrong = dict(self.document, targetId=other['id'], targetRevision=other['revision'], sessions={'account-a': value['name']})
        with self.assertRaises(ValueError):
            self.service.save(wrong)

    def test_preview_detects_expired_sessions_and_does_not_restore_permissions(self):
        from src_auto.session_vault import SessionVault, SessionProfile
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        vault = SessionVault(self.root)
        names = {}
        for role in ROLES[:-1]:
            names[role] = 'bound-' + role
            vault.save(SessionProfile(names[role], role, {'Cookie': 'sid=synthetic'}, self.target['id'], self.target['origin'], expiry.isoformat()))
        row = self.service.save(dict(self.document, sessions=names))
        with patch('src_auto.business_preparation.utcnow', return_value=expiry + timedelta(minutes=1)):
            preview = self.service.preview({'id': row['id']})
        self.assertFalse(preview['readyForNextStage'])
        self.assertIn('session_expired:account-a', preview['blockers'])
        self.assertFalse(preview['executionAuthorized'])

    def test_owned_app_requires_distinct_production_origin_and_reset_is_metadata_only(self):
        target = self.targets.save(dict(self.target_input, kind='owned_app'))
        value = dict(self.document, targetId=target['id'], targetRevision=target['revision'])
        for isolation in (value['isolation'], dict(value['isolation'], productionOrigin=target['origin'])):
            with self.assertRaises(ValueError):
                self.service.save(dict(value, isolation=isolation))
        row = self.service.save(dict(value, isolation=dict(value['isolation'], productionOrigin='http://127.0.0.1:9000')))
        self.assertEqual(row['state'], 'draft')
        self.assertFalse(row['isolationVerified'])
        self.assertNotIn('resetCommand', row)

    def test_delete_only_preparation_does_not_delete_target_or_sessions(self):
        row = self.service.save(self.document)
        self.service.delete({'id': row['id']})
        self.assertEqual(self.targets.list(), [self.target])
        self.assertEqual(self.service.snapshot()['preparations'], [])

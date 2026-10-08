import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class SessionVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT / "data"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_dpapi_round_trip_is_encrypted_and_metadata_is_redacted(self):
        from src_auto.session_vault import SessionProfile, SessionVault

        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        profile = SessionProfile(
            name="buyer-a",
            role="buyer",
            headers={"Authorization": "Bearer secret-token-a", "Cookie": "sid=secret-cookie"},
        )
        path = vault.save(profile)

        raw = path.read_bytes()
        self.assertNotIn(b"secret-token-a", raw)
        self.assertNotIn(b"secret-cookie", raw)
        restored = vault.load("buyer-a")
        self.assertEqual(restored.role, "buyer")
        self.assertEqual(restored.headers["Authorization"], "Bearer secret-token-a")
        listings = vault.list_profiles()
        self.assertEqual(listings, [{"name": "buyer-a", "role": "buyer", "header_names": ["Authorization", "Cookie"]}])
        self.assertNotIn("headers", listings[0])

    def test_profile_name_and_storage_must_stay_inside_project(self):
        from src_auto.session_vault import SessionProfile, SessionVault, SessionVaultError

        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        with self.assertRaisesRegex(SessionVaultError, "invalid_profile_name"):
            vault.save(SessionProfile("../escape", "buyer", {"Cookie": "x"}))
        with self.assertRaisesRegex(SessionVaultError, "vault_outside_project"):
            SessionVault(PROJECT_ROOT, PROJECT_ROOT.parent / "outside-vault")

    def test_delete_removes_only_named_profile(self):
        from src_auto.session_vault import SessionProfile, SessionVault

        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        vault.save(SessionProfile("buyer-a", "buyer", {"Cookie": "a"}))
        vault.save(SessionProfile("buyer-b", "buyer", {"Cookie": "b"}))

        self.assertTrue(vault.delete("buyer-a"))
        self.assertFalse(vault.delete("buyer-a"))
        self.assertEqual([item["name"] for item in vault.list_profiles()], ["buyer-b"])

    def test_bound_session_context_is_encrypted_and_checked_before_use(self):
        from src_auto.session_vault import SessionProfile, SessionVault, SessionVaultError
        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        target = 'custom-' + 'a' * 32
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        profile = SessionProfile('isolated-a', 'account-a', {'Authorization': 'Bearer synthetic-only'},
                                 target, 'http://127.0.0.1:8765', expiry)
        path = vault.save(profile)
        self.assertNotIn(b'Bearer synthetic-only', path.read_bytes())
        self.assertEqual(vault.load_for_target('isolated-a', target, profile.origin, 'account-a'), profile)
        for context in ((target, 'http://127.0.0.1:8766', 'account-a'),
                        ('custom-' + 'b' * 32, profile.origin, 'account-a'),
                        (target, profile.origin, 'account-b')):
            with self.assertRaisesRegex(SessionVaultError, 'session_target_mismatch'):
                vault.load_for_target('isolated-a', *context)
        metadata = vault.list_profiles()[0]
        self.assertTrue(metadata['bound'])
        self.assertFalse(metadata['expired'])
        self.assertNotIn('headers', metadata)

    def test_bound_session_rejects_expiry_legacy_and_metadata_rebinding(self):
        import json
        from src_auto.session_vault import SessionProfile, SessionVault, SessionVaultError
        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        target = 'custom-' + 'a' * 32
        now = datetime.now(timezone.utc)
        profile = SessionProfile('isolated-a', 'account-a', {'Cookie': 'sid=synthetic'}, target,
                                 'http://127.0.0.1:8765', (now + timedelta(minutes=5)).isoformat())
        path = vault.save(profile)
        with self.assertRaisesRegex(SessionVaultError, 'session_expired'):
            vault.load_for_target(profile.name, target, profile.origin, profile.role, now + timedelta(minutes=6))
        vault.save(SessionProfile('legacy', 'account-a', {'Cookie': 'sid=legacy'}))
        with self.assertRaisesRegex(SessionVaultError, 'session_binding_required'):
            vault.load_for_target('legacy', target, profile.origin, profile.role)
        document = json.loads(path.read_text(encoding='utf-8'))
        document['origin'] = 'http://127.0.0.1:8766'
        path.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaisesRegex(SessionVaultError, 'session_profile_invalid'):
            vault.load(profile.name)

    def test_bound_session_rejects_unsafe_headers_external_origins_and_partial_binding(self):
        from src_auto.session_vault import SessionProfile, SessionVault, SessionVaultError
        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        target = 'custom-' + 'a' * 32
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        for headers, origin, expires in (({'Host': 'outside.test'}, 'http://127.0.0.1:8765', expiry),
                                       ({'Cookie': 'sid=x\r\nHost: outside.test'}, 'http://127.0.0.1:8765', expiry),
                                       ({'Cookie': 'sid=x'}, 'https://outside.test:443', expiry),
                                       ({'Cookie': 'sid=x'}, 'http://127.0.0.1:8765', ''),
                                       ({'Cookie': 'sid=x'}, 'http://127.0.0.1:8765', '2099-01-01T00:00:00')):
            with self.subTest(origin=origin), self.assertRaises(SessionVaultError):
                vault.save(SessionProfile('invalid', 'account-a', headers, target, origin, expires))

    def test_bound_ciphertext_cannot_be_downgraded_to_legacy_headers(self):
        import json
        from src_auto.session_vault import SessionProfile, SessionVault, SessionVaultError
        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        path = vault.save(SessionProfile('isolated-a', 'account-a', {'Cookie': 'sid=synthetic'},
            'custom-' + 'a' * 32, 'http://127.0.0.1:8765',
            (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()))
        document = json.loads(path.read_text(encoding='utf-8'))
        document['schema_version'] = 1
        path.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaisesRegex(SessionVaultError, 'session_profile_invalid'):
            vault.load('isolated-a')

    def test_non_string_session_names_fail_with_public_error(self):
        from src_auto.session_vault import SessionVault, SessionVaultError
        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        for name in (None, 42, {}, []):
            with self.subTest(name=name), self.assertRaises(SessionVaultError):
                vault.load(name)

    def test_bound_http_credentials_reject_controls_unicode_and_non_strings(self):
        from src_auto.session_vault import SessionVault, SessionProfile, SessionVaultError
        vault = SessionVault(PROJECT_ROOT, Path(self.tmp.name))
        for value in ('sid=x\x00', 'sid=x\t', 'sid=中文', {'secret': 'x'}, 123):
            with self.subTest(value=value), self.assertRaises(SessionVaultError):
                vault.save(SessionProfile('isolated-a', 'account-a', {'Cookie': value},
                    'custom-' + 'a' * 32, 'http://127.0.0.1:8765',
                    (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()))


if __name__ == "__main__":
    unittest.main()

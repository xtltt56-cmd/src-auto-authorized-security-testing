import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()

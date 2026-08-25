import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
INSTALLER = PROJECT_ROOT / "tools" / "install_curated_tools.ps1"


class CuratedToolInstallerTests(unittest.TestCase):
    def test_installer_is_project_local_pinned_and_does_not_weaken_windows_security(self):
        self.assertTrue(INSTALLER.exists())
        raw = INSTALLER.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        lowered = text.lower()

        for required in (
            "vendor\\cache\\pip",
            "vendor\\cache\\tmp",
            "vendor\\pytools\\bbot",
            "vendor\\pytools\\schemathesis",
            "vendor\\testssl",
            "Get-FileHash",
            "github.com/projectdiscovery/nuclei",
            "github.com/blacklanternsecurity/bbot",
            "github.com/schemathesis/schemathesis",
            "github.com/testssl/testssl.sh",
            "bbot==",
            "schemathesis==",
            "--only-binary=:all:",
            "windows_binary_dependency_unavailable",
        ):
            self.assertIn(required.lower(), lowered)

        for forbidden in (
            "add-mppreference",
            "set-mppreference",
            "disablerealtimemonitoring",
            "netsh advfirewall",
            "setx path",
            "pip install --user",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_installer_never_extracts_unverified_nuclei_archive(self):
        text = INSTALLER.read_text(encoding="utf-8-sig")
        hash_check = text.index("Get-FileHash")
        archive_expand = text.index("Expand-Archive")
        self.assertLess(hash_check, archive_expand)
        self.assertIn("nucleiArchiveSha256", text)
        self.assertIn("throw 'nuclei_checksum_mismatch'", text)

    def test_testssl_wrapper_is_bounded_to_project_state(self):
        wrapper = PROJECT_ROOT / "vendor" / "bin" / "testssl.cmd"
        self.assertTrue(wrapper.exists())
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("vendor\\docker-state\\testssl", text.lower())
        self.assertIn("sha256:47d623064463c66ce3b02d37486c75dd1bff8fcef0d9947b37a5051b937ccd69", text.lower())
        self.assertNotIn("curl ", text.lower())
        self.assertNotIn("powershell", text.lower())

    def test_schemathesis_wrapper_forces_utf8_on_chinese_windows(self):
        wrapper = PROJECT_ROOT / "vendor" / "bin" / "schemathesis.cmd"
        self.assertTrue(wrapper.exists())
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("PYTHONUTF8=1", text)
        self.assertIn("PYTHONIOENCODING=utf-8", text)
        profiles = (PROJECT_ROOT / "config" / "integrations" / "tool_profiles.json").read_text(encoding="utf-8")
        self.assertIn('"command": "vendor/bin/schemathesis.cmd"', profiles)

    def test_docker_fallback_wrappers_are_digest_pinned_and_project_scoped(self):
        expected = {
            "nuclei.cmd": "sha256:582d5546902e67052097cb2d07296c642d50a1afc5e44623cb038845df9a32eb",
            "bbot.cmd": "sha256:0b5c3904e3f3f270e8cd31dd84655317de28064bc380d7fa1fd9b78a7d89a47e",
            "testssl.cmd": "sha256:47d623064463c66ce3b02d37486c75dd1bff8fcef0d9947b37a5051b937ccd69",
        }
        for name, digest in expected.items():
            text = (PROJECT_ROOT / "vendor" / "bin" / name).read_text(encoding="utf-8").lower()
            self.assertIn("docker run --rm", text)
            self.assertIn(digest, text)
            self.assertNotIn(":latest", text)
            self.assertIn("vendor\\docker-state", text)

    def test_zap_wrapper_suppresses_batch_echo_that_corrupts_chinese_paths(self):
        text = (PROJECT_ROOT / "vendor" / "bin" / "zap.cmd").read_text(encoding="utf-8").lower()
        self.assertTrue(text.startswith("@echo off"))
        self.assertIn("zap_2.17.0", text)
        self.assertIn("%zap_home%\\zap.bat", text)


if __name__ == "__main__":
    unittest.main()

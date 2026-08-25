import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class ToolProfileTests(unittest.TestCase):
    def test_curated_profiles_distinguish_scanners_from_discovery_tools(self):
        from src_auto.tool_profiles import load_tool_profiles

        profiles = load_tool_profiles(PROJECT_ROOT / "config" / "integrations" / "tool_profiles.json")

        self.assertEqual(profiles["subfinder"].role, "asset_discovery")
        self.assertFalse(profiles["subfinder"].is_vulnerability_scanner)
        self.assertEqual(profiles["httpx"].role, "http_probe")
        self.assertFalse(profiles["katana"].is_vulnerability_scanner)
        self.assertTrue(profiles["nuclei"].is_vulnerability_scanner)
        self.assertTrue(profiles["zap"].is_vulnerability_scanner)
        self.assertEqual(profiles["schemathesis"].role, "api_schema_testing")
        self.assertEqual(profiles["testssl"].role, "tls_assessment")

    def test_profiles_are_project_local_and_have_explicit_safe_modes(self):
        from src_auto.tool_profiles import load_tool_profiles

        profiles = load_tool_profiles(PROJECT_ROOT / "config" / "integrations" / "tool_profiles.json")

        self.assertGreaterEqual(len(profiles), 9)
        for name, profile in profiles.items():
            self.assertEqual(name, profile.name)
            self.assertTrue(profile.source.startswith("https://"))
            self.assertTrue(profile.allowed_modes)
            self.assertFalse(Path(profile.command).is_absolute(), name)
            self.assertNotIn("..", Path(profile.command).parts)
            self.assertNotIn("bruteforce", profile.allowed_modes)
            self.assertNotIn("dos", profile.allowed_modes)
        self.assertEqual(profiles["bbot"].allowed_modes, ("passive", "easm"))
        self.assertEqual(profiles["nuclei"].allowed_modes, ("reviewed-templates", "passive"))

    def test_project_tool_search_paths_include_isolated_venvs(self):
        from src_auto.tool_profiles import project_tool_search_paths

        paths = project_tool_search_paths(PROJECT_ROOT)
        relative = {path.relative_to(PROJECT_ROOT).as_posix().lower() for path in paths}

        self.assertIn("vendor/bin", relative)
        self.assertIn("vendor/pytools/bbot/scripts", relative)
        self.assertIn("vendor/pytools/schemathesis/scripts", relative)
        self.assertIn("vendor/zap/zap_2.17.0", relative)

    def test_registry_discovers_windows_cmd_wrappers(self):
        from src_auto.adapters import ToolRegistry

        wrapper_dir = PROJECT_ROOT / "vendor" / "test-wrappers"
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        wrapper = wrapper_dir / "sample-tool.cmd"
        try:
            wrapper.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
            registry = ToolRegistry(search_paths=[wrapper_dir])
            self.assertEqual(registry.command_for("sample-tool"), str(wrapper))
        finally:
            if wrapper.exists():
                wrapper.unlink()
            if wrapper_dir.exists():
                wrapper_dir.rmdir()

    def test_cli_uses_shared_project_tool_search_paths(self):
        cli = (PROJECT_ROOT / "src_auto" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("from .tool_profiles import project_tool_search_paths", cli)
        self.assertGreaterEqual(cli.count("project_tool_search_paths(PROJECT_ROOT)"), 2)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class DashboardLauncherTests(unittest.TestCase):
    def test_launcher_accepts_all_current_pages(self):
        content = (PROJECT_ROOT / 'tools/start_dashboard.ps1').read_text(encoding='utf-8-sig')
        first_validate_set = content[content.index('[ValidateSet('):content.index('[string]$InitialPage')]
        for page in ('agent', 'local-app', 'source-audit', 'business-preparation'):
            self.assertIn("'{}'".format(page), first_validate_set)

    def test_launcher_checks_api_compatibility_before_reusing_an_idle_process(self):
        path = PROJECT_ROOT / 'tools/start_dashboard.ps1'
        content = path.read_text(encoding='utf-8-sig')
        self.assertIn('function Test-DashboardApiCompatible', content)
        self.assertIn('$apiMatches = Test-DashboardApiCompatible $existingApiHealth', content)
        self.assertIn('-or -not $apiMatches', content)
        command = """
        $tokens=$null; $errors=$null
        $ast=[Management.Automation.Language.Parser]::ParseFile('%s',[ref]$tokens,[ref]$errors)
        $function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-DashboardApiCompatible'},$true)
        . ([scriptblock]::Create($function.Extent.Text))
        $results=@(
          (Test-DashboardApiCompatible ([pscustomobject]@{})),
          (Test-DashboardApiCompatible ([pscustomobject]@{serviceApiVersion=1;capabilities=@('business-preparation-v1')})),
          (Test-DashboardApiCompatible ([pscustomobject]@{serviceApiVersion=2;capabilities=@()})),
          (Test-DashboardApiCompatible ([pscustomobject]@{serviceApiVersion=2;capabilities=@('business-preparation-v1')})),
          (Test-DashboardApiCompatible ([pscustomobject]@{serviceApiVersion=3;capabilities=@('business-preparation-v1','business-execution-v1')})),
          (Test-DashboardApiCompatible ([pscustomobject]@{serviceApiVersion=2;capabilities='business-preparation-v1'}))
        ); ConvertTo-Json -InputObject $results -Compress
        """ % str(path).replace("'", "''")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        self.assertEqual(json.loads(result.stdout.decode('utf-8-sig')), [False, False, False, False, True, False])

    def test_dashboard_launcher_is_present_and_loopback_only(self):
        path = PROJECT_ROOT / "tools" / "start_dashboard.ps1"
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("127.0.0.1", content)
        self.assertIn("dashboard", content.lower())
        self.assertIn("node-v22.23.0-win-x64", content)
        self.assertNotIn("0.0.0.0", content)
        self.assertNotIn("https://", content.lower())
        self.assertNotIn("http://", content.lower().replace("http://127.0.0.1", ""))

    def test_dashboard_launcher_does_not_overwrite_runtime_data(self):
        path = PROJECT_ROOT / "tools" / "start_dashboard.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("dist", content.lower())
        self.assertIn("npm", content.lower())
        self.assertNotIn("Remove-Item", content)
        self.assertNotIn("git reset", content.lower())
        self.assertNotIn("config\\secrets", content.lower())

    def test_dashboard_launcher_starts_loopback_control_api(self):
        path = PROJECT_ROOT / "tools" / "start_dashboard.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("[int]$ApiPort = 4174", content)
        self.assertIn("src_auto.dashboard_server", content)
        self.assertIn("dashboard-api.stdout.log", content)
        self.assertIn("/health", content)
        self.assertIn("127.0.0.1:$ApiPort", content)
        self.assertNotIn("--host 0.0.0.0", content)

    def test_dashboard_launcher_uses_prebuilt_static_server_without_vite_runtime(self):
        path = PROJECT_ROOT / "tools" / "start_dashboard.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("src_auto.dashboard_web", content)
        self.assertIn("dashboard-web.stdout.log", content)
        self.assertNotIn("$arguments = @($viteEntry", content)
        self.assertIn("if(-not (Test-Path -LiteralPath $DistIndex))", content)

    def test_vite_proxies_only_api_to_fixed_loopback_port(self):
        content = (PROJECT_ROOT / "dashboard" / "vite.config.ts").read_text(encoding="utf-8")
        self.assertIn("'/api'", content)
        self.assertIn("http://127.0.0.1:4174", content)
        self.assertNotIn("0.0.0.0", content)

    def test_start_system_has_explicit_dashboard_switch_before_legacy_gui(self):
        path = PROJECT_ROOT / "START_SYSTEM.ps1"
        content = path.read_text(encoding="utf-8-sig")
        self.assertIn("[switch]$Dashboard", content)
        self.assertIn("[switch]$LegacyGui", content)
        dashboard_branch = content.index("$Dashboard")
        legacy_branch = content.index("src_auto_gui.ps1")
        self.assertLess(dashboard_branch, legacy_branch)
        self.assertIn("start_dashboard.ps1", content)


if __name__ == "__main__":
    unittest.main()

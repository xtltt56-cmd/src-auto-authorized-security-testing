import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
GUI_SCRIPT = PROJECT_ROOT / "tools" / "src_auto_gui.ps1"
TARGET_CONFIG_SCRIPT = PROJECT_ROOT / "tools" / "target_config.ps1"
SESSION_GUI_SCRIPT = PROJECT_ROOT / "tools" / "session_profile_gui.ps1"
LAUNCHER = PROJECT_ROOT / "START_SYSTEM.ps1"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
CI_NONINTERACTIVE = os.environ.get("CI", "").lower() == "true"


def _quote(value):
    return "'{}'".format(str(value).replace("'", "''"))


def _run_powershell(command):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-Sta",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=str(PROJECT_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


class DesktopGuiContractTests(unittest.TestCase):
    def _run_gui_probe(self, probe):
        command = (
            "$source = [IO.File]::ReadAllText({path}, [Text.Encoding]::UTF8); "
            "$source = $source.Replace('$PSScriptRoot', {tools}); "
            "$source = $source -replace '(?m)^Show-SrcAutoMainWindow\\s*$', ''; "
            "$probe = @'\n{probe}\n'@; "
            "& ([ScriptBlock]::Create($source + [Environment]::NewLine + $probe))"
        ).format(
            path=_quote(GUI_SCRIPT),
            tools=_quote(GUI_SCRIPT.parent),
            probe=probe,
        )
        return _run_powershell(command)

    def _run_session_gui_probe(self, probe):
        command = (
            "$source = [IO.File]::ReadAllText({path}, [Text.Encoding]::UTF8); "
            "$source = $source.Replace('$PSScriptRoot', {tools}); "
            "$source = $source -replace '(?m)^Show-SessionProfileManager\\s*$', ''; "
            "$probe = @'\n{probe}\n'@; "
            "& ([ScriptBlock]::Create($source + [Environment]::NewLine + $probe))"
        ).format(
            path=_quote(SESSION_GUI_SCRIPT),
            tools=_quote(GUI_SCRIPT.parent),
            probe=probe,
        )
        return _run_powershell(command)

    def test_gui_scripts_are_utf8_bom_encoded(self):
        self.assertTrue(GUI_SCRIPT.exists(), "the Chinese desktop GUI script must exist")
        self.assertTrue(TARGET_CONFIG_SCRIPT.exists(), "target configuration helpers must exist")
        self.assertTrue(GUI_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue(TARGET_CONFIG_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_gui_contains_concise_chinese_menu_and_no_scanner_path(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for label in (
            "本地靶场检测",
            "新建授权目标",
            "选择已有目标",
            "离线审阅目标范围",
            "查看 Findings 和报告",
            "AI 模型与密钥设置",
            "默认仅本机回环靶场",
        ):
            self.assertIn(label, content)
        self.assertIn("System.Windows.Forms", content)
        self.assertNotIn("run-live", content.lower())
        self.assertNotIn("--execute-live", content.lower())
        self.assertNotIn("invoke-webrequest", content.lower())
        self.assertNotIn("httpx", content.lower())
        self.assertNotIn("katana", content.lower())
        self.assertNotIn("zap", content.lower())

    def test_gui_uses_dpi_aware_crisp_text_rendering(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for required in (
            "SetProcessDPIAware",
            "$label.UseCompatibleTextRendering = $false",
            "$button.UseCompatibleTextRendering = $false",
            "AutoScaleMode]::Dpi",
        ):
            self.assertIn(required, content)

    @unittest.skipIf(CI_NONINTERACTIVE, "需要交互式 Windows 桌面会话")
    def test_dpi_aware_main_window_scales_from_96_dpi_design_baseline(self):
        """At 200% DPI, fonts and fixed controls must grow by the same factor."""
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        self.assertIn("AutoScaleDimensions = New-Object System.Drawing.SizeF(96, 96)", content)
        self.assertIn("function Enable-SrcAutoDpiLayout", content)
        self.assertEqual(content.count("Enable-SrcAutoDpiLayout -Form $form"), 4)
        provider_ui = (GUI_SCRIPT.parent / 'ai_provider_settings_gui.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('AutoScaleDimensions = New-Object System.Drawing.SizeF(96, 96)', provider_ui)
        probe = (
            "$script:DpiLayoutCheck = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $main = [System.Windows.Forms.Application]::OpenForms | Select-Object -First 1\n"
            "    if(-not $main) { return }\n"
            "    $scale = [double]$main.DeviceDpi / 96.0\n"
            "    $minimumWidth = [int][Math]::Floor(1180 * $scale * 0.98)\n"
            "    $minimumHeight = [int][Math]::Floor(730 * $scale * 0.98)\n"
            "    $sidebar = $main.Controls | Where-Object { $_ -is [System.Windows.Forms.Panel] -and $_.Left -eq 0 -and $_.Top -eq 0 } | Select-Object -First 1\n"
            "    $brand = $sidebar.Controls | Where-Object { $_ -is [System.Windows.Forms.Label] } | Sort-Object { $_.Font.Size } -Descending | Select-Object -First 1\n"
            "    $minimumSidebarWidth = [int][Math]::Floor(208 * $scale * 0.98)\n"
            "    $minimumBrandWidth = [int][Math]::Floor(160 * $scale * 0.98)\n"
            "    if($main.ClientSize.Width -lt $minimumWidth -or $main.ClientSize.Height -lt $minimumHeight -or -not $sidebar -or $sidebar.Width -lt $minimumSidebarWidth -or -not $brand -or $brand.Width -lt $minimumBrandWidth) {\n"
            "        $script:DpiLayoutError = ('main_controls_not_scaled_' + $main.DeviceDpi + '_' + $main.ClientSize.Width + 'x' + $main.ClientSize.Height)\n"
            "    }\n"
            "    $script:DpiLayoutCheck = $true\n"
            "    $main.Close(); $timer.Stop()\n"
            "})\n"
            "$timer.Start(); Show-SrcAutoMainWindow\n"
            "if($script:DpiLayoutError) { throw $script:DpiLayoutError }\n"
            "if(-not $script:DpiLayoutCheck) { throw 'main_dpi_layout_probe_never_completed' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_offline_review_uses_folder_first_safe_picker_contract(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for required in (
            "Show-OfflineReviewPicker",
            "offlineReviewPath",
            "offlineTargetList",
            "项目目标根",
            "上一级",
            "选择文件夹",
            "刷新",
            "开始离线审阅",
            "scope_confirmed.yaml",
            "live_plan.yaml",
            "config\\targets",
            "Get-OfflineReviewTargets",
            "候选 Scope（不可审阅）",
            "缺少 live_plan.yaml",
            "actionable",
        ):
            self.assertIn(required, content)
        self.assertIn("--confirm-selection", content)
        self.assertNotIn("--execute-live", content.lower())
        self.assertNotIn("run-live", content.lower())

    def test_offline_batch_review_is_sequential_local_and_summarized(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for required in (
            "Invoke-OfflineTargetReviewResult",
            "Invoke-OfflineReviewBatch",
            "Write-OfflineReviewBatchSummary",
            "--json",
            "network_contact = $false",
            "不同目标的授权范围不会合并",
        ):
            self.assertIn(required, content)
        self.assertNotIn("--execute-live", content.lower())

    def test_offline_batch_invokes_each_selected_target_once(self):
        probe = (
            "$fixtureRoot = Join-Path (Get-OfflineTargetsRoot) ('__gui_batch_test_' + [guid]::NewGuid().ToString('N'))\n"
            "try {\n"
            "    foreach($name in @('target-a','target-b')) {\n"
            "        $dir = Join-Path $fixtureRoot $name\n"
            "        [IO.Directory]::CreateDirectory($dir) | Out-Null\n"
            "        [IO.File]::WriteAllText((Join-Path $dir 'scope_confirmed.yaml'), 'target: test', [Text.Encoding]::UTF8)\n"
            "        [IO.File]::WriteAllText((Join-Path $dir 'live_plan.yaml'), 'plan: offline', [Text.Encoding]::UTF8)\n"
            "    }\n"
            "    $available = @(Get-OfflineReviewTargets -SelectedPath $fixtureRoot)\n"
            "    if($available.Count -ne 2) { throw 'offline_batch_fixture_targets_missing' }\n"
            "    $script:BatchCalls = @()\n"
            "    $runner = { param($scope, $plan)\n"
            "        $script:BatchCalls += ($scope + '|' + $plan)\n"
            "        [pscustomobject]@{ status = 'selection_reviewed'; reason = 'selection_confirmed'; exit_code = 0 }\n"
            "    }\n"
            "    $results = @(Invoke-OfflineReviewBatch -Targets $available -ReviewInvoker $runner)\n"
            "    if($script:BatchCalls.Count -ne 2) { throw 'offline_batch_call_count_wrong' }\n"
            "    if($results.Count -ne 2) { throw 'offline_batch_result_count_wrong' }\n"
            "    if(@($results | Where-Object { $_.display_status -ne '通过' }).Count -ne 0) { throw 'offline_batch_status_wrong' }\n"
            "    $none = @(Invoke-OfflineReviewBatch -Targets @() -ReviewInvoker $runner)\n"
            "    if($none.Count -ne 0 -or $script:BatchCalls.Count -ne 2) { throw 'offline_batch_cancel_invoked_runner' }\n"
            "} finally {\n"
            "    $verified = Assert-OfflineReviewDirectory -Path $fixtureRoot\n"
            "    if(-not $verified.StartsWith((Get-OfflineTargetsRoot) + '\\')) { throw 'unsafe_fixture_cleanup' }\n"
            "    [IO.Directory]::Delete($verified, $true)\n"
            "}"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_offline_review_process_returns_json_without_network_execution(self):
        targets_root = PROJECT_ROOT / "config" / "targets"
        with tempfile.TemporaryDirectory(dir=str(targets_root)) as raw:
            target_dir = Path(raw)
            scope_path = target_dir / "scope_confirmed.yaml"
            plan_path = target_dir / "live_plan.yaml"
            scope_path.write_text(
                json.dumps(
                    {
                        "target_id": "gui-offline-review-test",
                        "root_domains": [],
                        "allowed_hosts": ["127.0.0.1"],
                        "excluded_hosts": [],
                        "allowed_ports": [3000],
                        "confirmed": True,
                        "allow_network_contact": True,
                    }
                ),
                encoding="utf-8",
            )
            plan_path.write_text(
                json.dumps(
                    {
                        "name": "gui-offline-review-test",
                        "operator": "test-operator",
                        "authorization_note": "local fixture only",
                        "manual_execution_confirmed": True,
                        "target_urls": ["http://127.0.0.1:3000/"],
                        "sequence": ["httpx"],
                        "commands": {
                            "httpx": ["-silent", "-u", "http://127.0.0.1:3000/"]
                        },
                    }
                ),
                encoding="utf-8",
            )
            probe = (
                "$result = Invoke-OfflineTargetReviewResult -ScopePath {scope} -PlanPath {plan}\n"
                "if($result.status -ne 'selection_reviewed') {{ throw ('offline_review_status_' + $result.status) }}\n"
                "if($result.exit_code -ne 0) {{ throw 'offline_review_exit_code_wrong' }}"
            ).format(scope=_quote(scope_path), plan=_quote(plan_path))
            result = self._run_gui_probe(probe)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_start_system_dispatches_to_gui_but_keeps_local_switch(self):
        content = LAUNCHER.read_text(encoding="utf-8-sig")
        self.assertIn("RunLocalLab", content)
        self.assertIn("tools\\src_auto_gui.ps1", content)
        self.assertIn("仅本机回环靶场，不接触真实目标", content)
        self.assertLess(content.index("RunLocalLab"), content.index("src_auto new"))

    def test_button_click_can_resolve_functions_from_gui_script_scope(self):
        probe = (
            "$script:GuiClickProbe = $false\n"
            "function Invoke-GuiClickProbe { $script:GuiClickProbe = $true }\n"
            "$form = New-Object System.Windows.Forms.Form\n"
            "$form.ShowInTaskbar = $false; $form.Opacity = 0\n"
            "$button = New-GuiButton -Text 'probe' -Left 0 -Top 0 "
            "-Action { Invoke-GuiClickProbe }\n"
            "$form.Controls.Add($button); $form.Show()\n"
            "[System.Windows.Forms.Application]::DoEvents()\n"
            "$button.PerformClick(); [System.Windows.Forms.Application]::DoEvents()\n"
            "if(-not $script:GuiClickProbe) { throw 'gui_click_handler_not_invoked' }\n"
            "$form.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_target_wizard_can_open_and_close_without_runtime_errors(self):
        probe = (
            "$script:TargetWizardSeen = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $wizard = [System.Windows.Forms.Application]::OpenForms | "
            "Where-Object { $_.Text -eq 'SRC-Auto - 新建补天授权目标' }\n"
            "    if($wizard) {\n"
            "        $cancel = $wizard.Controls | "
            "Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '取消' } | "
            "Select-Object -First 1\n"
            "        if(-not $cancel) { throw 'target_wizard_cancel_button_missing' }\n"
            "        $script:TargetWizardSeen = $true\n"
            "        $cancel.PerformClick(); $timer.Stop()\n"
            "    }\n"
            "})\n"
            "$timer.Start(); Show-TargetWizard\n"
            "if(-not $script:TargetWizardSeen) { throw 'target_wizard_never_opened' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_ai_settings_routes_to_the_inline_dashboard_page(self):
        content = GUI_SCRIPT.read_text(encoding='utf-8-sig')
        function = content[content.index('function Open-AISettings'):content.index('function Open-SessionProfileManager')]
        self.assertIn("tools\\start_dashboard.ps1", function)
        self.assertIn("'-InitialPage','settings'", function)
        self.assertNotIn('ai_provider_settings_gui.ps1', function)

    def test_ai_settings_has_direct_paste_and_official_default_actions(self):
        content = (GUI_SCRIPT.parent / 'ai_provider_settings_gui.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("'粘贴剪贴板密钥'", content)
        self.assertIn("'恢复官方默认模型'", content)
        self.assertIn('[Windows.Forms.Clipboard]::GetText()', content)
        self.assertIn('$keyBox.Focus()', content)

    def test_offline_review_picker_can_open_and_close_with_navigation_controls(self):
        probe = (
            "$script:OfflinePickerSeen = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $window = [System.Windows.Forms.Application]::OpenForms | "
            "Where-Object { $_.Text -eq 'SRC-Auto - 离线审阅目标范围' }\n"
            "    if($window) {\n"
            "        $path = $window.Controls | Where-Object { $_.Name -eq 'offlineReviewPath' } | Select-Object -First 1\n"
            "        $list = $window.Controls | Where-Object { $_.Name -eq 'offlineTargetList' } | Select-Object -First 1\n"
            "        $cancel = $window.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '取消' } | Select-Object -First 1\n"
            "        $root = $window.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '项目目标根' } | Select-Object -First 1\n"
            "        $up = $window.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '上一级' } | Select-Object -First 1\n"
            "        if(-not $path -or -not $list -or -not $cancel -or -not $root -or -not $up) { throw 'offline_picker_controls_missing' }\n"
            "        if($list.Items.Count -lt 1) { throw 'offline_picker_did_not_show_existing_scopes' }\n"
            "        $script:OfflinePickerSeen = $true\n"
            "        $cancel.PerformClick(); $timer.Stop()\n"
            "    }\n"
            "})\n"
            "$timer.Start(); Show-OfflineReviewPicker\n"
            "if(-not $script:OfflinePickerSeen) { throw 'offline_picker_never_opened' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_home_screen_has_guided_chinese_navigation_and_safety_summary(self):
        content = GUI_SCRIPT.read_text(encoding="utf-8-sig")
        for label in (
            "快速开始",
            "目标与授权",
            "本地靶场",
            "结果与报告",
            "安全状态",
            "仅本机回环靶场",
            "真实目标不会自动执行",
        ):
            self.assertIn(label, content)

    def test_local_lab_dashboard_can_open_and_close_without_starting_a_lab(self):
        probe = (
            "$script:LabDashboardSeen = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $window = [System.Windows.Forms.Application]::OpenForms | "
            "Where-Object { $_.Text -eq 'SRC-Auto - 本地靶场与回归验证' }\n"
            "    if($window) {\n"
            "        $start = $window.Controls | "
            "Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '启动本地靶场' } | "
            "Select-Object -First 1\n"
            "        $close = $window.Controls | "
            "Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '返回主页' } | "
            "Select-Object -First 1\n"
            "        if(-not $start -or -not $close) { throw 'local_lab_dashboard_controls_missing' }\n"
            "        $script:LabDashboardSeen = $true\n"
            "        $close.PerformClick(); $timer.Stop()\n"
            "    }\n"
            "})\n"
            "$timer.Start(); Show-LocalLabDashboard\n"
            "if(-not $script:LabDashboardSeen) { throw 'local_lab_dashboard_never_opened' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_audit_stop_button_is_real_and_sets_project_stop_marker(self):
        marker = PROJECT_ROOT / "STOP"
        probe = (
            "$marker = {marker}\n"
            "if(Test-Path -LiteralPath $marker) {{ Remove-Item -LiteralPath $marker -Force }}\n"
            "$script:AuditStopSeen = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({{\n"
            "    $window = [System.Windows.Forms.Application]::OpenForms | Select-Object -First 1\n"
            "    if(-not $window) {{ return }}\n"
            "    $stop = $window.Controls | Where-Object {{ $_ -is [System.Windows.Forms.Button] }} | Select-Object -First 1\n"
            "    if(-not $stop) {{ throw 'audit_stop_button_missing' }}\n"
            "    $script:AuditStopSeen = $true\n"
            "    $stop.PerformClick(); $timer.Stop()\n"
            "}})\n"
            "$timer.Start(); Show-AuditSettingsWindow\n"
            "if(-not $script:AuditStopSeen) {{ throw 'audit_stop_button_not_clicked' }}\n"
            "if(-not (Test-Path -LiteralPath $marker)) {{ throw 'audit_stop_marker_missing' }}\n"
            "Remove-Item -LiteralPath $marker -Force\n"
            "$timer.Dispose()"
        ).format(marker=_quote(marker))
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_main_window_new_target_button_opens_its_guided_form(self):
        probe = (
            "$script:MainClickSeen = $false\n"
            "$script:TargetWizardSeen = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $main = [System.Windows.Forms.Application]::OpenForms | "
            "Where-Object { $_.Text -eq 'SRC-Auto 安全测试控制台' } | Select-Object -First 1\n"
            "    if($main -and -not $script:MainClickSeen) {\n"
            "        $button = $main.Controls | "
            "Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '新建授权目标' } | "
            "Select-Object -First 1\n"
            "        if(-not $button) { throw 'main_target_button_missing' }\n"
            "        $script:MainClickSeen = $true\n"
            "        $button.PerformClick()\n"
            "    }\n"
            "    $wizard = [System.Windows.Forms.Application]::OpenForms | "
            "Where-Object { $_.Text -eq 'SRC-Auto - 新建补天授权目标' } | Select-Object -First 1\n"
            "    if($wizard) {\n"
            "        $cancel = $wizard.Controls | "
            "Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Text -eq '取消' } | "
            "Select-Object -First 1\n"
            "        if(-not $cancel) { throw 'main_target_wizard_cancel_missing' }\n"
            "        $script:TargetWizardSeen = $true\n"
            "        $cancel.PerformClick()\n"
            "        if($main) { $main.Close() }\n"
            "        $timer.Stop()\n"
            "    }\n"
            "})\n"
            "$timer.Start(); Show-SrcAutoMainWindow\n"
            "if(-not $script:MainClickSeen -or -not $script:TargetWizardSeen) { throw 'main_target_button_not_connected' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipIf(CI_NONINTERACTIVE, "需要交互式 Windows 桌面会话")
    def test_main_window_visible_buttons_are_real_mouse_targets(self):
        """A button must be above sibling panels at the point a user clicks."""
        probe = (
            "$script:MouseTargetCheck = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $main = [System.Windows.Forms.Application]::OpenForms | Select-Object -First 1\n"
            "    if(-not $main) { return }\n"
            "    foreach($button in @($main.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Visible -and $_.Enabled })) {\n"
            "        $center = New-Object System.Drawing.Point(($button.Left + [int]($button.Width / 2)), ($button.Top + [int]($button.Height / 2)))\n"
            "        $hit = $main.GetChildAtPoint($center)\n"
            "        if($hit -ne $button) { $script:MouseTargetError = ('main_button_not_topmost_' + $button.Text + '_hit_' + $hit.GetType().Name); break }\n"
            "    }\n"
            "    $script:MouseTargetCheck = $true\n"
            "    $main.Close(); $timer.Stop()\n"
            "})\n"
            "$timer.Start(); Show-SrcAutoMainWindow\n"
            "if($script:MouseTargetError) { throw $script:MouseTargetError }\n"
            "if(-not $script:MouseTargetCheck) { throw 'main_mouse_target_probe_never_completed' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_sidebar_navigation_buttons_are_clickable_and_route_to_features(self):
        probe = (
            "$script:SidebarRoutes = @{}\n"
            "function Show-LocalLabDashboard { $script:SidebarRoutes.local = $true }\n"
            "function Show-TargetWizard { $script:SidebarRoutes.target = $true }\n"
            "function Show-OfflineReviewPicker { $script:SidebarRoutes.offline = $true }\n"
            "function Open-ReportsFolder { $script:SidebarRoutes.reports = $true }\n"
            "function Open-AISettings { $script:SidebarRoutes.ai = $true }\n"
            "$script:SidebarNavigationCheck = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $main = [System.Windows.Forms.Application]::OpenForms | Select-Object -First 1\n"
            "    if(-not $main) { return }\n"
            "    $sidebar = $main.Controls | Where-Object { $_ -is [System.Windows.Forms.Panel] -and $_.Left -eq 0 -and $_.Top -eq 0 } | Select-Object -First 1\n"
            "    $expected = @('navQuickStart','navLocalLab','navTarget','navOffline','navReports','navAI')\n"
            "    $buttons = @($sidebar.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Name -in $expected })\n"
            "    if($buttons.Count -ne 6) { $script:SidebarNavigationError = ('sidebar_navigation_button_count_' + $buttons.Count) }\n"
            "    foreach($button in $buttons) {\n"
            "        $center = New-Object System.Drawing.Point(($button.Left + [int]($button.Width / 2)), ($button.Top + [int]($button.Height / 2)))\n"
            "        if($sidebar.GetChildAtPoint($center) -ne $button) { $script:SidebarNavigationError = ('sidebar_button_not_mouse_target_' + $button.Name); break }\n"
            "    }\n"
            "    if(-not $script:SidebarNavigationError) {\n"
            "        foreach($name in @('navLocalLab','navTarget','navOffline','navReports','navAI')) {\n"
            "            ($buttons | Where-Object { $_.Name -eq $name } | Select-Object -First 1).PerformClick()\n"
            "        }\n"
            "        ($buttons | Where-Object { $_.Name -eq 'navQuickStart' } | Select-Object -First 1).PerformClick()\n"
            "        [System.Windows.Forms.Application]::DoEvents()\n"
            "        if(@($script:SidebarRoutes.Keys).Count -ne 5) { $script:SidebarNavigationError = 'sidebar_routes_not_invoked' }\n"
            "        if(-not $main.ActiveControl -or $main.ActiveControl.Name -ne 'actionLocalLab') { $script:SidebarNavigationError = 'sidebar_quick_start_did_not_focus_first_action' }\n"
            "    }\n"
            "    $script:SidebarNavigationCheck = $true\n"
            "    $main.Close(); $timer.Stop()\n"
            "})\n"
            "$timer.Start(); Show-SrcAutoMainWindow\n"
            "if($script:SidebarNavigationError) { throw $script:SidebarNavigationError }\n"
            "if(-not $script:SidebarNavigationCheck) { throw 'sidebar_navigation_probe_never_completed' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_findings_window_selects_report_and_previews_file_content(self):
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            reports = project_root / "reports"
            validation = project_root / "validation"
            reports.mkdir()
            validation.mkdir()
            (reports / "sample-report.md").write_text(
                "# 本地报告\n\nDETAIL_MARKER_2026\n",
                encoding="utf-8",
            )
            probe = (
                "$ProjectRoot = " + _quote(project_root) + "\n"
                "$script:ReportPreviewCheck = $false\n"
                "$timer = New-Object System.Windows.Forms.Timer\n"
                "$timer.Interval = 100\n"
                "$timer.Add_Tick({\n"
                "    $window = [System.Windows.Forms.Application]::OpenForms | "
                "Where-Object { $_.Text -eq 'SRC-Auto - 发现与报告' } | Select-Object -First 1\n"
                "    if(-not $window) { return }\n"
                "    $list = $window.Controls | Where-Object { $_.Name -eq 'findingsList' } | Select-Object -First 1\n"
                "    $preview = $window.Controls | Where-Object { $_.Name -eq 'reportPreview' } | Select-Object -First 1\n"
                "    if(-not $list) { $script:ReportPreviewError = 'findings_list_missing' }\n"
                "    elseif(-not $preview) { $script:ReportPreviewError = 'report_preview_missing' }\n"
                "    elseif($list.Items.Count -ne 1) { $script:ReportPreviewError = ('unexpected_report_count_' + $list.Items.Count) }\n"
                "    if($script:ReportPreviewError) { $window.Close(); $timer.Stop(); return }\n"
                "    $list.SelectedIndex = 0\n"
                "    [System.Windows.Forms.Application]::DoEvents()\n"
                "    if($preview.Text -notmatch 'DETAIL_MARKER_2026') { $script:ReportPreviewError = ('report_content_not_previewed:' + $preview.Text) }\n"
                "    $script:ReportPreviewCheck = $true\n"
                "    $window.Close(); $timer.Stop()\n"
                "})\n"
                "$timer.Start(); Show-FindingsWindow\n"
                "if($script:ReportPreviewError) { throw $script:ReportPreviewError }\n"
                "if(-not $script:ReportPreviewCheck) { throw 'report_preview_probe_never_completed' }\n"
                "$timer.Dispose()"
            )
            result = self._run_gui_probe(probe)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipIf(CI_NONINTERACTIVE, "需要交互式 Windows 桌面会话")
    def test_main_action_card_text_does_not_run_under_its_button(self):
        """The home cards keep a readable gap above their overlaid actions."""
        probe = (
            "$script:CardLayoutCheck = $false\n"
            "$timer = New-Object System.Windows.Forms.Timer\n"
            "$timer.Interval = 100\n"
            "$timer.Add_Tick({\n"
            "    $main = [System.Windows.Forms.Application]::OpenForms | Select-Object -First 1\n"
            "    if(-not $main) { return }\n"
            "    $scale = [double]$main.ClientSize.Width / 1180.0\n"
            "    $cardTop = [int][Math]::Round(232 * $scale)\n"
            "    $buttonTop = [int][Math]::Round(360 * $scale)\n"
            "    $cards = @($main.Controls | Where-Object { $_ -is [System.Windows.Forms.Panel] -and $_.Top -eq $cardTop })\n"
            "    $buttons = @($main.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] -and $_.Top -eq $buttonTop })\n"
            "    if($cards.Count -ne 3 -or $buttons.Count -ne 3) { $script:CardLayoutError = 'main_action_card_fixture_missing' }\n"
            "    foreach($card in $cards) {\n"
            "        foreach($label in @($card.Controls | Where-Object { $_ -is [System.Windows.Forms.Label] })) {\n"
            "            $labelBounds = New-Object System.Drawing.Rectangle(($card.Left + $label.Left), ($card.Top + $label.Top), $label.Width, $label.Height)\n"
            "            foreach($button in $buttons) {\n"
            "                if($labelBounds.IntersectsWith($button.Bounds)) { $script:CardLayoutError = 'main_card_text_overlaps_action_button'; break }\n"
            "            }\n"
            "            if($script:CardLayoutError) { break }\n"
            "        }\n"
            "        if($script:CardLayoutError) { break }\n"
            "    }\n"
            "    $script:CardLayoutCheck = $true\n"
            "    $main.Close(); $timer.Stop()\n"
            "})\n"
            "$timer.Start(); Show-SrcAutoMainWindow\n"
            "if($script:CardLayoutError) { throw $script:CardLayoutError }\n"
            "if(-not $script:CardLayoutCheck) { throw 'main_action_card_layout_probe_never_completed' }\n"
            "$timer.Dispose()"
        )
        result = self._run_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_session_profile_manager_uses_current_user_dpapi_and_never_lists_values(self):
        content = SESSION_GUI_SCRIPT.read_text(encoding="utf-8-sig")
        self.assertTrue(SESSION_GUI_SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf"))
        for required in (
            "Show-SessionProfileManager",
            "Get-SessionProfiles",
            "Save-SessionProfile",
            "DataProtectionScope]::CurrentUser",
            "SRC-Auto|test-session-v1",
            "config\\sessions",
            "UseSystemPasswordChar",
            "测试会话管理",
        ):
            self.assertIn(required, content)
        self.assertIn("session_profile_gui.ps1", GUI_SCRIPT.read_text(encoding="utf-8-sig"))

    def test_session_profile_manager_writes_a_python_compatible_redacted_profile(self):
        profile_name = "gui-session-{}".format(os.urandom(5).hex())
        header_value = "fixture-session-value"
        probe = (
            "$path = Save-SessionProfile -ProfileName {name} -Role 'peer-user' "
            "-HeaderName 'X-Test-Session' -HeaderValue {value}\n"
            "$listed = @(Get-SessionProfiles | Where-Object {{ $_.name -eq {name} }})\n"
            "if($listed.Count -ne 1) {{ throw 'session_profile_not_listed' }}\n"
            "if($listed[0].PSObject.Properties.Name -contains 'header_value') {{ throw 'session_value_exposed_in_list' }}\n"
            "Write-Output $path"
        ).format(name=_quote(profile_name), value=_quote(header_value))
        result = self._run_session_gui_probe(probe)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        profile_path = Path(result.stdout.strip())
        self.assertTrue(profile_path.exists())
        try:
            from src_auto.session_vault import SessionVault

            loaded = SessionVault(PROJECT_ROOT).load(profile_name)
            self.assertEqual(loaded.role, "peer-user")
            self.assertEqual(dict(loaded.headers), {"X-Test-Session": header_value})
            self.assertNotIn(header_value, profile_path.read_text(encoding="utf-8"))
        finally:
            if profile_path.exists():
                profile_path.unlink()


if __name__ == "__main__":
    unittest.main()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetConfigHelper = Join-Path $PSScriptRoot 'target_config.ps1'
Set-Location -LiteralPath $ProjectRoot

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if(-not ('SrcAutoDpiAwareness' -as [type])) {
    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class SrcAutoDpiAwareness
{
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetProcessDPIAware();
}
'@
}
try {
    # Must run before the first form is created.  A false result simply means
    # the host has already selected a DPI mode, which is also safe to use.
    [void][SrcAutoDpiAwareness]::SetProcessDPIAware()
} catch {}
. $TargetConfigHelper
[System.Windows.Forms.Application]::EnableVisualStyles()

$fontName = 'Microsoft YaHei UI'
$titleColor = [System.Drawing.Color]::FromArgb(20, 74, 126)
$accentColor = [System.Drawing.Color]::FromArgb(30, 136, 229)
$mutedColor = [System.Drawing.Color]::FromArgb(92, 106, 120)
$safeColor = [System.Drawing.Color]::FromArgb(26, 127, 82)
$navColor = [System.Drawing.Color]::FromArgb(13, 48, 82)
$canvasColor = [System.Drawing.Color]::FromArgb(246, 249, 252)
$cardBorderColor = [System.Drawing.Color]::FromArgb(218, 228, 238)
$warningColor = [System.Drawing.Color]::FromArgb(181, 109, 20)

function Enable-SrcAutoDpiLayout {
    param([Parameter(Mandatory = $true)][System.Windows.Forms.Form]$Form)
    # All coordinates use a 96-DPI design baseline. Apply scaling after every
    # nested control exists so the form, panels, labels and buttons grow once.
    $Form.AutoScaleDimensions = New-Object System.Drawing.SizeF(96, 96)
    $Form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi
}

function New-GuiLabel {
    param(
        [string]$Text,
        [int]$Left,
        [int]$Top,
        [int]$Width = 280,
        [int]$Height = 28,
        [int]$Size = 9,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::Black,
        [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular
    )
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point($Left, $Top)
    $label.Size = New-Object System.Drawing.Size($Width, $Height)
    $label.Font = New-Object System.Drawing.Font($fontName, $Size, $Style)
    $label.ForeColor = $Color
    $label.UseCompatibleTextRendering = $false
    $label.AutoEllipsis = $true
    return $label
}

function New-GuiButton {
    param(
        [string]$Text,
        [int]$Left,
        [int]$Top,
        [int]$Width = 360,
        [int]$Height = 54,
        [scriptblock]$Action,
        [System.Drawing.Color]$BackColor = [System.Drawing.Color]::White,
        [System.Drawing.Color]$ForeColor = [System.Drawing.Color]::FromArgb(20, 45, 70)
    )
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Location = New-Object System.Drawing.Point($Left, $Top)
    $button.Size = New-Object System.Drawing.Size($Width, $Height)
    $button.Font = New-Object System.Drawing.Font($fontName, 10, [System.Drawing.FontStyle]::Regular)
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(210, 220, 230)
    $button.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(238, 246, 253)
    $button.FlatAppearance.MouseDownBackColor = [System.Drawing.Color]::FromArgb(222, 237, 249)
    $button.BackColor = $BackColor
    $button.ForeColor = $ForeColor
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    $button.UseVisualStyleBackColor = $false
    $button.UseCompatibleTextRendering = $false
    $button.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    # Keep the caller's PowerShell scope intact.  Event script blocks that are
    # converted into this helper's closure can no longer resolve sibling GUI
    # functions, which turns a clickable button into a terminal error.
    if($Action){ $button.Add_Click($Action) }
    return $button
}

function New-SidebarNavButton {
    param(
        [string]$Name,
        [string]$Text,
        [int]$Top,
        [scriptblock]$Action,
        [bool]$Active = $false
    )
    $background = if($Active){ [System.Drawing.Color]::FromArgb(22, 77, 124) } else { $navColor }
    $button = New-GuiButton -Text $Text -Left 0 -Top $Top -Width 208 -Height 36 -Action $Action -BackColor $background -ForeColor ([System.Drawing.Color]::FromArgb(230, 241, 251))
    $button.Name = $Name
    $button.FlatAppearance.BorderSize = 0
    $button.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(28, 88, 139)
    $button.FlatAppearance.MouseDownBackColor = [System.Drawing.Color]::FromArgb(35, 105, 162)
    $button.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
    $button.Padding = New-Object System.Windows.Forms.Padding(26, 0, 0, 0)
    if($Active){
        $button.Font = New-Object System.Drawing.Font($fontName, 10, [System.Drawing.FontStyle]::Bold)
    }
    return $button
}

function Show-Info {
    param([string]$Text, [string]$Title = 'SRC-Auto')
    [System.Windows.Forms.MessageBox]::Show(
        $Text,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}

function Show-Warning {
    param([string]$Text, [string]$Title = '需要确认')
    [System.Windows.Forms.MessageBox]::Show(
        $Text,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
}

function Invoke-OfflineTargetReview {
    param(
        [Parameter(Mandatory = $true)][string]$ScopePath,
        [Parameter(Mandatory = $true)][string]$PlanPath
    )
    try {
        $result = Invoke-OfflineTargetReviewResult -ScopePath $ScopePath -PlanPath $PlanPath
        if($result.status -eq 'selection_reviewed'){
            Show-Info '离线审阅已完成。此过程没有访问目标网站，也没有授予网络执行权限。' '离线审阅完成'
        } else {
            Show-Warning ('离线审阅未通过：' + [string]$result.reason) '离线审阅已阻止'
        }
    } catch {
        Show-Warning '离线审阅失败。请检查 Scope、计划文件和 Python 环境；没有发起网络请求。' '离线审阅失败'
    }
}

function Start-LocalLabWindow {
    $launcher = Join-Path $ProjectRoot 'START_SYSTEM.ps1'
    if(-not (Test-Path -LiteralPath $launcher)){
        Show-Warning '找不到本地靶场启动脚本。'
        return
    }
    Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', $launcher, '-RunLocalLab') -WorkingDirectory $ProjectRoot | Out-Null
    Show-Info '本地靶场已在独立终端窗口启动。`r`n`r`n该流程只使用 127.0.0.1 回环地址，不会进入真实目标流程。'
}

function New-LabGuideCard {
    param(
        [string]$Title,
        [string]$Address,
        [string]$Description,
        [int]$Left,
        [int]$Top,
        [int]$Width = 292
    )
    $card = New-Object System.Windows.Forms.Panel
    $card.Location = New-Object System.Drawing.Point($Left, $Top)
    $card.Size = New-Object System.Drawing.Size($Width, 150)
    $card.BackColor = [System.Drawing.Color]::White
    $card.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $card.Controls.Add((New-GuiLabel -Text $Title -Left 18 -Top 16 -Width ($Width - 36) -Height 28 -Size 12 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $card.Controls.Add((New-GuiLabel -Text $Address -Left 18 -Top 52 -Width ($Width - 36) -Height 24 -Size 9 -Color $safeColor -Style ([System.Drawing.FontStyle]::Bold)))
    $card.Controls.Add((New-GuiLabel -Text $Description -Left 18 -Top 82 -Width ($Width - 36) -Height 50 -Size 9 -Color $mutedColor))
    return $card
}

function Show-LocalLabDashboard {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto - 本地靶场与回归验证'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = New-Object System.Drawing.Size(1010, 650)
    $form.MinimumSize = New-Object System.Drawing.Size(1010, 650)
    $form.BackColor = $canvasColor

    $header = New-Object System.Windows.Forms.Panel
    $header.Location = New-Object System.Drawing.Point(0, 0)
    $header.Size = New-Object System.Drawing.Size(1010, 120)
    $header.BackColor = $titleColor
    $form.Controls.Add($header)
    $header.Controls.Add((New-GuiLabel -Text '本地靶场与回归验证' -Left 34 -Top 22 -Width 480 -Height 38 -Size 19 -Color ([System.Drawing.Color]::White) -Style ([System.Drawing.FontStyle]::Bold)))
    $header.Controls.Add((New-GuiLabel -Text '只绑定 127.0.0.1，用于熟悉流程、验证界面和回归测试。' -Left 36 -Top 65 -Width 600 -Height 28 -Size 10 -Color ([System.Drawing.Color]::FromArgb(220, 235, 250))))
    $header.Controls.Add((New-GuiLabel -Text '不会连接真实目标' -Left 760 -Top 28 -Width 205 -Height 25 -Size 10 -Color ([System.Drawing.Color]::FromArgb(255, 231, 170)) -Style ([System.Drawing.FontStyle]::Bold)))
    $header.Controls.Add((New-GuiLabel -Text '状态：等待人工启动' -Left 760 -Top 59 -Width 205 -Height 25 -Size 9 -Color ([System.Drawing.Color]::White)))

    $form.Controls.Add((New-GuiLabel -Text '建议按以下顺序完成首次验证' -Left 34 -Top 145 -Width 450 -Height 30 -Size 13 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-GuiLabel -Text '1. 启动本地靶场  2. 在浏览器打开对应回环地址  3. 仅在靶场内练习并查看本地结果。' -Left 34 -Top 177 -Width 900 -Height 26 -Size 9 -Color $mutedColor))

    $form.Controls.Add((New-LabGuideCard -Title 'Juice Shop' -Address '127.0.0.1:3000' -Description '面向 Web 应用安全练习的本地靶场。' -Left 34 -Top 220 -Width 216))
    $form.Controls.Add((New-LabGuideCard -Title 'DVWA' -Address '127.0.0.1:8081' -Description '用于常见 Web 输入与会话安全验证。' -Left 266 -Top 220 -Width 216))
    $form.Controls.Add((New-LabGuideCard -Title 'WebGoat' -Address '127.0.0.1:8082' -Description '带有课程式说明的本地安全学习环境。' -Left 498 -Top 220 -Width 216))
    $form.Controls.Add((New-LabGuideCard -Title 'VAmPI' -Address '127.0.0.1:8083' -Description '本地业务 API 靶场，用于对象授权与接口契约练习。' -Left 730 -Top 220 -Width 246))

    $guide = New-Object System.Windows.Forms.Panel
    $guide.Location = New-Object System.Drawing.Point(34, 395)
    $guide.Size = New-Object System.Drawing.Size(942, 102)
    $guide.BackColor = [System.Drawing.Color]::FromArgb(233, 246, 238)
    $guide.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $guide.Controls.Add((New-GuiLabel -Text '操作提示' -Left 18 -Top 13 -Width 120 -Height 24 -Size 10 -Color $safeColor -Style ([System.Drawing.FontStyle]::Bold)))
    $guide.Controls.Add((New-GuiLabel -Text '靶场未启动时，先点击“启动本地靶场”。启动终端会保留在前台，便于查看启动状态；本窗口不执行任何真实目标操作。' -Left 18 -Top 41 -Width 900 -Height 24 -Size 9 -Color $safeColor))
    $guide.Controls.Add((New-GuiLabel -Text '完成练习后，可从“查看 Findings 和报告”打开项目内的本地结果文件。' -Left 18 -Top 68 -Width 900 -Height 22 -Size 9 -Color $safeColor))
    $form.Controls.Add($guide)

    $startButton = New-GuiButton -Text '启动本地靶场' -Left 34 -Top 540 -Width 190 -Height 46 -Action { Start-LocalLabWindow } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $reportButton = New-GuiButton -Text '查看本地报告' -Left 236 -Top 540 -Width 170 -Height 46 -Action { Open-ReportsFolder }
    $closeButton = New-GuiButton -Text '返回主页' -Left 806 -Top 540 -Width 170 -Height 46 -Action { $form.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)
    $form.Controls.Add($startButton)
    $form.Controls.Add($reportButton)
    $form.Controls.Add($closeButton)
    $form.CancelButton = $closeButton
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

function Open-ReportsFolder {
    $reports = Join-Path $ProjectRoot 'reports'
    $reports = Assert-TargetProjectPath -Path $reports -ProjectRoot $ProjectRoot
    if(-not (Test-Path -LiteralPath $reports)){ [System.IO.Directory]::CreateDirectory($reports) | Out-Null }
    Start-Process -FilePath 'explorer.exe' -ArgumentList @($reports) | Out-Null
}

function Save-TargetFromForm {
    param(
        [hashtable]$Controls,
        [bool]$AsReviewedPlan
    )
    $targetId = $Controls.targetId.Text.Trim().ToLowerInvariant()
    $hosts = @($Controls.allowedHosts.Text -split '[,;\r\n]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim().ToLowerInvariant() })
    $excluded = @($Controls.excludedHosts.Text -split '[,;\r\n]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim().ToLowerInvariant() })
    $roots = @($Controls.rootDomains.Text -split '[,;\r\n]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim().ToLowerInvariant() })
    $ports = @($Controls.allowedPorts.Text -split '[,;\r\n]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim() })
    $draft = [pscustomobject]@{
        target_id = $targetId
        vendor = $Controls.vendor.Text.Trim()
        authorization_source = $Controls.authorizationSource.Text.Trim()
        target_url = $Controls.targetUrl.Text.Trim()
        root_domains = $roots
        allowed_hosts = $hosts
        excluded_hosts = $excluded
        allowed_ports = $ports
        test_window = $Controls.testWindow.Text.Trim()
        operator = $Controls.operator.Text.Trim()
        confirmed = [bool]$AsReviewedPlan
        allow_network_contact = [bool]$AsReviewedPlan
        manual_execution_confirmed = $false
    }
    $check = Test-TargetDraft -Draft $draft
    if(-not $check.valid){
        Show-Warning ("目标配置未通过校验：`r`n`r`n" + (($check.errors | Select-Object -Unique) -join "`r`n")) '无法保存目标'
        return $false
    }
    if($AsReviewedPlan -and (-not $Controls.scopeConfirmed.Checked -or -not $Controls.automationAllowed.Checked)){
        Show-Warning '只有同时勾选“已人工核对补天规则”和“平台明确允许低频自动化测试”，才能生成已确认的 Scope。'
        return $false
    }
    try {
        $written = Write-TargetConfig -Draft $draft -ProjectRoot $ProjectRoot
        if($AsReviewedPlan){
            Show-Info ("已保存授权范围，并准备进行离线审阅。`r`n`r`nScope：{0}`r`n计划：{1}`r`n`r`n此步骤不访问目标网站。" -f $written.scope_path, $written.plan_path) '保存成功'
            Invoke-OfflineTargetReview -ScopePath $written.scope_path -PlanPath $written.plan_path
        } else {
            Show-Info ("草稿已保存，未启用网络访问。`r`n`r`nScope：{0}`r`n计划：{1}" -f $written.scope_path, $written.plan_path) '草稿已保存'
        }
        return $true
    } catch {
        Show-Warning '写入目标配置失败。没有发起网络请求，也没有启动任何外部工具。' '保存失败'
        return $false
    }
}

function New-FormTextBox {
    param([System.Windows.Forms.Form]$Form, [string]$LabelText, [string]$Name, [int]$Top, [string]$Default = '', [bool]$Multiline = $false)
    $label = New-GuiLabel -Text $LabelText -Left 28 -Top $Top -Width 205 -Height 24 -Size 9 -Color $mutedColor
    $box = New-Object System.Windows.Forms.TextBox
    $box.Name = $Name
    $box.Text = $Default
    $box.Location = New-Object System.Drawing.Point(238, ($Top - 3))
    $box.Size = New-Object System.Drawing.Size(570, $(if($Multiline){58}else{27}))
    $box.Font = New-Object System.Drawing.Font($fontName, 9)
    $box.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $box.Multiline = $Multiline
    $box.ScrollBars = if($Multiline){[System.Windows.Forms.ScrollBars]::Vertical}else{[System.Windows.Forms.ScrollBars]::None}
    $Form.Controls.Add($label)
    $Form.Controls.Add($box)
    return $box
}

function Show-TargetWizard {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto - 新建补天授权目标'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = New-Object System.Drawing.Size(850, 720)
    $form.MinimumSize = New-Object System.Drawing.Size(850, 720)
    $form.BackColor = [System.Drawing.Color]::White
    $form.AutoScroll = $true

    $form.Controls.Add((New-GuiLabel -Text '新建补天授权目标' -Left 28 -Top 20 -Width 500 -Height 34 -Size 17 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-GuiLabel -Text '仅保存你已核对的授权范围；保存和离线审阅都不会访问目标网站。' -Left 30 -Top 58 -Width 760 -Height 28 -Size 9 -Color $safeColor))

    $controls = @{}
    $controls.targetId = New-FormTextBox -Form $form -LabelText '项目代号（小写英文）' -Name 'targetId' -Top 100
    $controls.vendor = New-FormTextBox -Form $form -LabelText '厂商 / 项目名称' -Name 'vendor' -Top 140
    $controls.authorizationSource = New-FormTextBox -Form $form -LabelText '授权来源 / 项目编号' -Name 'authorizationSource' -Top 180
    $controls.targetUrl = New-FormTextBox -Form $form -LabelText '起始网址（HTTPS）' -Name 'targetUrl' -Top 220
    $controls.rootDomains = New-FormTextBox -Form $form -LabelText '根域名（逗号或换行）' -Name 'rootDomains' -Top 260
    $controls.allowedHosts = New-FormTextBox -Form $form -LabelText '允许主机（逐项填写）' -Name 'allowedHosts' -Top 300 -Multiline $true
    $controls.excludedHosts = New-FormTextBox -Form $form -LabelText '排除主机（可选）' -Name 'excludedHosts' -Top 370 -Multiline $true
    $controls.allowedPorts = New-FormTextBox -Form $form -LabelText '允许端口（默认 443）' -Name 'allowedPorts' -Top 440 -Default '443'
    $controls.testWindow = New-FormTextBox -Form $form -LabelText '允许测试时间窗口' -Name 'testWindow' -Top 480
    $controls.operator = New-FormTextBox -Form $form -LabelText '操作者' -Name 'operator' -Top 520

    $scopeConfirmed = New-Object System.Windows.Forms.CheckBox
    $scopeConfirmed.Text = '我已人工核对补天项目规则、资产归属和排除项'
    $scopeConfirmed.Location = New-Object System.Drawing.Point(238, 560)
    $scopeConfirmed.Size = New-Object System.Drawing.Size(570, 26)
    $scopeConfirmed.Font = New-Object System.Drawing.Font($fontName, 9)
    $form.Controls.Add($scopeConfirmed)
    $controls.scopeConfirmed = $scopeConfirmed

    $automationAllowed = New-Object System.Windows.Forms.CheckBox
    $automationAllowed.Text = '项目规则明确允许低频、非破坏性自动化测试'
    $automationAllowed.Location = New-Object System.Drawing.Point(238, 590)
    $automationAllowed.Size = New-Object System.Drawing.Size(570, 26)
    $automationAllowed.Font = New-Object System.Drawing.Font($fontName, 9)
    $form.Controls.Add($automationAllowed)
    $controls.automationAllowed = $automationAllowed

    $draftButton = New-GuiButton -Text '保存草稿' -Left 410 -Top 635 -Width 125 -Height 40 -Action { [void](Save-TargetFromForm -Controls $controls -AsReviewedPlan:$false) }
    $reviewButton = New-GuiButton -Text '保存并离线审阅' -Left 548 -Top 635 -Width 175 -Height 40 -Action { [void](Save-TargetFromForm -Controls $controls -AsReviewedPlan:$true) } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $cancelButton = New-GuiButton -Text '取消' -Left 736 -Top 635 -Width 86 -Height 40 -Action { $form.Close() }
    $form.Controls.Add($draftButton)
    $form.Controls.Add($reviewButton)
    $form.Controls.Add($cancelButton)
    $form.AcceptButton = $draftButton
    $form.CancelButton = $cancelButton
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

function Get-OfflineTargetsRoot {
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'config\targets')).TrimEnd('\')
}

function Assert-OfflineReviewDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $root = Get-OfflineTargetsRoot
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $rootPrefix = $root + '\'
    if(($full -ne $root) -and (-not $full.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase))){
        throw 'offline_review_path_outside_targets'
    }
    if(-not (Test-Path -LiteralPath $full -PathType Container)){
        throw 'offline_review_directory_missing'
    }
    return $full
}

function Get-OfflineReviewTargets {
    param([Parameter(Mandatory = $true)][string]$SelectedPath)
    $selected = Assert-OfflineReviewDirectory -Path $SelectedPath
    $root = Get-OfflineTargetsRoot
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if([string]::IsNullOrWhiteSpace($python)){
        throw 'offline_review_python_missing'
    }
    $raw = @(& $python -m src_auto.offline_scope_picker --selected $selected --root $root 2>&1)
    if($LASTEXITCODE -ne 0){
        $reason = ($raw -join ' ').Trim()
        throw ('offline_review_discovery_blocked: ' + $reason)
    }
    $payload = ($raw -join "`n") | ConvertFrom-Json
    if($null -eq $payload -or $payload.status -ne 'ok'){
        throw 'offline_review_discovery_invalid'
    }
    return @($payload.entries)
}

function Assert-OfflineReviewPair {
    param(
        [Parameter(Mandatory = $true)][string]$ScopePath,
        [Parameter(Mandatory = $true)][string]$PlanPath
    )
    $scope = Assert-TargetProjectPath -Path $ScopePath -ProjectRoot $ProjectRoot
    $plan = Assert-TargetProjectPath -Path $PlanPath -ProjectRoot $ProjectRoot
    if((Split-Path -Leaf $scope) -ne 'scope_confirmed.yaml'){
        throw 'offline_review_scope_name_invalid'
    }
    if((Split-Path -Leaf $plan) -ne 'live_plan.yaml'){
        throw 'offline_review_plan_name_invalid'
    }
    if(-not (Test-Path -LiteralPath $scope -PathType Leaf) -or -not (Test-Path -LiteralPath $plan -PathType Leaf)){
        throw 'offline_review_pair_missing'
    }
    $scopeDirectory = Assert-OfflineReviewDirectory -Path (Split-Path -Parent $scope)
    $planDirectory = Assert-OfflineReviewDirectory -Path (Split-Path -Parent $plan)
    if($scopeDirectory -ne $planDirectory){
        throw 'offline_review_pair_directory_mismatch'
    }
    return [pscustomobject]@{
        scope_path = $scope
        plan_path = $plan
        target_dir = $scopeDirectory
    }
}

function Invoke-OfflineTargetReviewResult {
    param(
        [Parameter(Mandatory = $true)][string]$ScopePath,
        [Parameter(Mandatory = $true)][string]$PlanPath
    )
    $pair = Assert-OfflineReviewPair -ScopePath $ScopePath -PlanPath $PlanPath
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if([string]::IsNullOrWhiteSpace($python)){
        throw 'offline_review_python_missing'
    }
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $python
    $startInfo.WorkingDirectory = $ProjectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $startInfo.Arguments = '-m src_auto target-review --scope "{0}" --plan "{1}" --confirm-selection --json' -f `
        $pair.scope_path.Replace('"', '\"'), $pair.plan_path.Replace('"', '\"')
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if(-not $process.Start()){
        throw 'offline_review_process_start_failed'
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    [void]$process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $process.Dispose()
    try { $payload = $stdout | ConvertFrom-Json } catch { $payload = $null }
    if($null -eq $payload){
        return [pscustomobject]@{
            status = 'blocked_review'
            reason = 'offline_review_output_invalid'
            exit_code = $exitCode
        }
    }
    return [pscustomobject]@{
        status = [string]$payload.status
        reason = [string]$payload.reason
        exit_code = $exitCode
    }
}

function Invoke-OfflineReviewBatch {
    param(
        [object[]]$Targets = @(),
        [scriptblock]$ReviewInvoker
    )
    if($null -eq $ReviewInvoker){
        $ReviewInvoker = {
            param($scope, $plan)
            Invoke-OfflineTargetReviewResult -ScopePath $scope -PlanPath $plan
        }
    }
    $results = @()
    foreach($target in @($Targets)){
        $name = [string]$target.relative_name
        if([string]::IsNullOrWhiteSpace($name)){ $name = '未命名目标' }
        try {
            $pair = Assert-OfflineReviewPair -ScopePath ([string]$target.scope_path) -PlanPath ([string]$target.plan_path)
            $review = & $ReviewInvoker $pair.scope_path $pair.plan_path
            $machineStatus = [string]$review.status
            $displayStatus = if($machineStatus -eq 'selection_reviewed'){
                '通过'
            } elseif($machineStatus.StartsWith('blocked')){
                '已阻止'
            } else {
                '需要人工复核'
            }
            $results += [pscustomobject]@{
                target = $name
                scope_path = $pair.scope_path
                plan_path = $pair.plan_path
                status = $machineStatus
                reason = [string]$review.reason
                exit_code = [int]$review.exit_code
                display_status = $displayStatus
                network_contact = $false
            }
        } catch {
            $results += [pscustomobject]@{
                target = $name
                scope_path = ''
                plan_path = ''
                status = 'blocked_review'
                reason = 'invalid_local_scope_plan_pair'
                exit_code = 3
                display_status = '已阻止'
                network_contact = $false
            }
        }
    }
    return @($results)
}

function Write-OfflineReviewBatchSummary {
    param([Parameter(Mandatory = $true)][object[]]$Results)
    $reportDirectory = Assert-TargetProjectPath -Path (Join-Path $ProjectRoot 'reports\offline-review') -ProjectRoot $ProjectRoot
    if(-not (Test-Path -LiteralPath $reportDirectory)){
        [System.IO.Directory]::CreateDirectory($reportDirectory) | Out-Null
    }
    $safeResults = @($Results | ForEach-Object {
        [ordered]@{
            target = [string]$_.target
            scope_path = [string]$_.scope_path
            plan_path = [string]$_.plan_path
            status = [string]$_.status
            reason = [string]$_.reason
            exit_code = [int]$_.exit_code
            display_status = [string]$_.display_status
            network_contact = $false
        }
    })
    $document = [ordered]@{
        schema_version = 1
        created_at = [DateTime]::UtcNow.ToString('o')
        operation = 'offline_target_review'
        network_contact = $false
        result_count = $safeResults.Count
        results = $safeResults
    }
    $name = 'offline-review-{0}-{1}.json' -f [DateTime]::Now.ToString('yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $path = Assert-TargetProjectPath -Path (Join-Path $reportDirectory $name) -ProjectRoot $ProjectRoot
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, (($document | ConvertTo-Json -Depth 6) + "`n"), $encoding)
    return $path
}

function Update-OfflineReviewList {
    param(
        [System.Windows.Forms.TextBox]$PathBox,
        [System.Windows.Forms.ListView]$TargetList,
        [System.Windows.Forms.Label]$StatusLabel
    )
    $TargetList.Items.Clear()
    try {
        $selected = Assert-OfflineReviewDirectory -Path $PathBox.Text.Trim()
        $PathBox.Text = $selected
        $entries = @(Get-OfflineReviewTargets -SelectedPath $selected)
        foreach($entry in $entries){
            $scopeText = switch([string]$entry.scope_status){
                'confirmed' { '已确认' }
                'candidate' { '候选' }
                default { '缺失' }
            }
            $planText = if([string]$entry.plan_status -eq 'present'){ '存在' } else { '缺失' }
            $statusText = switch([string]$entry.status){
                'ready' { '可审阅' }
                'missing_plan' { '缺少 live_plan.yaml' }
                'candidate_only' { '候选 Scope（不可审阅）' }
                default { '缺少已确认 Scope' }
            }
            $item = New-Object System.Windows.Forms.ListViewItem([string]$entry.relative_name)
            [void]$item.SubItems.Add($scopeText)
            [void]$item.SubItems.Add($planText)
            [void]$item.SubItems.Add($statusText)
            $item.Tag = $entry
            if(-not [bool]$entry.actionable){
                $item.ForeColor = [System.Drawing.Color]::Gray
            }
            [void]$TargetList.Items.Add($item)
        }
        $actionableCount = @($entries | Where-Object { [bool]$_.actionable }).Count
        if($entries.Count -eq 0){
            $StatusLabel.Text = '当前目录下没有发现 Scope 或人工计划文件。'
            $StatusLabel.ForeColor = $mutedColor
        } else {
            $StatusLabel.Text = ('已发现 {0} 个目标目录，其中 {1} 个可离线审阅。灰色项目仅供检查，不能执行。' -f $entries.Count, $actionableCount)
            $StatusLabel.ForeColor = if($actionableCount -gt 0){ $safeColor } else { $mutedColor }
        }
    } catch {
        $StatusLabel.Text = '目录不可用或超出 config\targets 安全边界。'
        $StatusLabel.ForeColor = [System.Drawing.Color]::Firebrick
    }
}

function Show-OfflineReviewPicker {
    $targetsRoot = Get-OfflineTargetsRoot
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto - 离线审阅目标范围'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = New-Object System.Drawing.Size(940, 610)
    $form.MinimumSize = New-Object System.Drawing.Size(940, 610)
    $form.BackColor = [System.Drawing.Color]::White

    $form.Controls.Add((New-GuiLabel -Text '离线审阅目标范围' -Left 28 -Top 20 -Width 520 -Height 34 -Size 17 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-GuiLabel -Text '选择任意允许的上级文件夹，程序会在本地列出其下所有完整目标；此窗口不会访问目标网站。' -Left 30 -Top 58 -Width 860 -Height 26 -Size 9 -Color $safeColor))

    $pathLabel = New-GuiLabel -Text '目标目录' -Left 30 -Top 102 -Width 90 -Height 25 -Size 9 -Color $mutedColor
    $form.Controls.Add($pathLabel)
    $pathBox = New-Object System.Windows.Forms.TextBox
    $pathBox.Name = 'offlineReviewPath'
    $pathBox.Text = $targetsRoot
    $pathBox.Location = New-Object System.Drawing.Point(120, 99)
    $pathBox.Size = New-Object System.Drawing.Size(785, 28)
    $pathBox.Font = New-Object System.Drawing.Font($fontName, 9)
    $pathBox.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $form.Controls.Add($pathBox)

    $targetList = New-Object System.Windows.Forms.ListView
    $targetList.Name = 'offlineTargetList'
    $targetList.Location = New-Object System.Drawing.Point(30, 185)
    $targetList.Size = New-Object System.Drawing.Size(875, 300)
    $targetList.View = [System.Windows.Forms.View]::Details
    $targetList.FullRowSelect = $true
    $targetList.GridLines = $true
    $targetList.CheckBoxes = $true
    $targetList.HideSelection = $false
    $targetList.Font = New-Object System.Drawing.Font($fontName, 9)
    [void]$targetList.Columns.Add('目标 / 相对路径', 520)
    [void]$targetList.Columns.Add('Scope', 105)
    [void]$targetList.Columns.Add('计划', 105)
    [void]$targetList.Columns.Add('状态', 120)
    $form.Controls.Add($targetList)

    $statusLabel = New-GuiLabel -Text '正在读取本地目标配置……' -Left 30 -Top 495 -Width 875 -Height 28 -Size 9 -Color $mutedColor
    $statusLabel.Name = 'offlineReviewStatus'
    $form.Controls.Add($statusLabel)

    $refreshAction = {
        Update-OfflineReviewList -PathBox $pathBox -TargetList $targetList -StatusLabel $statusLabel
    }
    $rootButton = New-GuiButton -Text '项目目标根' -Left 30 -Top 140 -Width 125 -Height 32 -Action {
        $pathBox.Text = $targetsRoot
        & $refreshAction
    }
    $upButton = New-GuiButton -Text '上一级' -Left 165 -Top 140 -Width 100 -Height 32 -Action {
        try {
            $current = Assert-OfflineReviewDirectory -Path $pathBox.Text.Trim()
            if($current -eq $targetsRoot){
                $pathBox.Text = $targetsRoot
            } else {
                $parent = Split-Path -Parent $current
                $pathBox.Text = Assert-OfflineReviewDirectory -Path $parent
            }
            & $refreshAction
        } catch {
            $pathBox.Text = $targetsRoot
            & $refreshAction
        }
    }
    $folderButton = New-GuiButton -Text '选择文件夹' -Left 275 -Top 140 -Width 125 -Height 32 -Action {
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = '选择 config\targets 内的目标文件夹或上级分组文件夹'
        $dialog.SelectedPath = $pathBox.Text
        $dialog.ShowNewFolderButton = $false
        if($dialog.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK){
            $pathBox.Text = $dialog.SelectedPath
            & $refreshAction
        }
        $dialog.Dispose()
    }
    $refreshButton = New-GuiButton -Text '刷新' -Left 410 -Top 140 -Width 90 -Height 32 -Action { & $refreshAction }
    $selectAllButton = New-GuiButton -Text '全选结果' -Left 510 -Top 140 -Width 110 -Height 32 -Action {
        foreach($item in $targetList.Items){
            if([bool]$item.Tag.actionable){ $item.Checked = $true }
        }
    }
    $form.Controls.Add($rootButton)
    $form.Controls.Add($upButton)
    $form.Controls.Add($folderButton)
    $form.Controls.Add($refreshButton)
    $form.Controls.Add($selectAllButton)

    $pathBox.Add_KeyDown({
        if($_.KeyCode -eq [System.Windows.Forms.Keys]::Enter){
            & $refreshAction
            $_.SuppressKeyPress = $true
        }
    })
    $targetList.Add_DoubleClick({
        if($targetList.SelectedItems.Count -eq 1){
            $pathBox.Text = [string]$targetList.SelectedItems[0].Tag.target_dir
            & $refreshAction
        }
    })
    $targetList.Add_ItemCheck({
        if($_.Index -ge 0){
            $entry = $targetList.Items[$_.Index].Tag
            if(-not [bool]$entry.actionable){
                $_.NewValue = [System.Windows.Forms.CheckState]::Unchecked
            }
        }
    })

    $reviewButton = New-GuiButton -Text '开始离线审阅' -Left 620 -Top 545 -Width 165 -Height 40 -Action {
        $selectedItems = @($targetList.CheckedItems | Where-Object { [bool]$_.Tag.actionable })
        if($selectedItems.Count -eq 0 -and $targetList.SelectedItems.Count -eq 1 -and [bool]$targetList.SelectedItems[0].Tag.actionable){
            $selectedItems = @($targetList.SelectedItems[0])
        }
        if($selectedItems.Count -eq 0){
            Show-Warning '请先勾选至少一个可审阅目标。'
            return
        }
        $selectedTargets = @($selectedItems | ForEach-Object { $_.Tag })
        $results = @(Invoke-OfflineReviewBatch -Targets $selectedTargets)
        $summaryPath = Write-OfflineReviewBatchSummary -Results $results
        $lines = @($results | ForEach-Object { '{0}：{1}' -f $_.target, $_.display_status })
        $message = "离线审阅完成。不同目标的授权范围不会合并。`r`n`r`n{0}`r`n`r`n汇总：{1}`r`n`r`n全程没有访问目标网站。" -f ($lines -join "`r`n"), $summaryPath
        Show-Info $message '离线审阅完成'
    } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $cancelButton = New-GuiButton -Text '取消' -Left 800 -Top 545 -Width 105 -Height 40 -Action { $form.Close() }
    $form.Controls.Add($reviewButton)
    $form.Controls.Add($cancelButton)
    $form.CancelButton = $cancelButton

    & $refreshAction
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

function Select-ExistingTarget {
    Show-OfflineReviewPicker
}

function Open-AISettings {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto - AI 模型与密钥设置'
    $form.StartPosition = 'CenterParent'
    $form.ClientSize = New-Object System.Drawing.Size(650, 300)
    $form.BackColor = [System.Drawing.Color]::White
    $form.Controls.Add((New-GuiLabel -Text 'AI 模型与密钥设置' -Left 28 -Top 20 -Width 500 -Height 34 -Size 16 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-GuiLabel -Text '远程 AI 默认关闭；保存密钥不会联网，也不会在窗口中显示明文。' -Left 30 -Top 60 -Width 575 -Height 30 -Size 9 -Color $safeColor))
    $deepseek = New-GuiButton -Text '保存 DeepSeek 密钥' -Left 40 -Top 115 -Width 250 -Height 50 -Action {
        $script = Join-Path $ProjectRoot 'tools\save_deepseek_key.ps1'
        Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script) -WorkingDirectory $ProjectRoot | Out-Null
    }
    $openrouter = New-GuiButton -Text '保存 OpenRouter / Ox Alpha 密钥' -Left 320 -Top 115 -Width 285 -Height 50 -Action {
        $script = Join-Path $ProjectRoot 'tools\save_openrouter_key_gui.ps1'
        Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-Sta','-ExecutionPolicy','Bypass','-File',$script) -WorkingDirectory $ProjectRoot | Out-Null
    }
    $form.Controls.Add($deepseek)
    $form.Controls.Add($openrouter)
    $form.Controls.Add((New-GuiLabel -Text '说明：模型只允许人工审阅已有 Finding，不参与自动发现、目标选择或报告提交。' -Left 40 -Top 195 -Width 565 -Height 34 -Size 9 -Color $mutedColor))
    $close = New-GuiButton -Text '关闭' -Left 500 -Top 240 -Width 105 -Height 36 -Action { $form.Close() }
    $form.Controls.Add($close)
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

function Open-SessionProfileManager {
    $script = Join-Path $ProjectRoot 'tools\session_profile_gui.ps1'
    if(-not (Test-Path -LiteralPath $script)){
        Show-Warning '找不到测试会话管理窗口。'
        return
    }
    Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-Sta','-ExecutionPolicy','Bypass','-File',$script) -WorkingDirectory $ProjectRoot | Out-Null
}

function New-HomeActionCard {
    param(
        [string]$Step,
        [string]$Title,
        [string]$Description,
        [int]$Left,
        [int]$Top,
        [int]$Width = 285
    )
    $card = New-Object System.Windows.Forms.Panel
    $card.Location = New-Object System.Drawing.Point($Left, $Top)
    $card.Size = New-Object System.Drawing.Size($Width, 184)
    $card.BackColor = [System.Drawing.Color]::White
    $card.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $card.Controls.Add((New-GuiLabel -Text $Step -Left 18 -Top 16 -Width 90 -Height 22 -Size 9 -Color $accentColor -Style ([System.Drawing.FontStyle]::Bold)))
    $card.Controls.Add((New-GuiLabel -Text $Title -Left 18 -Top 48 -Width ($Width - 36) -Height 30 -Size 12 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    # Keep the description above the action row (which begins at y=128 in the
    # card) so the larger, clearer text is never hidden under a button.
    $card.Controls.Add((New-GuiLabel -Text $Description -Left 18 -Top 84 -Width ($Width - 36) -Height 42 -Size 10 -Color $mutedColor))
    return $card
}

function Show-SrcAutoMainWindow {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto 安全测试控制台'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = New-Object System.Drawing.Size(1180, 730)
    $form.MinimumSize = New-Object System.Drawing.Size(1080, 690)
    $form.BackColor = $canvasColor

    $sidebar = New-Object System.Windows.Forms.Panel
    $sidebar.Location = New-Object System.Drawing.Point(0, 0)
    $sidebar.Size = New-Object System.Drawing.Size(208, 730)
    $sidebar.BackColor = $navColor
    $form.Controls.Add($sidebar)
    $sidebar.Controls.Add((New-GuiLabel -Text 'SRC-Auto' -Left 26 -Top 28 -Width 160 -Height 34 -Size 18 -Color ([System.Drawing.Color]::White) -Style ([System.Drawing.FontStyle]::Bold)))
    $sidebar.Controls.Add((New-GuiLabel -Text '安全测试控制台' -Left 28 -Top 64 -Width 150 -Height 23 -Size 9 -Color ([System.Drawing.Color]::FromArgb(200, 221, 239))))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navQuickStart' -Text '快速开始' -Top 112 -Active:$true -Action {
        if($localLabButton){
            $form.ActiveControl = $localLabButton
            [void]$localLabButton.Focus()
        }
    }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navLocalLab' -Text '本地靶场' -Top 164 -Action { Show-LocalLabDashboard }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navTarget' -Text '目标与授权' -Top 202 -Action { Show-TargetWizard }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navOffline' -Text '离线审阅' -Top 240 -Action { Show-OfflineReviewPicker }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navReports' -Text '结果与报告' -Top 278 -Action { Open-ReportsFolder }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navAI' -Text 'AI 设置' -Top 316 -Action { Open-AISettings }))
    $sidebar.Controls.Add((New-GuiLabel -Text '安全状态' -Left 28 -Top 563 -Width 150 -Height 24 -Size 9 -Color ([System.Drawing.Color]::FromArgb(155, 202, 176)) -Style ([System.Drawing.FontStyle]::Bold)))
    $sidebar.Controls.Add((New-GuiLabel -Text '默认安全模式' -Left 28 -Top 590 -Width 150 -Height 23 -Size 9 -Color ([System.Drawing.Color]::White)))
    $sidebar.Controls.Add((New-GuiLabel -Text '默认仅本机回环靶场' -Left 28 -Top 616 -Width 170 -Height 23 -Size 9 -Color ([System.Drawing.Color]::FromArgb(220, 235, 250))))
    $sidebar.Controls.Add((New-GuiLabel -Text '真实目标不会自动执行' -Left 28 -Top 642 -Width 165 -Height 38 -Size 9 -Color ([System.Drawing.Color]::FromArgb(255, 231, 170))))

    $header = New-Object System.Windows.Forms.Panel
    $header.Location = New-Object System.Drawing.Point(208, 0)
    $header.Size = New-Object System.Drawing.Size(972, 138)
    $header.BackColor = [System.Drawing.Color]::White
    $header.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $form.Controls.Add($header)
    $header.Controls.Add((New-GuiLabel -Text '清晰、可控地开始一次安全测试' -Left 32 -Top 28 -Width 590 -Height 36 -Size 17 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $header.Controls.Add((New-GuiLabel -Text '先在本地靶场熟悉流程；真实项目只录入授权范围并进行离线审阅。' -Left 34 -Top 68 -Width 600 -Height 28 -Size 10 -Color $mutedColor))
    $header.Controls.Add((New-GuiLabel -Text '安全状态' -Left 742 -Top 27 -Width 165 -Height 22 -Size 9 -Color $mutedColor))
    $header.Controls.Add((New-GuiLabel -Text '待人工操作' -Left 742 -Top 52 -Width 180 -Height 26 -Size 11 -Color $safeColor -Style ([System.Drawing.FontStyle]::Bold)))
    $header.Controls.Add((New-GuiLabel -Text '未自动访问任何真实目标' -Left 742 -Top 82 -Width 205 -Height 23 -Size 9 -Color $mutedColor))

    $form.Controls.Add((New-GuiLabel -Text '快速开始' -Left 242 -Top 164 -Width 300 -Height 30 -Size 13 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-GuiLabel -Text '从下列三步任选其一。每一步都会明确提示下一步和安全边界。' -Left 242 -Top 194 -Width 650 -Height 25 -Size 9 -Color $mutedColor))

    $form.Controls.Add((New-HomeActionCard -Step '步骤 1' -Title '练习本地靶场' -Description '启动后只使用本机回环地址。适合熟悉界面、验证流程和查看本地结果。' -Left 242 -Top 232))
    $form.Controls.Add((New-HomeActionCard -Step '步骤 2' -Title '录入授权目标' -Description '把补天项目规则、允许主机、端口和测试窗口写入本地配置草稿。' -Left 546 -Top 232))
    $form.Controls.Add((New-HomeActionCard -Step '步骤 3' -Title '审阅已有范围' -Description '仅在本地核对范围与计划文件，不访问目标网站，也不启动外部检测。' -Left 850 -Top 232))
    # The action buttons overlap the lower portion of their cards.  Keep the
    # cards as background content and explicitly place these controls on top,
    # otherwise a panel wins the mouse hit-test even though PerformClick works.
    $localLabButton = New-GuiButton -Text '本地靶场检测' -Left 260 -Top 360 -Width 249 -Height 40 -Action { Show-LocalLabDashboard } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $localLabButton.Name = 'actionLocalLab'
    $targetButton = New-GuiButton -Text '新建授权目标' -Left 564 -Top 360 -Width 249 -Height 40 -Action { Show-TargetWizard }
    $offlineReviewButton = New-GuiButton -Text '离线审阅目标范围' -Left 868 -Top 360 -Width 249 -Height 40 -Action { Show-OfflineReviewPicker }
    foreach($button in @($localLabButton, $targetButton, $offlineReviewButton)) {
        $form.Controls.Add($button)
        $button.BringToFront()
    }

    $form.Controls.Add((New-GuiLabel -Text '其他操作' -Left 242 -Top 440 -Width 300 -Height 28 -Size 12 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-GuiLabel -Text '常用入口集中在这里，不会直接启动真实目标测试。' -Left 242 -Top 470 -Width 650 -Height 24 -Size 9 -Color $mutedColor))
    $form.Controls.Add((New-GuiButton -Text '选择已有目标' -Left 242 -Top 505 -Width 208 -Height 42 -Action { Select-ExistingTarget }))
    $form.Controls.Add((New-GuiButton -Text '查看 Findings 和报告' -Left 462 -Top 505 -Width 208 -Height 42 -Action { Open-ReportsFolder }))
    $form.Controls.Add((New-GuiButton -Text 'AI 模型与密钥设置' -Left 682 -Top 505 -Width 208 -Height 42 -Action { Open-AISettings }))
    $form.Controls.Add((New-GuiButton -Text '测试会话管理' -Left 902 -Top 505 -Width 208 -Height 42 -Action { Open-SessionProfileManager }))

    $safety = New-Object System.Windows.Forms.Panel
    $safety.Location = New-Object System.Drawing.Point(242, 582)
    $safety.Size = New-Object System.Drawing.Size(876, 82)
    $safety.BackColor = [System.Drawing.Color]::FromArgb(233, 246, 238)
    $safety.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $safety.Controls.Add((New-GuiLabel -Text '安全提示' -Left 18 -Top 12 -Width 120 -Height 22 -Size 10 -Color $safeColor -Style ([System.Drawing.FontStyle]::Bold)))
    $safety.Controls.Add((New-GuiLabel -Text '仅对你明确拥有授权的目标操作。禁止越界、爆破、破坏性请求和批量收集个人信息。' -Left 18 -Top 38 -Width 825 -Height 22 -Size 9 -Color $safeColor))
    $safety.Controls.Add((New-GuiLabel -Text '状态、报告和密钥密文均保存在 D:\网络安全文件夹\SRC-Auto。' -Left 18 -Top 59 -Width 825 -Height 20 -Size 9 -Color $safeColor))
    $form.Controls.Add($safety)
    $form.Controls.Add((New-GuiButton -Text '退出' -Left 954 -Top 680 -Width 164 -Height 32 -Action { $form.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)))
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

Show-SrcAutoMainWindow

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
    $composeFile = Join-Path $ProjectRoot 'docker-compose.local-labs.yml'
    $statusLabel = $null
    function Update-LocalLabDashboardStatus {
        param([string]$Prefix = '状态：')
        if(-not $statusLabel){ return }
        try {
            $raw = @(& python -m src_auto local-labs status --json 2>$null)
            $json = ($raw -join "`n") | ConvertFrom-Json
            $ready = @($json.labs | Where-Object { $_.status -eq 'READY' }).Count
            $total = @($json.labs).Count
            $statusLabel.Text = '{0} {1}/{2} 个靶场已就绪；网络接触：{3}' -f $Prefix, $ready, $total, $(if($json.network_contact){'本地回环'}else{'无'})
        } catch {
            $statusLabel.Text = "$Prefix 无法读取 Docker 状态；请先启动 Docker Desktop。"
        }
    }
    function Stop-LocalLabServices {
        if(-not (Test-Path -LiteralPath $composeFile)){
            $statusLabel.Text = '状态：找不到本地靶场编排文件。'
            return
        }
        try {
            & docker compose -f $composeFile down 2>$null | Out-Null
            $statusLabel.Text = '状态：已请求停止本地靶场；未访问真实目标。'
        } catch {
            $statusLabel.Text = '状态：停止失败，Docker Desktop 可能未运行。'
        }
    }
    function Start-LocalValidation {
        $validation = Join-Path $ProjectRoot 'tools\run_local_lab_validation.py'
        if(-not (Test-Path -LiteralPath $validation)){
            $statusLabel.Text = '状态：找不到本地验收脚本。'
            return
        }
        Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-Command',"Set-Location -LiteralPath '$ProjectRoot'; python tools\run_local_lab_validation.py --local-only --repeat-rounds 0 --json") -WorkingDirectory $ProjectRoot | Out-Null
        $statusLabel.Text = '验证进度：已在独立终端启动本地验收（仅回环，结果写入 validation/autotest）。'
    }
    function Open-SelectedLoopbackLab {
        $selected = [string]$selector.SelectedItem
        if($selected -notmatch '^(Juice Shop|DVWA|WebGoat|VAmPI|业务 API)\|http://127\.0\.0\.1:[0-9]+'){
            $statusLabel.Text = '状态：请选择固定回环靶场。'
            return
        }
        $url = ($selected -split '\|', 2)[1].Trim()
        if($url -notmatch '^http://127\.0\.0\.1:[0-9]+'){ throw 'loopback_url_required' }
        Start-Process $url | Out-Null
        $statusLabel.Text = '状态：已打开固定回环页面：' + $url
    }
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto - 本地靶场与回归验证'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = New-Object System.Drawing.Size(1010, 760)
    $form.MinimumSize = New-Object System.Drawing.Size(1010, 760)
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

    $form.Controls.Add((New-LabGuideCard -Title 'Juice Shop' -Address '127.0.0.1:3000' -Description '面向 Web 应用安全练习的本地靶场。' -Left 34 -Top 220 -Width 292))
    $form.Controls.Add((New-LabGuideCard -Title 'DVWA' -Address '127.0.0.1:8081' -Description '用于常见 Web 输入与会话安全验证。' -Left 358 -Top 220 -Width 292))
    $form.Controls.Add((New-LabGuideCard -Title 'WebGoat' -Address '127.0.0.1:8082' -Description '带有课程式说明的本地安全学习环境。' -Left 682 -Top 220 -Width 292))
    $form.Controls.Add((New-LabGuideCard -Title 'VAmPI' -Address '127.0.0.1:8083' -Description '本地 API 练习环境，用于接口契约和对象授权复核。' -Left 34 -Top 380 -Width 292))
    $form.Controls.Add((New-LabGuideCard -Title '业务 API（business-api）' -Address '127.0.0.1:8084' -Description '确定性合成订单夹具，专门验证账号会话、API 对比和 IDOR 候选。' -Left 358 -Top 380 -Width 292))

    $guide = New-Object System.Windows.Forms.Panel
    $guide.Location = New-Object System.Drawing.Point(34, 545)
    $guide.Size = New-Object System.Drawing.Size(942, 74)
    $guide.BackColor = [System.Drawing.Color]::FromArgb(233, 246, 238)
    $guide.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $guide.Controls.Add((New-GuiLabel -Text '操作提示' -Left 18 -Top 10 -Width 120 -Height 24 -Size 10 -Color $safeColor -Style ([System.Drawing.FontStyle]::Bold)))
    $guide.Controls.Add((New-GuiLabel -Text '启动、停止、打开和验证都只针对固定 127.0.0.1 靶场；真实目标不会出现在此页面。' -Left 18 -Top 36 -Width 900 -Height 24 -Size 9 -Color $safeColor))
    $form.Controls.Add($guide)

    $selector = New-Object System.Windows.Forms.ComboBox
    $selector.Name = 'labSelector'
    $selector.Location = New-Object System.Drawing.Point(34, 642)
    $selector.Size = New-Object System.Drawing.Size(250, 38)
    $selector.Font = New-Object System.Drawing.Font($fontName, 10)
    foreach($item in @('Juice Shop|http://127.0.0.1:3000/','DVWA|http://127.0.0.1:8081/login.php','WebGoat|http://127.0.0.1:8082/WebGoat/','VAmPI|http://127.0.0.1:8083/ui/','业务 API|http://127.0.0.1:8084/health')){ [void]$selector.Items.Add($item) }
    $selector.SelectedIndex = 0
    $form.Controls.Add($selector)
    $statusLabel = New-GuiLabel -Text '状态：正在读取本地靶场状态…' -Left 300 -Top 648 -Width 660 -Height 26 -Size 9 -Color $mutedColor
    $form.Controls.Add($statusLabel)
    $startButton = New-GuiButton -Text '启动本地靶场' -Left 34 -Top 694 -Width 150 -Height 42 -Action { Start-LocalLabWindow } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $stopButton = New-GuiButton -Text '停止本地靶场' -Left 194 -Top 694 -Width 150 -Height 42 -Action { Stop-LocalLabServices }
    $openButton = New-GuiButton -Text '打开回环页面' -Left 354 -Top 694 -Width 150 -Height 42 -Action { Open-SelectedLoopbackLab }
    $validateButton = New-GuiButton -Text '运行本地验证' -Left 514 -Top 694 -Width 150 -Height 42 -Action { Start-LocalValidation } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $reportButton = New-GuiButton -Text '查看本地报告' -Left 674 -Top 694 -Width 140 -Height 42 -Action { Open-ReportsFolder }
    $closeButton = New-GuiButton -Text '返回主页' -Left 826 -Top 694 -Width 150 -Height 42 -Action { $form.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)
    $form.Controls.Add($startButton)
    $form.Controls.Add($stopButton)
    $form.Controls.Add($openButton)
    $form.Controls.Add($validateButton)
    $form.Controls.Add($reportButton)
    $form.Controls.Add($closeButton)
    $form.CancelButton = $closeButton
    Update-LocalLabDashboardStatus
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

function Open-ReportsFolder {
    # Keep one in-app, closable results surface so a navigation click cannot
    # silently launch Explorer or appear to do nothing.
    Show-FindingsWindow
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
    $script = Join-Path $ProjectRoot 'tools\start_dashboard.ps1'
    if(-not (Test-Path -LiteralPath $script)){ Show-Warning '找不到平台系统设置入口。'; return }
    Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script,'-InitialPage','settings') -WorkingDirectory $ProjectRoot -WindowStyle Hidden | Out-Null
}

function Open-SessionProfileManager {
    $script = Join-Path $ProjectRoot 'tools\session_profile_gui.ps1'
    if(-not (Test-Path -LiteralPath $script)){
        Show-Warning '找不到测试会话管理窗口。'
        return
    }
    Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-Sta','-ExecutionPolicy','Bypass','-File',$script) -WorkingDirectory $ProjectRoot | Out-Null
}

function Show-Workbench {
    # The workbench is the already-open main window.  Keep this handler real so
    # the sidebar never points at a missing command; the caller focuses the
    # first local action when the main form is available.
    if($script:SrcAutoMainForm -and -not $script:SrcAutoMainForm.IsDisposed){
        [void]$script:SrcAutoMainForm.Activate()
    }
}

function New-SrcAutoInfoWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$Summary,
        [string[]]$Lines = @(),
        [string]$PrimaryText = '关闭',
        [scriptblock]$PrimaryAction
    )
    $window = New-Object System.Windows.Forms.Form
    $window.Text = 'SRC-Auto - ' + $Title
    $window.StartPosition = 'CenterParent'
    $window.ClientSize = New-Object System.Drawing.Size(760, 480)
    $window.MinimumSize = New-Object System.Drawing.Size(760, 480)
    $window.BackColor = [System.Drawing.Color]::White
    $window.Controls.Add((New-GuiLabel -Text $Title -Left 32 -Top 24 -Width 660 -Height 36 -Size 17 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $window.Controls.Add((New-GuiLabel -Text $Summary -Left 34 -Top 68 -Width 680 -Height 46 -Size 10 -Color $mutedColor))
    $list = New-Object System.Windows.Forms.ListBox
    $list.Name = 'statusList'
    $list.Location = New-Object System.Drawing.Point(34, 128)
    $list.Size = New-Object System.Drawing.Size(692, 245)
    $list.Font = New-Object System.Drawing.Font($fontName, 10)
    $list.HorizontalScrollbar = $true
    foreach($line in $Lines){ [void]$list.Items.Add([string]$line) }
    $window.Controls.Add($list)
    if($PrimaryAction){
        # Pass the dialog explicitly so a caller's action never relies on
        # PowerShell dynamic-scope lookup after the WinForms event fires.
        $closeAction = {
            & $PrimaryAction $window
        }.GetNewClosure()
    } else {
        $closeAction = { $window.Close() }.GetNewClosure()
    }
    $primary = New-GuiButton -Text $PrimaryText -Left 510 -Top 398 -Width 216 -Height 42 -Action $closeAction -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $window.Controls.Add($primary)
    $window.CancelButton = $primary
    Enable-SrcAutoDpiLayout -Form $window
    [void]$window.ShowDialog()
    $window.Dispose()
}

function Show-SessionTaskWindow {
    $lines = @(
        '会话与任务：仅展示本地授权审阅、会话元数据和可恢复状态。',
        '当前策略：远程目标不会从此页面自动启动。',
        '账号值保存在 Windows 当前用户 DPAPI 密文中，列表不显示明文。',
        '下一步：使用“测试会话管理”录入会话，再由人工确认 API 对比任务。'
    )
    New-SrcAutoInfoWindow -Title '会话与任务' -Summary '查看本地任务状态、授权审阅和可恢复会话；所有动作都停留在项目目录。' -Lines $lines
}

function Show-ProxyApiReviewWindow {
    $lines = @(
        '代理与 API 复核：Burp 手动代理和 OWASP 代理仅作为人工确认后的观察工具。',
        '默认请求方法：GET / HEAD；写操作必须由人工确认且仅限合成本地对象。',
        'API 对象差异只保留路径和指纹，不在报告中保存 Cookie、Token 或响应正文。',
        '当前页面不会连接 Burp 或任何真实目标。'
    )
    New-SrcAutoInfoWindow -Title '代理与 API 复核' -Summary '先准备会话和范围，再从本地报告入口复核对象差异；没有授权就不会启动代理流量。' -Lines $lines
}

function Show-FindingsWindow {
    $window = New-Object System.Windows.Forms.Form
    $window.Text = 'SRC-Auto - 发现与报告'
    $window.StartPosition = 'CenterParent'
    $window.ClientSize = New-Object System.Drawing.Size(1060, 650)
    $window.MinimumSize = New-Object System.Drawing.Size(1060, 650)
    $window.BackColor = [System.Drawing.Color]::White
    $window.Controls.Add((New-GuiLabel -Text '发现与报告' -Left 32 -Top 24 -Width 900 -Height 36 -Size 17 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $window.Controls.Add((New-GuiLabel -Text '单击左侧文件即可在右侧查看详细内容；这里只读取项目内报告，不会执行其中的链接或脚本。' -Left 34 -Top 68 -Width 970 -Height 36 -Size 10 -Color $mutedColor))
    $window.Controls.Add((New-GuiLabel -Text '本地报告文件' -Left 34 -Top 108 -Width 300 -Height 26 -Size 10 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $window.Controls.Add((New-GuiLabel -Text '详细内容预览' -Left 390 -Top 108 -Width 500 -Height 26 -Size 10 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $list = New-Object System.Windows.Forms.ListBox
    $list.Name = 'findingsList'
    $list.Location = New-Object System.Drawing.Point(34, 140)
    $list.Size = New-Object System.Drawing.Size(328, 410)
    $list.Font = New-Object System.Drawing.Font($fontName, 9)
    $list.HorizontalScrollbar = $true
    $window.Controls.Add($list)

    $preview = New-Object System.Windows.Forms.RichTextBox
    $preview.Name = 'reportPreview'
    $preview.Location = New-Object System.Drawing.Point(390, 140)
    $preview.Size = New-Object System.Drawing.Size(638, 410)
    $preview.Font = New-Object System.Drawing.Font('Consolas', 9)
    $preview.ReadOnly = $true
    $preview.WordWrap = $false
    $preview.DetectUrls = $false
    $preview.ScrollBars = [System.Windows.Forms.RichTextBoxScrollBars]::Both
    $preview.BackColor = [System.Drawing.Color]::FromArgb(250, 252, 254)
    $preview.Text = '请从左侧选择一个报告文件。'
    $window.Controls.Add($preview)

    $status = New-GuiLabel -Text '尚未选择文件。' -Left 390 -Top 556 -Width 638 -Height 42 -Size 9 -Color $mutedColor
    $status.Name = 'reportStatus'
    $window.Controls.Add($status)
    $reportPaths = @{}
    $reportProjectRoot = [string]$ProjectRoot

    $showSelected = {
        if($list.SelectedIndex -lt 0){ return }
        $relative = [string]$list.SelectedItem
        if(-not $reportPaths.ContainsKey($relative)){
            $preview.Text = '该项目不是可查看的报告文件。'
            $status.Text = '请选择有效的本地报告。'
            return
        }
        try {
            $path = [System.IO.Path]::GetFullPath([string]$reportPaths[$relative])
            $safeRoot = [System.IO.Path]::GetFullPath($reportProjectRoot).TrimEnd('\') + '\'
            if(-not $path.StartsWith($safeRoot, [System.StringComparison]::OrdinalIgnoreCase)){ throw 'report_path_outside_project' }
            if(-not (Test-Path -LiteralPath $path -PathType Leaf)){ throw 'report_file_not_found' }
            $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
            if($extension -notin @('.json','.md','.html','.txt','.log','.xml')){ throw 'report_file_type_not_supported' }
            $file = Get-Item -LiteralPath $path -ErrorAction Stop
            if($file.Length -gt 1048576){
                $preview.Text = '该报告超过 1 MB。为避免界面卡顿，内置预览未加载全文；请查看较小的摘要报告。'
                $status.Text = ('文件：{0}　大小：{1:N0} KB　状态：超过内置预览上限' -f $relative, ($file.Length / 1KB))
                return
            }
            $preview.Text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
            $preview.SelectionStart = 0
            $preview.SelectionLength = 0
            $preview.ScrollToCaret()
            $status.Text = ('文件：{0}　大小：{1:N1} KB　修改：{2:yyyy-MM-dd HH:mm:ss}' -f $relative, ($file.Length / 1KB), $file.LastWriteTime)
        } catch {
            $preview.Text = '无法读取所选报告：' + $_.Exception.Message
            $status.Text = '读取失败；文件必须位于项目目录内且格式受支持。'
        }
    }.GetNewClosure()

    $refresh = {
        $list.Items.Clear()
        $reportPaths.Clear()
        $preview.Text = '请从左侧选择一个报告文件。'
        $status.Text = '尚未选择文件。'
        $roots = @((Join-Path $reportProjectRoot 'reports'), (Join-Path $reportProjectRoot 'validation'))
        $files = @()
        foreach($root in $roots){
            # Do not recursively walk scanner/vendor work directories from the UI;
            # top-level summaries are enough for a responsive, readable view.
            if(Test-Path -LiteralPath $root){
                $files += @(Get-ChildItem -LiteralPath $root -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @('.json','.md','.html') })
                $files += @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    Get-ChildItem -LiteralPath $_.FullName -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @('.json','.md','.html') } | Select-Object -First 20
                })
            }
        }
        $files = @($files | Sort-Object FullName -Unique | Select-Object -First 120)
        if($files.Count -eq 0){ [void]$list.Items.Add('暂无本地报告；先运行本地靶场或离线审阅。') }
        else {
            foreach($file in $files){
                $relative = $file.FullName.Substring($reportProjectRoot.Length).TrimStart('\')
                $reportPaths[$relative] = $file.FullName
                [void]$list.Items.Add($relative)
            }
        }
    }.GetNewClosure()
    $list.Add_SelectedIndexChanged($showSelected)
    $refreshButton = New-GuiButton -Text '刷新本地结果' -Left 34 -Top 588 -Width 180 -Height 40 -Action $refresh
    $closeButton = New-GuiButton -Text '关闭' -Left 912 -Top 588 -Width 116 -Height 40 -Action { $window.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)
    $window.Controls.Add($refreshButton)
    $window.Controls.Add($closeButton)
    $window.CancelButton = $closeButton
    & $refresh
    Enable-SrcAutoDpiLayout -Form $window
    [void]$window.ShowDialog()
    $window.Dispose()
}

function Show-DefenseObservationWindow {
    $window = New-Object System.Windows.Forms.Form
    $window.Text = 'SRC-Auto - 蓝队被动分析'
    $window.StartPosition = 'CenterParent'
    $window.ClientSize = New-Object System.Drawing.Size(780, 520)
    $window.MinimumSize = New-Object System.Drawing.Size(780, 520)
    $window.BackColor = [System.Drawing.Color]::White
    $window.Controls.Add((New-GuiLabel -Text '蓝队被动分析' -Left 32 -Top 24 -Width 650 -Height 36 -Size 17 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $window.Controls.Add((New-GuiLabel -Text '输入自有或受托保护域名，仅登记授权状态；没有所有权和自动化观察许可时保持待授权。' -Left 34 -Top 68 -Width 700 -Height 42 -Size 10 -Color $mutedColor))
    $window.Controls.Add((New-GuiLabel -Text '域名' -Left 34 -Top 132 -Width 120 -Height 26 -Size 10 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $domain = New-Object System.Windows.Forms.TextBox
    $domain.Name = 'defenseDomain'
    $domain.Location = New-Object System.Drawing.Point(160, 128)
    $domain.Size = New-Object System.Drawing.Size(560, 32)
    $domain.Font = New-Object System.Drawing.Font($fontName, 10)
    $window.Controls.Add($domain)
    $window.Controls.Add((New-GuiLabel -Text '授权/所有权证据（例如资产清单编号）' -Left 34 -Top 184 -Width 300 -Height 26 -Size 10 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $evidence = New-Object System.Windows.Forms.TextBox
    $evidence.Name = 'defenseEvidence'
    $evidence.Location = New-Object System.Drawing.Point(34, 218)
    $evidence.Size = New-Object System.Drawing.Size(686, 54)
    $evidence.Multiline = $true
    $evidence.Font = New-Object System.Drawing.Font($fontName, 10)
    $window.Controls.Add($evidence)
    $owned = New-Object System.Windows.Forms.CheckBox
    $owned.Name = 'defenseOwned'
    $owned.Text = '我已确认所有权/受托保护关系'
    $owned.Location = New-Object System.Drawing.Point(34, 296)
    $owned.Size = New-Object System.Drawing.Size(310, 28)
    $owned.Font = New-Object System.Drawing.Font($fontName, 10)
    $window.Controls.Add($owned)
    $automated = New-Object System.Windows.Forms.CheckBox
    $automated.Name = 'defenseAutomation'
    $automated.Text = '授权允许低速自动化观察'
    $automated.Location = New-Object System.Drawing.Point(360, 296)
    $automated.Size = New-Object System.Drawing.Size(300, 28)
    $automated.Font = New-Object System.Drawing.Font($fontName, 10)
    $window.Controls.Add($automated)
    $status = New-GuiLabel -Text '状态：尚未登记' -Left 34 -Top 348 -Width 680 -Height 32 -Size 10 -Color $warningColor
    $window.Controls.Add($status)
    $register = New-GuiButton -Text '登记并生成防护草稿' -Left 430 -Top 410 -Width 210 -Height 42 -Action {
        $rawDomain = $domain.Text.Trim().ToLowerInvariant()
        if([string]::IsNullOrWhiteSpace($rawDomain) -or [string]::IsNullOrWhiteSpace($evidence.Text.Trim())){
            $status.Text = '状态：请先填写域名和授权/所有权证据'
            return
        }
        $slug = ($rawDomain -replace '[^a-z0-9.-]', '-')
        if([string]::IsNullOrWhiteSpace($slug)){ $slug = 'asset' }
        $folder = Join-Path $ProjectRoot 'config\defense'
        [IO.Directory]::CreateDirectory($folder) | Out-Null
        $assetPath = Join-Path $folder ($slug + '.json')
        $asset = [pscustomobject]@{
            asset_id = $slug
            domain = $rawDomain
            authorization_source = $evidence.Text.Trim()
            confirmed_owned = [bool]$owned.Checked
            allow_automated_observation = [bool]$automated.Checked
        }
        [IO.File]::WriteAllText($assetPath, ($asset | ConvertTo-Json -Depth 4), [Text.Encoding]::UTF8)
        if($owned.Checked -and $automated.Checked){
            $status.Text = '状态：已登记授权，可由人工继续生成观察计划（未联网）'
        } else {
            $status.Text = '状态：已保存为待授权草稿，补齐勾选后才能生成计划（未联网）'
        }
    } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $close = New-GuiButton -Text '关闭' -Left 654 -Top 410 -Width 100 -Height 42 -Action { $window.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)
    $window.Controls.Add($register)
    $window.Controls.Add($close)
    $window.CancelButton = $close
    Enable-SrcAutoDpiLayout -Form $window
    [void]$window.ShowDialog()
    $window.Dispose()
}

function Show-AuditSettingsWindow {
    $lines = @(
        '默认模式：仅本机回环靶场；真实目标不会自动执行。',
        '目标状态：录入 → 授权待确认 → 人工启动确认 → 可恢复任务。',
        '远程 AI：每次会话单独启用；选择“否”时本次不会调用远程模型。',
        '自动提交：永久关闭；平台只保存可人工修改的报告草稿。',
        '立即停止：停止当前本地任务并保留审计工件，之后可从会话管理恢复。'
    )
    New-SrcAutoInfoWindow -Title '审计与设置' -Summary '这里集中显示安全策略、审计保留和恢复规则；不会修改授权，也不会启动网络动作。' -Lines $lines -PrimaryText '请求停止 / 关闭' -PrimaryAction {
        param($DialogWindow)
        try {
            $stopMarker = Join-Path $ProjectRoot 'STOP'
            [IO.File]::WriteAllText($stopMarker, "stop requested by desktop console`n", [Text.Encoding]::UTF8)
            $DialogWindow.Tag = 'STOP_REQUESTED'
        } catch {
            $DialogWindow.Tag = 'STOP_MARKER_WRITE_FAILED'
        }
        $DialogWindow.Close()
    }
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
    $script:SrcAutoMainForm = $form

    $sidebar = New-Object System.Windows.Forms.Panel
    $sidebar.Location = New-Object System.Drawing.Point(0, 0)
    $sidebar.Size = New-Object System.Drawing.Size(208, 730)
    $sidebar.BackColor = $navColor
    $form.Controls.Add($sidebar)
    $sidebar.Controls.Add((New-GuiLabel -Text 'SRC-Auto' -Left 26 -Top 28 -Width 160 -Height 34 -Size 18 -Color ([System.Drawing.Color]::White) -Style ([System.Drawing.FontStyle]::Bold)))
    $sidebar.Controls.Add((New-GuiLabel -Text '安全测试控制台' -Left 28 -Top 64 -Width 150 -Height 23 -Size 9 -Color ([System.Drawing.Color]::FromArgb(200, 221, 239))))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navQuickStart' -Text '工作台' -Top 112 -Active:$true -Action {
        if($localLabButton){
            $form.ActiveControl = $localLabButton
            [void]$localLabButton.Focus()
        }
    }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navLocalLab' -Text '本地靶场' -Top 150 -Action { Show-LocalLabDashboard }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navTarget' -Text '目标与授权' -Top 188 -Action { Show-TargetWizard }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navSession' -Text '会话与任务' -Top 226 -Action { Show-SessionTaskWindow }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navProxy' -Text '代理与 API 复核' -Top 264 -Action { Show-ProxyApiReviewWindow }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navReports' -Text '发现与报告' -Top 302 -Action { Open-ReportsFolder }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navDefense' -Text '蓝队被动分析' -Top 340 -Action { Show-DefenseObservationWindow }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navAI' -Text 'AI 与工具' -Top 378 -Action { Open-AISettings }))
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navAudit' -Text '审计与设置' -Top 416 -Action { Show-AuditSettingsWindow }))
    # Offline scope review remains available as a clearly marked sub-entry;
    # it is deliberately separate from the Figma V2 execution-confirmation lane.
    $sidebar.Controls.Add((New-SidebarNavButton -Name 'navOffline' -Text '离线审阅范围' -Top 454 -Action { Show-OfflineReviewPicker }))
    $sidebar.Controls.Add((New-GuiLabel -Text '安全状态' -Left 28 -Top 570 -Width 150 -Height 24 -Size 9 -Color ([System.Drawing.Color]::FromArgb(155, 202, 176)) -Style ([System.Drawing.FontStyle]::Bold)))
    $sidebar.Controls.Add((New-GuiLabel -Text '默认安全模式' -Left 28 -Top 596 -Width 150 -Height 23 -Size 9 -Color ([System.Drawing.Color]::White)))
    $sidebar.Controls.Add((New-GuiLabel -Text '默认仅本机回环靶场' -Left 28 -Top 622 -Width 170 -Height 23 -Size 9 -Color ([System.Drawing.Color]::FromArgb(220, 235, 250))))
    $sidebar.Controls.Add((New-GuiLabel -Text '真实目标不会自动执行' -Left 28 -Top 648 -Width 165 -Height 38 -Size 9 -Color ([System.Drawing.Color]::FromArgb(255, 231, 170))))

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
    $form.Controls.Add((New-GuiLabel -Text '常用入口集中在这里：结果与报告、AI 设置和测试会话管理；不会直接启动真实目标测试。' -Left 242 -Top 470 -Width 720 -Height 24 -Size 9 -Color $mutedColor))
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
    $safety.Controls.Add((New-GuiLabel -Text "状态、报告和密钥密文均保存在：$ProjectRoot" -Left 18 -Top 59 -Width 825 -Height 20 -Size 9 -Color $safeColor))
    $form.Controls.Add($safety)
    $form.Controls.Add((New-GuiButton -Text '退出' -Left 954 -Top 680 -Width 164 -Height 32 -Action { $form.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)))
    Enable-SrcAutoDpiLayout -Form $form
    [void]$form.ShowDialog()
    $form.Dispose()
}

Show-SrcAutoMainWindow

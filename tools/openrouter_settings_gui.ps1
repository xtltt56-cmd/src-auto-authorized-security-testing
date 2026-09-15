param([switch]$NoShow)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'openrouter_settings.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object Windows.Forms.Form
$form.Text = 'SRC-Auto — OpenRouter 密钥与模型设置'
$form.Font = New-Object Drawing.Font('Microsoft YaHei UI', 10)
$form.AutoScaleMode = [Windows.Forms.AutoScaleMode]::Dpi
$form.ClientSize = New-Object Drawing.Size(780, 580)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.StartPosition = 'CenterScreen'
$form.BackColor = [Drawing.Color]::White
$script:catalog = @()

function New-OrLabel([string]$Caption, [int]$Y, [int]$Height=40){
    $control = New-Object Windows.Forms.Label
    $control.Text = $Caption
    $control.Location = New-Object Drawing.Point(24, $Y)
    $control.Size = New-Object Drawing.Size(730, $Height)
    $form.Controls.Add($control)
    return $control
}
function New-OrButton([string]$Caption, [int]$X, [int]$Y, [int]$Width=225){
    $control = New-Object Windows.Forms.Button
    $control.Text = $Caption
    $control.Location = New-Object Drawing.Point($X, $Y)
    $control.Size = New-Object Drawing.Size($Width, 38)
    $form.Controls.Add($control)
    return $control
}
$title = New-OrLabel 'OpenRouter：密钥不随模型名称变化' 20
$title.Font = New-Object Drawing.Font('Microsoft YaHei UI', 15, [Drawing.FontStyle]::Bold)
$keyStatus = New-OrLabel '' 66 30
$keyButton = New-OrButton '粘贴 / 更换密钥…' 24 100
$null = New-OrLabel '密钥留空不会被覆盖。已有密钥可继续使用，模型单独选择与保存。' 148 32
$network = New-Object Windows.Forms.CheckBox
$network.Text = '本窗口允许联网检查 OpenRouter（关闭窗口即失效）'
$network.Location = New-Object Drawing.Point(24, 182)
$network.Size = New-Object Drawing.Size(730, 30)
$form.Controls.Add($network)
$refresh = New-OrButton '刷新官方模型目录' 24 222
$free = New-Object Windows.Forms.CheckBox
$free.Text = '仅显示输入、输出价格均为零的模型'
$free.Checked = $true
$free.Location = New-Object Drawing.Point(276, 227)
$free.Size = New-Object Drawing.Size(470, 30)
$form.Controls.Add($free)
$combo = New-Object Windows.Forms.ComboBox
$combo.DropDownStyle = 'DropDown'
$combo.Location = New-Object Drawing.Point(24, 276)
$combo.Size = New-Object Drawing.Size(730, 34)
$combo.MaxDropDownItems = 10
$form.Controls.Add($combo)
$detail = New-OrLabel '请先允许联网、刷新目录；可选择或粘贴精确模型 ID。只列出支持文本和 JSON 格式的模型。' 319 52
$saveModel = New-OrButton '保存模型设置' 24 378
$check = New-OrButton '检查密钥与模型（无生成）' 274 378
$generate = New-OrButton '发送一次最小测试消息' 524 378
$status = New-OrLabel '就绪。保存和打开窗口不会启用后台 AI。测试消息仅为固定 JSON，不包含项目数据。' 431 80
$status.ForeColor = [Drawing.Color]::DarkSlateGray
$close = New-OrButton '关闭' 624 523 125
$form.CancelButton = $close

function Update-OrKeyStatus {
    $saved = Test-Path -LiteralPath (Join-Path $ProjectRoot 'config/secrets/openrouter_api_key.dpapi')
    $keyStatus.Text = if($saved){ '密钥状态：已保存 Windows 加密密文（有效性需单独检查）' } else { '密钥状态：尚未保存，请点击下方按钮粘贴' }
}
function Update-OrModelList {
    $current = $combo.Text
    $combo.Items.Clear()
    foreach($item in $script:catalog){
        if(-not $free.Checked -or ($item.inputRate -eq 0 -and $item.outputRate -eq 0)){ [void]$combo.Items.Add($item.id) }
    }
    $combo.Text = $current
}
function Invoke-OrUiCheck([bool]$Generate){
    if(-not $network.Checked){ $status.Text='请先勾选本窗口联网检查。'; return }
    if([string]::IsNullOrWhiteSpace($combo.Text)){ $status.Text='请先选择模型。'; return }
    if($Generate -and [Windows.Forms.MessageBox]::Show($form, '发送一条固定 JSON 测试消息，最多 256 输出 token。付费模型可能产生少量费用；不会启用后台 AI。', '仅本次生成测试', 'OKCancel', 'Information') -ne 'OK'){return}
    $check.Enabled=$false; $generate.Enabled=$false; $refresh.Enabled=$false
    $form.UseWaitCursor=$true
    $status.Text='正在检查，请稍候（网络超时会返回中文提示）…'
    $status.Refresh()
    try {
        $code = Test-OpenRouterSettings -ProjectRoot $ProjectRoot -ModelId $combo.Text.Trim() -AllowNetwork -Generate:$Generate
        $status.Text = Get-OpenRouterCheckMessage $code
    } finally {
        $check.Enabled=$true; $generate.Enabled=$true; $refresh.Enabled=$true
        $form.UseWaitCursor=$false
    }
}
$keyButton.Add_Click({
    & (Join-Path $PSScriptRoot 'save_openrouter_key_gui.ps1')
    Update-OrKeyStatus
})
$refresh.Add_Click({
    if(-not $network.Checked){ $status.Text='请先勾选本窗口联网检查。'; return }
    $refresh.Enabled=$false; $form.UseWaitCursor=$true
    try {
        $script:catalog = @(Get-OpenRouterModels | Sort-Object id)
        Update-OrModelList
        $status.Text = '已刷新。请选择模型后保存；旧 ID 不在目录中时必须重新选择。显示为零价的模型仍可能有免费配额限制。'
    } catch { $script:catalog=@(); Update-OrModelList; $status.Text='无法获取官方目录，请检查网络后重试；未修改已保存配置。' }
    finally { $refresh.Enabled=$true; $form.UseWaitCursor=$false }
})
$free.Add_CheckedChanged({ Update-OrModelList })
$combo.Add_TextChanged({
    $item = @($script:catalog | Where-Object { $_.id -ceq $combo.Text })
    if($item.Count -eq 1){
        $detail.Text = '{0} | 每百万 token：输入 ${1} / 输出 ${2}。目录价格仅供参考，实际以服务账单为准。' -f $item[0].name,$item[0].inputRate,$item[0].outputRate
    } else { $detail.Text = '该 ID 尚未在本次兼容目录中验证；请刷新后选择，模型显示名称不能代替 API ID。' }
})
$saveModel.Add_Click({
    try {
        Save-OpenRouterModel -ProjectRoot $ProjectRoot -ModelId $combo.Text.Trim() -Models $script:catalog
        $status.Text = '模型已保存；已备份上一次模型配置。密钥及 DeepSeek 设置未改动，下次人工审阅读取新 ID。'
    } catch { $status.Text = '未保存：请刷新目录并选择有效模型 ID；也请确认配置文件可写。' }
})
$check.Add_Click({ Invoke-OrUiCheck $false })
$generate.Add_Click({ Invoke-OrUiCheck $true })
$close.Add_Click({ $form.Close() })
Update-OrKeyStatus
try { $combo.Text = ([IO.File]::ReadAllText((Join-Path $ProjectRoot 'config/models.yaml'), [Text.Encoding]::UTF8) | ConvertFrom-Json).remote_providers.openrouter.model }
catch { $status.Text='无法读取模型配置，请检查 config/models.yaml。' }
if(-not $NoShow){ [void]$form.ShowDialog(); $form.Dispose() }

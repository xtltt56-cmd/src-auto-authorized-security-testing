param([switch]$NoShow)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'provider_secret.ps1')
. (Join-Path $PSScriptRoot 'ai_provider_settings.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
if(-not ('SrcAutoProviderDpi' -as [type])) {
    Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public static class SrcAutoProviderDpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
}
[void][SrcAutoProviderDpi]::SetProcessDPIAware()

$form = New-Object Windows.Forms.Form
$form.Text = 'SRC-Auto — 云端 AI 密钥与模型设置'
$form.Font = New-Object Drawing.Font('Microsoft YaHei UI', 10)
$form.AutoScaleMode = [Windows.Forms.AutoScaleMode]::None
$form.ClientSize = New-Object Drawing.Size(760, 630)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.StartPosition = 'CenterScreen'
$form.BackColor = [Drawing.Color]::White

function Add-Label([string]$Text,[int]$X,[int]$Y,[int]$W,[int]$H=28){
    $label=New-Object Windows.Forms.Label; $label.Text=$Text; $label.Location=New-Object Drawing.Point($X,$Y); $label.Size=New-Object Drawing.Size($W,$H); $form.Controls.Add($label); return $label
}
function Add-Button([string]$Text,[int]$X,[int]$Y,[int]$W=180){
    $button=New-Object Windows.Forms.Button; $button.Text=$Text; $button.Location=New-Object Drawing.Point($X,$Y); $button.Size=New-Object Drawing.Size($W,38); $form.Controls.Add($button); return $button
}

$title=Add-Label '只粘贴密钥即可使用官方默认模型' 24 18 700 38
$title.Font=New-Object Drawing.Font('Microsoft YaHei UI',15,[Drawing.FontStyle]::Bold)
$null=Add-Label '保存只写入当前 Windows 用户可解密的 DPAPI 密文，不联网、不启用后台调用。模型更名时可刷新目录或修改 API ID。' 24 60 710 48
$null=Add-Label '服务商' 24 120 110
$provider=New-Object Windows.Forms.ComboBox
$provider.DropDownStyle='DropDownList'; $provider.Location=New-Object Drawing.Point(140,116); $provider.Size=New-Object Drawing.Size(590,32)
[void]$provider.Items.Add('DeepSeek|deepseek'); [void]$provider.Items.Add('智谱 GLM|zhipu'); [void]$provider.Items.Add('OpenRouter|openrouter'); $provider.SelectedIndex=0
$form.Controls.Add($provider)
$null=Add-Label 'API 密钥' 24 172 110
$keyBox=New-Object Windows.Forms.TextBox
$keyBox.Location=New-Object Drawing.Point(140,168); $keyBox.Size=New-Object Drawing.Size(590,32); $keyBox.UseSystemPasswordChar=$true
$form.Controls.Add($keyBox)
$paste=Add-Button '粘贴剪贴板密钥' 140 208 185
$keyStatus=Add-Label '' 340 214 390 28
$null=Add-Label '模型 API ID' 24 266 110
$modelBox=New-Object Windows.Forms.ComboBox
$modelBox.DropDownStyle='DropDown'; $modelBox.Location=New-Object Drawing.Point(140,262); $modelBox.Size=New-Object Drawing.Size(385,32)
$form.Controls.Add($modelBox)
$official=Add-Button '恢复官方默认模型' 540 258 190
$save=Add-Button '保存密钥与模型' 140 322 190
$refresh=Add-Button '刷新官方模型目录' 345 322 190
$close=Add-Button '关闭' 550 322 180
$network=New-Object Windows.Forms.CheckBox
$network.Text='允许本次联网测试/刷新目录（不发送项目数据，可能少量计费）'; $network.Location=New-Object Drawing.Point(140,372); $network.Size=New-Object Drawing.Size(590,28); $form.Controls.Add($network)
$test=Add-Button '测试已保存的密钥与模型' 140 408 250
$status=Add-Label '请选择服务商，粘贴密钥后保存。密钥留空时只更新模型，不覆盖已有密钥。' 24 463 706 72
$status.ForeColor=[Drawing.Color]::DarkSlateGray
$notice=Add-Label '安全边界：保存不启用远程 AI。审阅仍需显式授权；不会自动扫描、确认或提交漏洞。Flash 不代表免费，以官方账户账单为准。' 24 556 706 48
$notice.ForeColor=[Drawing.Color]::DarkGreen

function Current-Provider { return (($provider.SelectedItem -split '\|')[1]) }
function Update-KeyStatus {
    $id=Current-Provider
    $saved=Test-SrcAutoProviderKeySaved -Provider $id -ProjectRoot $ProjectRoot
    $keyStatus.Text=if($saved){'密钥状态：已保存加密密文（明文不会回显）'}else{'密钥状态：尚未保存；粘贴后点击保存'}
}
function Refresh-Ui {
    $id=Current-Provider
    $definition=Get-SrcAutoProviderDefault -Provider $id
    $config=Get-SrcAutoProviderConfig -Provider $id -ProjectRoot $ProjectRoot
    $modelBox.Items.Clear(); $modelBox.Text=[string]$config.model
    Update-KeyStatus
    $refresh.Enabled=($id -in @('deepseek','openrouter'))
    $status.Text=if($id -eq 'zhipu'){'官方默认：GLM-5.3-Flash。只填密钥即可；此模型必须开启思考，测试可能需要等待。'}elseif($id -eq 'deepseek'){'官方默认：DeepSeek V4.1 Flash，API ID 为 deepseek-flash。'}else{'OpenRouter 模型可能下架；刷新目录后选择可用模型。目录列出不等于实际调用成功。'}
}
$provider.Add_SelectedIndexChanged({ $keyBox.Clear(); $network.Checked=$false; Refresh-Ui })
$paste.Add_Click({
    try {
        if([Windows.Forms.Clipboard]::ContainsText()){$keyBox.Text=[Windows.Forms.Clipboard]::GetText(); $keyBox.Focus(); $keyBox.SelectionStart=$keyBox.TextLength; $status.Text='已从剪贴板粘贴到加密输入框；请确认服务商后点击保存。'}
        else {$status.Text='剪贴板中没有文字。'}
    } catch {$status.Text='无法读取剪贴板，请点击密钥框后按 Ctrl+V。'}
})
$official.Add_Click({$modelBox.Text=[string](Get-SrcAutoProviderDefault -Provider (Current-Provider)).model; $status.Text='已恢复该服务商的官方默认模型；点击保存后生效。'})
$save.Add_Click({
    $id=Current-Provider; $secure=$null
    try {
        if($modelBox.Text.Trim().Length -gt 160 -or $modelBox.Text.Trim() -notmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]+$'){throw 'provider_model_invalid'}
        if(-not [string]::IsNullOrWhiteSpace($keyBox.Text)){
            $secure=ConvertTo-SecureString -String $keyBox.Text -AsPlainText -Force
            [void](Protect-SrcAutoProviderKey -Provider $id -SecureKey $secure -ProjectRoot $ProjectRoot)
        }
        Save-SrcAutoProviderModel -Provider $id -ModelId $modelBox.Text -ProjectRoot $ProjectRoot
        $status.Text='保存成功。默认仍不联网；请在实际人工审阅会话中显式启用该服务商。'
    } catch { $status.Text='保存失败：请检查密钥是否为空、模型 API ID 格式和项目目录权限。' }
    finally { $keyBox.Clear(); if($secure){$secure.Dispose()}; Update-KeyStatus }
})
$refresh.Add_Click({
    if(-not $network.Checked){$status.Text='请先勾选本次联网测试/刷新目录。'; return}
    $id=Current-Provider
    try {
        $refresh.Enabled=$false; $form.UseWaitCursor=$true; $status.Text='正在读取官方模型目录；不会发送项目内容……'; $status.Refresh()
        $models=@(Get-SrcAutoProviderModels -Provider $id -ProjectRoot $ProjectRoot -AllowNetwork)
        $selectedModel=$modelBox.Text
        $modelBox.Items.Clear(); foreach($item in $models){[void]$modelBox.Items.Add($item)}
        $modelBox.Text=$selectedModel
        if($models -contains $selectedModel){$status.Text='目录读取成功，当前模型已列出；实际可用性请点击测试。'}else{$status.Text='目录读取成功；当前模型未列出，请从下拉列表选择后保存。'}
    } catch { $status.Text='无法读取模型目录。请先保存有效密钥并检查网络；现有配置未修改。' }
    finally { $form.UseWaitCursor=$false; $refresh.Enabled=$true; $network.Checked=$false }
})
$test.Add_Click({
    if(-not $network.Checked){$status.Text='请先勾选本窗口联网测试。'; return}
    $id=Current-Provider
    try {
        $test.Enabled=$false; $form.UseWaitCursor=$true; $status.Text='正在执行最小连通性测试……'; $status.Refresh()
        $code=Test-SrcAutoProviderConnection -Provider $id -ProjectRoot $ProjectRoot -AllowNetwork
        $status.Text=switch($code){
            'reachable_model_available' {'连接成功：密钥有效，当前模型可调用。'}
            'reachable_model_not_listed' {'密钥可连接，但当前模型未在目录中，请更新模型 ID。'}
            default {'连接失败：' + $code + '。未显示服务端正文或密钥。'}
        }
    } catch {$status.Text='无法完成测试：请先保存密钥并检查配置。未显示异常正文。'}
    finally {$test.Enabled=$true; $form.UseWaitCursor=$false; $network.Checked=$false}
})
$close.Add_Click({$form.Close()}); $form.CancelButton=$close
Refresh-Ui
$form.AutoScaleDimensions = New-Object System.Drawing.SizeF(96, 96)
$form.AutoScaleMode = [Windows.Forms.AutoScaleMode]::Dpi
$form.Add_Shown({$form.Activate(); $form.TopMost=$true; $keyBox.Focus(); $form.TopMost=$false})
if(-not $NoShow){[void]$form.ShowDialog(); $form.Dispose()}

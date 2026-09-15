$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HelperPath = Join-Path $PSScriptRoot 'openrouter_secret.ps1'
$SecretPath = Join-Path $ProjectRoot 'config\secrets\openrouter_api_key.dpapi'
Set-Location -LiteralPath $ProjectRoot

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. $HelperPath

[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = 'SRC-Auto - 保存 OpenRouter API Key'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = New-Object System.Drawing.Size(620, 250)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$title = New-Object System.Windows.Forms.Label
$title.Text = 'OpenRouter 密钥安全保存（所有模型通用）'
$title.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 14, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(24, 20)
$title.AutoSize = $true
$form.Controls.Add($title)

$notice = New-Object System.Windows.Forms.Label
$notice.Text = "请粘贴以 sk-or- 开头的 OpenRouter API Key。`r`n输入会隐藏；只写入 D 盘 DPAPI 密文，不联网、不写日志。"
$notice.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$notice.Location = New-Object System.Drawing.Point(26, 62)
$notice.Size = New-Object System.Drawing.Size(565, 48)
$form.Controls.Add($notice)

$text = New-Object System.Windows.Forms.TextBox
$text.Location = New-Object System.Drawing.Point(28, 116)
$text.Size = New-Object System.Drawing.Size(560, 28)
$text.Font = New-Object System.Drawing.Font('Consolas', 10)
$text.UseSystemPasswordChar = $true
$text.ShortcutsEnabled = $true
$form.Controls.Add($text)

$save = New-Object System.Windows.Forms.Button
$save.Text = '粘贴后加密保存'
$save.Location = New-Object System.Drawing.Point(300, 174)
$save.Size = New-Object System.Drawing.Size(150, 38)
$save.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$form.Controls.Add($save)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = '取消'
$cancel.Location = New-Object System.Drawing.Point(468, 174)
$cancel.Size = New-Object System.Drawing.Size(120, 38)
$cancel.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$form.Controls.Add($cancel)

$form.AcceptButton = $save
$form.CancelButton = $cancel

$cancel.Add_Click({ $text.Clear(); $form.Close() })
$save.Add_Click({
    $plain = $text.Text.Trim()
    if($plain -notmatch '^sk-or-v1-[A-Za-z0-9_-]{32,}$' -or $plain -match '[\r\n\s]'){
        [System.Windows.Forms.MessageBox]::Show(
            '格式不正确。请确认粘贴的是完整 OpenRouter API Key，并且没有空格或换行。',
            '无法保存',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }
    $secure = $null
    try {
        $secure = ConvertTo-SecureString $plain -AsPlainText -Force
        Protect-OpenRouterKey -SecureKey $secure -Path $SecretPath -ProjectRoot $ProjectRoot
        $text.Clear()
        $plain = $null
        [System.Windows.Forms.MessageBox]::Show(
            "密钥已使用 Windows DPAPI 加密保存。`r`n保存过程没有产生网络请求。",
            '保存成功',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
        $form.Close()
    } catch {
        $text.Clear()
        $plain = $null
        [System.Windows.Forms.MessageBox]::Show(
            '密钥保存失败。没有输出密钥或异常正文，也没有进行网络请求。',
            '保存失败',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } finally {
        if($secure){ $secure.Dispose() }
        $secure = $null
        $plain = $null
    }
})

$form.Add_Shown({ $text.Focus() })
[void]$form.ShowDialog()
$text.Clear()
$form.Dispose()

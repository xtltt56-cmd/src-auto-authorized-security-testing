$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
Set-Location -LiteralPath $ProjectRoot

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Security
[System.Windows.Forms.Application]::EnableVisualStyles()

$fontName = 'Microsoft YaHei UI'
$titleColor = [System.Drawing.Color]::FromArgb(20, 74, 126)
$accentColor = [System.Drawing.Color]::FromArgb(30, 136, 229)
$mutedColor = [System.Drawing.Color]::FromArgb(92, 106, 120)
$safeColor = [System.Drawing.Color]::FromArgb(26, 127, 82)

function New-SessionLabel {
    param(
        [string]$Text,
        [int]$Left,
        [int]$Top,
        [int]$Width = 300,
        [int]$Height = 26,
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
    $label.AutoEllipsis = $true
    return $label
}

function New-SessionButton {
    param(
        [string]$Text,
        [int]$Left,
        [int]$Top,
        [int]$Width = 140,
        [int]$Height = 38,
        [scriptblock]$Action,
        [System.Drawing.Color]$BackColor = [System.Drawing.Color]::White,
        [System.Drawing.Color]$ForeColor = [System.Drawing.Color]::FromArgb(20, 45, 70)
    )
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Location = New-Object System.Drawing.Point($Left, $Top)
    $button.Size = New-Object System.Drawing.Size($Width, $Height)
    $button.Font = New-Object System.Drawing.Font($fontName, 9)
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(210, 220, 230)
    $button.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(238, 246, 253)
    $button.BackColor = $BackColor
    $button.ForeColor = $ForeColor
    $button.UseVisualStyleBackColor = $false
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    if($Action){ $button.Add_Click($Action) }
    return $button
}

function ConvertTo-SessionProfileName {
    param([Parameter(Mandatory = $true)][string]$ProfileName)
    $name = $ProfileName.Trim().ToLowerInvariant()
    if($name -notmatch '^[a-z0-9][a-z0-9_-]{0,63}$'){
        throw 'invalid_profile_name'
    }
    return $name
}

function Get-SessionVaultDirectory {
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $directory = [System.IO.Path]::GetFullPath((Join-Path $root 'config\sessions')).TrimEnd('\')
    if(-not $directory.StartsWith(($root + '\'), [System.StringComparison]::OrdinalIgnoreCase)){
        throw 'session_vault_outside_project'
    }
    if(-not (Test-Path -LiteralPath $directory)){
        [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    }
    return $directory
}

function Get-SessionProfilePath {
    param([Parameter(Mandatory = $true)][string]$ProfileName)
    $name = ConvertTo-SessionProfileName -ProfileName $ProfileName
    $directory = Get-SessionVaultDirectory
    $path = [System.IO.Path]::GetFullPath((Join-Path $directory ($name + '.dpapi.json')))
    if(-not $path.StartsWith(($directory + '\'), [System.StringComparison]::OrdinalIgnoreCase)){
        throw 'session_profile_outside_vault'
    }
    return $path
}

function Get-SessionEntropy {
    $source = ([System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\').ToLowerInvariant() + '|SRC-Auto|test-session-v1')
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        return $hash.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($source))
    } finally {
        $hash.Dispose()
    }
}

function Get-SessionProfiles {
    $directory = Get-SessionVaultDirectory
    $profiles = @()
    foreach($path in @(Get-ChildItem -LiteralPath $directory -Filter '*.dpapi.json' -File -ErrorAction SilentlyContinue | Sort-Object Name)){
        try {
            $document = [System.IO.File]::ReadAllText($path.FullName, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
            $headerNames = @($document.header_names | ForEach-Object { [string]$_ } | Sort-Object)
            $profiles += [pscustomobject]@{
                name = [string]$document.name
                role = [string]$document.role
                header_names = $headerNames
                path = $path.FullName
            }
        } catch {
            # A malformed file is deliberately not displayed as a usable session.
        }
    }
    return @($profiles)
}

function Save-SessionProfile {
    param(
        [Parameter(Mandatory = $true)][string]$ProfileName,
        [Parameter(Mandatory = $true)][string]$Role,
        [Parameter(Mandatory = $true)][string]$HeaderName,
        [Parameter(Mandatory = $true)][string]$HeaderValue
    )
    $name = ConvertTo-SessionProfileName -ProfileName $ProfileName
    $cleanRole = $Role.Trim()
    $cleanHeaderName = $HeaderName.Trim()
    if([string]::IsNullOrWhiteSpace($cleanRole)){ throw 'profile_role_required' }
    if([string]::IsNullOrWhiteSpace($cleanHeaderName) -or $cleanHeaderName -match '[\r\n]'){ throw 'invalid_header_name' }
    if([string]::IsNullOrEmpty($HeaderValue) -or $HeaderValue -match '[\r\n]'){ throw 'invalid_header_value' }

    $headers = [ordered]@{}
    $headers[$cleanHeaderName] = [string]$HeaderValue
    $plaintext = ConvertTo-Json -InputObject $headers -Compress
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $plainBytes = $utf8.GetBytes($plaintext)
    $entropy = Get-SessionEntropy
    $ciphertext = [System.Security.Cryptography.ProtectedData]::Protect(
        $plainBytes,
        $entropy,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    $document = [ordered]@{
        schema_version = 1
        name = $name
        role = $cleanRole
        header_names = @($cleanHeaderName)
        ciphertext = [System.Convert]::ToBase64String($ciphertext)
        created_at = [DateTime]::UtcNow.ToString('o')
    }
    $path = Get-SessionProfilePath -ProfileName $name
    $temporary = $path + '.tmp-' + [Guid]::NewGuid().ToString('N')
    try {
        [System.IO.File]::WriteAllText($temporary, (($document | ConvertTo-Json -Depth 4) + "`n"), $utf8)
        [System.IO.File]::Copy($temporary, $path, $true)
    } finally {
        if(Test-Path -LiteralPath $temporary){
            [System.IO.File]::Delete($temporary)
        }
        $HeaderValue = $null
        $plaintext = $null
    }
    return $path
}

function Remove-SessionProfile {
    param([Parameter(Mandatory = $true)][string]$ProfileName)
    $path = Get-SessionProfilePath -ProfileName $ProfileName
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)){
        return $false
    }
    [System.IO.File]::Delete($path)
    return $true
}

function Update-SessionProfileList {
    param(
        [System.Windows.Forms.ListView]$List,
        [System.Windows.Forms.Label]$Status
    )
    $List.Items.Clear()
    $profiles = @(Get-SessionProfiles)
    foreach($profile in $profiles){
        $item = New-Object System.Windows.Forms.ListViewItem([string]$profile.name)
        [void]$item.SubItems.Add([string]$profile.role)
        [void]$item.SubItems.Add((@($profile.header_names) -join ', '))
        $item.Tag = [string]$profile.name
        [void]$List.Items.Add($item)
    }
    if($profiles.Count -eq 0){
        $Status.Text = '尚未保存测试会话。列表只显示名称、角色和请求头名称。'
        $Status.ForeColor = $mutedColor
    } else {
        $Status.Text = ('已发现 {0} 个本地测试会话；请求头值不会显示。' -f $profiles.Count)
        $Status.ForeColor = $safeColor
    }
}

function Show-SessionProfileManager {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SRC-Auto - 测试会话管理'
    $form.StartPosition = 'CenterScreen'
    $form.ClientSize = New-Object System.Drawing.Size(900, 665)
    $form.MinimumSize = New-Object System.Drawing.Size(900, 665)
    $form.BackColor = [System.Drawing.Color]::FromArgb(247, 250, 252)
    $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi

    $header = New-Object System.Windows.Forms.Panel
    $header.Location = New-Object System.Drawing.Point(0, 0)
    $header.Size = New-Object System.Drawing.Size(900, 114)
    $header.BackColor = $titleColor
    $form.Controls.Add($header)
    $header.Controls.Add((New-SessionLabel -Text '测试会话管理' -Left 30 -Top 23 -Width 400 -Height 35 -Size 18 -Color ([System.Drawing.Color]::White) -Style ([System.Drawing.FontStyle]::Bold)))
    $header.Controls.Add((New-SessionLabel -Text '仅保存你已获授权的测试账号会话头；此页面不登录、不发送请求、不显示会话值。' -Left 32 -Top 66 -Width 760 -Height 27 -Size 9 -Color ([System.Drawing.Color]::FromArgb(220, 235, 250))))

    $form.Controls.Add((New-SessionLabel -Text '新建或更新会话' -Left 30 -Top 140 -Width 300 -Height 29 -Size 13 -Color $titleColor -Style ([System.Drawing.FontStyle]::Bold)))
    $form.Controls.Add((New-SessionLabel -Text '会话名称仅支持小写英文、数字、连字符和下划线。建议按测试角色命名，例如 owner-test。' -Left 30 -Top 171 -Width 820 -Height 25 -Size 9 -Color $mutedColor))

    $labels = @(
        @{ text = '会话名称'; top = 214 },
        @{ text = '测试角色'; top = 258 },
        @{ text = '请求头名称'; top = 302 },
        @{ text = '请求头值'; top = 346 }
    )
    foreach($entry in $labels){
        $form.Controls.Add((New-SessionLabel -Text $entry.text -Left 30 -Top $entry.top -Width 130 -Height 25 -Size 9 -Color $mutedColor))
    }

    $profileName = New-Object System.Windows.Forms.TextBox
    $profileName.Name = 'sessionProfileName'
    $profileName.Location = New-Object System.Drawing.Point(165, 210)
    $profileName.Size = New-Object System.Drawing.Size(675, 28)
    $profileName.Font = New-Object System.Drawing.Font($fontName, 9)
    $form.Controls.Add($profileName)

    $role = New-Object System.Windows.Forms.TextBox
    $role.Name = 'sessionProfileRole'
$role.Location = New-Object System.Drawing.Point(165, 254)
$role.Size = New-Object System.Drawing.Size(675, 28)
$role.Font = New-Object System.Drawing.Font($fontName, 9)
$form.Controls.Add($role)

    $headerName = New-Object System.Windows.Forms.TextBox
    $headerName.Name = 'sessionHeaderName'
    $headerName.Text = 'Authorization'
    $headerName.Location = New-Object System.Drawing.Point(165, 298)
    $headerName.Size = New-Object System.Drawing.Size(675, 28)
    $headerName.Font = New-Object System.Drawing.Font($fontName, 9)
    $form.Controls.Add($headerName)

    $headerValue = New-Object System.Windows.Forms.TextBox
    $headerValue.Name = 'sessionHeaderValue'
    $headerValue.Location = New-Object System.Drawing.Point(165, 342)
    $headerValue.Size = New-Object System.Drawing.Size(675, 28)
    $headerValue.Font = New-Object System.Drawing.Font('Consolas', 9)
    $headerValue.UseSystemPasswordChar = $true
    $headerValue.ShortcutsEnabled = $true
    $form.Controls.Add($headerValue)

    $sessionList = New-Object System.Windows.Forms.ListView
    $sessionList.Name = 'sessionProfileList'
    $sessionList.Location = New-Object System.Drawing.Point(30, 444)
    $sessionList.Size = New-Object System.Drawing.Size(810, 120)
    $sessionList.View = [System.Windows.Forms.View]::Details
    $sessionList.FullRowSelect = $true
    $sessionList.GridLines = $true
    $sessionList.HideSelection = $false
    $sessionList.Font = New-Object System.Drawing.Font($fontName, 9)
    [void]$sessionList.Columns.Add('会话名称', 260)
    [void]$sessionList.Columns.Add('测试角色', 260)
    [void]$sessionList.Columns.Add('保存的请求头名称', 270)
    $form.Controls.Add($sessionList)

    $status = New-SessionLabel -Text '正在读取本地测试会话……' -Left 30 -Top 576 -Width 810 -Height 24 -Size 9 -Color $mutedColor
    $status.Name = 'sessionProfileStatus'
    $form.Controls.Add($status)

    $refreshAction = { Update-SessionProfileList -List $sessionList -Status $status }
    $save = New-SessionButton -Text '加密保存会话' -Left 522 -Top 390 -Width 152 -Height 38 -Action {
        try {
            $name = $profileName.Text
            $existingPath = Get-SessionProfilePath -ProfileName $name
            if(Test-Path -LiteralPath $existingPath -PathType Leaf){
                $choice = [System.Windows.Forms.MessageBox]::Show(
                    '同名会话已经存在。是否只覆盖这个会话？',
                    '确认更新',
                    [System.Windows.Forms.MessageBoxButtons]::YesNo,
                    [System.Windows.Forms.MessageBoxIcon]::Warning
                )
                if($choice -ne [System.Windows.Forms.DialogResult]::Yes){ return }
            }
            [void](Save-SessionProfile -ProfileName $name -Role $role.Text -HeaderName $headerName.Text -HeaderValue $headerValue.Text)
            $headerValue.Clear()
            & $refreshAction
            [System.Windows.Forms.MessageBox]::Show(
                '测试会话已使用当前 Windows 用户的 DPAPI 加密保存。此过程没有发起网络请求。',
                '保存成功',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information
            ) | Out-Null
        } catch {
            $headerValue.Clear()
            [System.Windows.Forms.MessageBox]::Show(
                '无法保存测试会话。请检查名称、角色和请求头格式；没有输出会话值，也没有执行网络操作。',
                '保存失败',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            ) | Out-Null
        }
    } -BackColor $accentColor -ForeColor ([System.Drawing.Color]::White)
    $delete = New-SessionButton -Text '删除选中会话' -Left 688 -Top 390 -Width 152 -Height 38 -Action {
        if($sessionList.SelectedItems.Count -ne 1){
            [System.Windows.Forms.MessageBox]::Show('请先在列表中选择一个会话。', '需要选择', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
            return
        }
        $name = [string]$sessionList.SelectedItems[0].Tag
        $choice = [System.Windows.Forms.MessageBox]::Show(
            ('是否删除测试会话 “{0}”？此操作只删除该名称对应的本地密文文件。' -f $name),
            '确认删除',
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        )
        if($choice -eq [System.Windows.Forms.DialogResult]::Yes){
            [void](Remove-SessionProfile -ProfileName $name)
            & $refreshAction
        }
    }
    $close = New-SessionButton -Text '关闭' -Left 702 -Top 605 -Width 138 -Height 35 -Action { $headerValue.Clear(); $form.Close() } -BackColor $titleColor -ForeColor ([System.Drawing.Color]::White)
    $form.Controls.Add($save)
    $form.Controls.Add($delete)
    $form.Controls.Add($close)
    $form.Controls.Add((New-SessionLabel -Text '请求头值仅在内存中短暂处理，列表和本地报告永远不显示该值。' -Left 30 -Top 608 -Width 650 -Height 22 -Size 9 -Color $safeColor))
    $form.AcceptButton = $save
    $form.CancelButton = $close
    & $refreshAction
    $form.Add_Shown({ $profileName.Focus() })
    [void]$form.ShowDialog()
    $headerValue.Clear()
    $form.Dispose()
}

Show-SessionProfileManager

function Assert-DeepSeekSecretPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    if(-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)){
        throw 'deepseek_secret_path_outside_project'
    }
    return $full
}

function Protect-DeepSeekKey {
    param(
        [Parameter(Mandatory = $true)][System.Security.SecureString]$SecureKey,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    if($SecureKey.Length -le 0){ throw 'deepseek_secret_empty' }
    $full = Assert-DeepSeekSecretPath -Path $Path -ProjectRoot $ProjectRoot
    $encrypted = $SecureKey | ConvertFrom-SecureString
    if([string]::IsNullOrWhiteSpace($encrypted)){ throw 'deepseek_secret_encrypt_failed' }
    $parent = [System.IO.Path]::GetDirectoryName($full)
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    [System.IO.File]::WriteAllText($full, $encrypted, (New-Object System.Text.UTF8Encoding($false)))
}

function Unprotect-DeepSeekKey {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $full = Assert-DeepSeekSecretPath -Path $Path -ProjectRoot $ProjectRoot
    if(-not [System.IO.File]::Exists($full)){ throw 'deepseek_secret_missing' }
    $encrypted = [System.IO.File]::ReadAllText($full, [System.Text.Encoding]::UTF8).Trim()
    if([string]::IsNullOrWhiteSpace($encrypted)){ throw 'deepseek_secret_empty' }
    $secure = $encrypted | ConvertTo-SecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if([string]::IsNullOrWhiteSpace($plain)){ throw 'deepseek_secret_decrypt_failed' }
        return $plain
    } finally {
        if($pointer -ne [IntPtr]::Zero){
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        if($secure){ $secure.Dispose() }
    }
}

Import-Module Microsoft.PowerShell.Security -ErrorAction Stop

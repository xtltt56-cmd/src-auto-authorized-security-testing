function Get-SrcAutoProviderSecretPath {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    return [System.IO.Path]::Combine($root, 'config', 'secrets', ($Provider + '_api_key.dpapi'))
}

function Protect-SrcAutoProviderKey {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][System.Security.SecureString]$SecureKey,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    if($SecureKey.Length -le 0){ throw 'provider_secret_empty' }
    $path = Get-SrcAutoProviderSecretPath -Provider $Provider -ProjectRoot $ProjectRoot
    $encrypted = $SecureKey | ConvertFrom-SecureString
    if([string]::IsNullOrWhiteSpace($encrypted)){ throw 'provider_secret_encrypt_failed' }
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path)) | Out-Null
    $temporary = $path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [System.IO.File]::WriteAllText($temporary, $encrypted, (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temporary -Destination $path -Force
    } finally {
        if([System.IO.File]::Exists($temporary)){ Remove-Item -LiteralPath $temporary -Force }
    }
    return $path
}

function Unprotect-SrcAutoProviderKey {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $path = Get-SrcAutoProviderSecretPath -Provider $Provider -ProjectRoot $ProjectRoot
    if(-not [System.IO.File]::Exists($path)){ throw 'provider_secret_missing' }
    $encrypted = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8).Trim()
    if([string]::IsNullOrWhiteSpace($encrypted)){ throw 'provider_secret_empty' }
    $secure = $encrypted | ConvertTo-SecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if([string]::IsNullOrWhiteSpace($plain)){ throw 'provider_secret_decrypt_failed' }
        return $plain
    } finally {
        if($pointer -ne [IntPtr]::Zero){ [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        if($secure){ $secure.Dispose() }
    }
}

function Test-SrcAutoProviderKeySaved {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    return [System.IO.File]::Exists((Get-SrcAutoProviderSecretPath -Provider $Provider -ProjectRoot $ProjectRoot))
}

# ConvertTo/From-SecureString are built into Windows PowerShell.  Do not force
# reload Microsoft.PowerShell.Security: the host GUI may already have loaded
# its type data, and a second import can fail before the settings form opens.

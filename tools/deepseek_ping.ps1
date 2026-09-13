$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ResultPath = Join-Path $ProjectRoot 'validation\deepseek_ping_latest.json'
$SecretHelperPath = Join-Path $ProjectRoot 'tools\deepseek_secret.ps1'
$SecretPath = Join-Path $ProjectRoot 'config\secrets\deepseek_api_key.dpapi'
$ModelId = 'deepseek-v4-flash'
$ModelDisplayName = 'DeepSeek V4 Flash（官方滚动最新版）'
$ModelsEndpoint = 'https://api.deepseek.com/models'
$CatalogAliases = @('deepseek-v4-flash', 'deepseek-flash')
Set-Location -LiteralPath $ProjectRoot

function Write-PingResult {
    param(
        [string]$Status,
        [bool]$NetworkContact,
        [Nullable[int]]$HttpStatus = $null,
        [bool]$ModelPresent = $false,
        [string]$ErrorCode = ''
    )
    $result = [ordered]@{
        status = $Status
        network_contact = $NetworkContact
        http_status = $HttpStatus
        model = $ModelId
        display_name = $ModelDisplayName
        catalog_model = ''
        model_present = $ModelPresent
        request_count = if($NetworkContact){ 1 } else { 0 }
        error = $ErrorCode
        checked_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $parent = Split-Path -Parent $ResultPath
    if(-not (Test-Path -LiteralPath $parent)){ New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    [pscustomobject]$result
}

function Read-SessionKey {
    try {
        $secureKey = Read-Host '请输入新的 DeepSeek API Key（输入不回显，仅本次检测，不会写入文件）' -AsSecureString
    } catch {
        return $null
    }
    if($null -eq $secureKey){ return $null }
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } catch {
        return $null
    } finally {
        if($pointer -ne [IntPtr]::Zero){
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        $secureKey.Dispose()
    }
}

Write-Host "$ModelDisplayName 轻量连通性检测" -ForegroundColor Cyan
Write-Host "本检测只访问 $ModelsEndpoint，不发送 Finding、靶场 URL 或文件内容。" -ForegroundColor Yellow
$answer = (Read-Host '是否授权本次单次连通性检测？输入 Y/是 继续，N/否/回车 拒绝').Trim().ToLowerInvariant()
if($answer -notin @('y', 'yes', '是', '启用')){
    $blocked = Write-PingResult -Status 'blocked_by_user' -NetworkContact:$false -ErrorCode 'remote_ai_disabled_for_session'
    Write-Host '已拒绝；没有发起网络请求。' -ForegroundColor Green
    $blocked | ConvertTo-Json -Compress
    exit 0
}

$key = $null
if((Test-Path -LiteralPath $SecretPath) -and (Test-Path -LiteralPath $SecretHelperPath)){
    try {
        . $SecretHelperPath
        $key = Unprotect-DeepSeekKey -Path $SecretPath -ProjectRoot $ProjectRoot
        if(-not [string]::IsNullOrWhiteSpace($key)){
            Write-Host '已读取当前 Windows 用户的 DPAPI 加密密钥；密钥不会显示或写入日志。' -ForegroundColor Green
        }
    } catch {
        $key = $null
        Write-Host '已保存密钥无法解密，将改为本次临时输入；不会输出密钥。' -ForegroundColor Yellow
    }
}
if([string]::IsNullOrWhiteSpace($key)){
    $key = Read-SessionKey
}
if([string]::IsNullOrWhiteSpace($key)){
    $missing = Write-PingResult -Status 'blocked_missing_key' -NetworkContact:$false -ErrorCode 'provider_key_missing'
    Write-Host '未输入有效密钥；没有发起网络请求。' -ForegroundColor Yellow
    $missing | ConvertTo-Json -Compress
    exit 0
}

$env:DEEPSEEK_API_KEY = $key
$env:SRC_AUTO_REMOTE_AI_CONSENT = 'enabled'
$env:SRC_AUTO_DEEPSEEK_CONSENT = 'enabled'
$request = $null
$response = $null
$reader = $null
try {
    $request = [System.Net.WebRequest]::Create($ModelsEndpoint)
    $request.Method = 'GET'
    $request.Timeout = 10000
    $request.ReadWriteTimeout = 10000
    $request.Headers['Authorization'] = 'Bearer ' + $key
    $response = $request.GetResponse()
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    $body = $reader.ReadToEnd()
    $document = $body | ConvertFrom-Json
    $ids = @($document.data | ForEach-Object { [string]$_.id })
    $catalogModel = @($CatalogAliases | Where-Object { $ids -contains $_ } | Select-Object -First 1)
    $present = $catalogModel.Count -gt 0
    if($present){
        $ok = Write-PingResult -Status 'reachable_authenticated' -NetworkContact:$true -HttpStatus ([int]$response.StatusCode) -ModelPresent:$true
        $ok.catalog_model = [string]$catalogModel[0]
        $ok | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
        Write-Host "连通性检测成功：密钥有效，$ModelDisplayName 可用；实际请求 ID 为 $ModelId，目录标识为 $($catalogModel[0])。" -ForegroundColor Green
    } else {
        $ok = Write-PingResult -Status 'reachable_model_not_listed' -NetworkContact:$true -HttpStatus ([int]$response.StatusCode) -ModelPresent:$false -ErrorCode 'deepseek_v4_flash_not_listed'
        Write-Host "已连接到 DeepSeek，但模型列表中没有 $ModelId。" -ForegroundColor Yellow
    }
    $ok | ConvertTo-Json -Compress
} catch [System.Net.WebException] {
    $httpStatus = $null
    if($_.Exception.Response){ $httpStatus = [int]$_.Exception.Response.StatusCode }
    $code = if($null -ne $httpStatus){ 'http_' + $httpStatus } else { 'network_error' }
    $failed = Write-PingResult -Status 'request_failed' -NetworkContact:$true -HttpStatus $httpStatus -ErrorCode $code
    Write-Host ('连通性检测失败：' + $code + '。未输出响应正文。') -ForegroundColor Red
    $failed | ConvertTo-Json -Compress
} catch {
    $failed = Write-PingResult -Status 'request_failed' -NetworkContact:$true -ErrorCode 'unexpected_error'
    Write-Host '连通性检测失败：unexpected_error。未输出响应正文。' -ForegroundColor Red
    $failed | ConvertTo-Json -Compress
} finally {
    if($reader){ $reader.Dispose() }
    if($response){ $response.Dispose() }
    $env:DEEPSEEK_API_KEY = $null
    $env:SRC_AUTO_DEEPSEEK_CONSENT = 'disabled'
    $env:SRC_AUTO_REMOTE_AI_CONSENT = 'disabled'
    $key = $null
}

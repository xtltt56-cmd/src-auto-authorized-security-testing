$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HelperPath = Join-Path $PSScriptRoot 'deepseek_secret.ps1'
$SecretPath = Join-Path $ProjectRoot 'config\secrets\deepseek_api_key.dpapi'
Set-Location -LiteralPath $ProjectRoot

Write-Host 'DeepSeek API 密钥一次性加密保存' -ForegroundColor Cyan
Write-Host '密钥将由当前 Windows 用户的 DPAPI 加密，只保存到指定 D 盘项目目录。' -ForegroundColor Yellow
Write-Host '输入内容不会回显，也不会写入日志、数据库或报告。' -ForegroundColor Yellow

$secureKey = $null
try {
    . $HelperPath
    $secureKey = Read-Host '请粘贴新的 DeepSeek API Key，然后按回车' -AsSecureString
    if($null -eq $secureKey -or $secureKey.Length -le 0){
        Write-Host '未输入有效密钥；没有创建或覆盖加密文件。' -ForegroundColor Yellow
        exit 2
    }
    Protect-DeepSeekKey -SecureKey $secureKey -Path $SecretPath -ProjectRoot $ProjectRoot
    Write-Host '密钥已使用 DPAPI 加密保存。' -ForegroundColor Green
    Write-Host ("保存位置：{0}" -f $SecretPath) -ForegroundColor Green
    Write-Host '以后启动时选择“是”即可自动加载；选择“否”不会读取或解密。' -ForegroundColor Cyan
    exit 0
} catch {
    Write-Host '密钥保存失败；没有输出密钥或异常正文。请关闭窗口后重试。' -ForegroundColor Red
    exit 1
} finally {
    if($secureKey){ $secureKey.Dispose() }
    $secureKey = $null
}

[CmdletBinding()]
param(
    [switch]$OpenLatest
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $ProjectRoot 'VERSION'
$repository = 'xtltt56-cmd/src-auto-authorized-security-testing'
$latestPage = "https://github.com/$repository/releases/latest"

if(-not (Test-Path -LiteralPath $versionPath)){
    Write-Host '未找到 VERSION，无法确定当前版本。' -ForegroundColor Red
    exit 2
}

$currentText = (Get-Content -LiteralPath $versionPath -Raw).Trim()
$currentVersion = $null
if(-not [version]::TryParse($currentText, [ref]$currentVersion)){
    Write-Host "当前版本格式无效：$currentText" -ForegroundColor Red
    exit 2
}

try {
    $headers = @{
        'Accept' = 'application/vnd.github+json'
        'User-Agent' = 'SRC-Auto-Update-Check'
    }
    $release = Invoke-RestMethod -Method Get -Uri "https://api.github.com/repos/$repository/releases/latest" -Headers $headers -TimeoutSec 15
} catch {
    Write-Host '无法读取 GitHub 最新正式版信息；没有下载或修改任何文件。' -ForegroundColor Yellow
    exit 3
}

$tag = [string]$release.tag_name
$latestText = $tag.TrimStart('v')
$latestVersion = $null
if(-not [version]::TryParse($latestText, [ref]$latestVersion)){
    Write-Host "GitHub 最新版本标签无法识别：$tag" -ForegroundColor Yellow
    exit 4
}

Write-Host "当前版本：v$currentText"
Write-Host "最新正式版：$tag"
if($latestVersion -gt $currentVersion){
    Write-Host '发现新版本。请查看发布说明并人工确认升级。' -ForegroundColor Cyan
    Write-Host $latestPage
    if($OpenLatest){ Start-Process -FilePath $latestPage | Out-Null }
    exit 10
}

Write-Host '当前已经是最新正式版。' -ForegroundColor Green
exit 0

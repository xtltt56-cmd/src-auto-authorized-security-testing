[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$PythonRuntimePath,
    [switch]$SkipDashboardBuild,
    [switch]$KeepStaging
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if([string]::IsNullOrWhiteSpace($OutputDirectory)){
    $OutputDirectory = Join-Path $ProjectRoot 'artifacts\release'
}
$projectFull = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$outputFull = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if(-not $outputFull.StartsWith($projectFull + '\', [StringComparison]::OrdinalIgnoreCase)){
    throw '发布输出目录必须位于项目目录内。'
}

$version = (Get-Content -LiteralPath (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
if($version -notmatch '^\d+\.\d+\.\d+$'){ throw "VERSION 不是语义化版本：$version" }
$commit = (& git -C $ProjectRoot rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$'){ throw '无法读取 Git 提交。' }

$distIndex = Join-Path $ProjectRoot 'dashboard\dist\index.html'
if(-not (Test-Path -LiteralPath $distIndex)){
    if($SkipDashboardBuild){ throw 'Dashboard 尚未构建。' }
    $node = @(
        (Join-Path $ProjectRoot 'runtime\node-v22.23.0-win-x64\node.exe'),
        (Get-Command node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if(-not $node){ throw '未找到 Node.js，无法构建 Dashboard。' }
    $npmCli = Join-Path (Split-Path -Parent $node) 'node_modules\npm\bin\npm-cli.js'
    if(-not (Test-Path -LiteralPath $npmCli)){ throw '未找到 npm-cli.js。' }
    & $node $npmCli run build --prefix (Join-Path $ProjectRoot 'dashboard')
    if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $distIndex)){ throw 'Dashboard 生产构建失败。' }
}

New-Item -ItemType Directory -Force -Path $outputFull | Out-Null
$stagingParent = Join-Path $outputFull 'staging'
$stagingRoot = Join-Path $stagingParent 'SRC-Auto'
foreach($target in @($stagingParent)){
    $targetFull = [IO.Path]::GetFullPath($target)
    if(-not $targetFull.StartsWith($outputFull + '\', [StringComparison]::OrdinalIgnoreCase)){
        throw '拒绝清理发布目录以外的路径。'
    }
    if(Test-Path -LiteralPath $targetFull){ Remove-Item -LiteralPath $targetFull -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

$rootFiles = @(
    'VERSION', 'requirements-runtime.txt', 'pyproject.toml',
    'START_SYSTEM.ps1', 'START.bat', 'START_DASHBOARD.bat', 'STOP.bat', 'STATUS.bat', 'CHECK_UPDATE.bat',
    'README.md', 'USER_MANUAL.md', 'OPERATIONS.md', 'POLICY.md', 'ARCHITECTURE.md',
    'KNOWN_ISSUES.md', 'RELEASE_MANIFEST.md', 'tools.lock.yaml', 'docker-compose.local-labs.yml'
)
$deniedFragments = @(
    'config\secrets', 'config\sessions', 'data', 'reports', 'validation',
    'runs', 'logs', 'evidence', '.git', 'vendor', '__pycache__'
)

function Test-ReleasePathAllowed([string]$RelativePath){
    $unix = $RelativePath.Replace('\', '/')
    if($rootFiles -contains $unix){ return $true }
    if($unix.StartsWith('src_auto/')){ return -not $unix.Contains('/__pycache__/') }
    if($unix.StartsWith('lab/')){ return $true }
    if($unix.StartsWith('tools/')){ return $unix -ne 'tools/restore-pre-storybook-baseline.ps1' }
    if($unix.StartsWith('docs/')){
        return -not ($unix.StartsWith('docs/design/') -or $unix.StartsWith('docs/superpowers/'))
    }
    if($unix.StartsWith('config/')){
        if($unix.StartsWith('config/secrets/') -or $unix.StartsWith('config/sessions/')){ return $false }
        if($unix.StartsWith('config/targets/')){
            return $unix -eq 'config/targets/README.md' -or
                $unix.StartsWith('config/targets/local-lab/') -or
                $unix.StartsWith('config/targets/dvwa-local/') -or
                $unix.StartsWith('config/targets/juice-shop-local/') -or
                $unix.StartsWith('config/targets/vampi-local/')
        }
        return $true
    }
    return $false
}

$tracked = @(& git -C $ProjectRoot ls-files)
if($LASTEXITCODE -ne 0){ throw 'git ls-files 失败。' }
foreach($relative in $tracked){
    if(-not (Test-ReleasePathAllowed $relative)){ continue }
    $source = Join-Path $ProjectRoot $relative
    if(-not (Test-Path -LiteralPath $source -PathType Leaf)){ continue }
    $destination = Join-Path $stagingRoot $relative
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$distDestination = Join-Path $stagingRoot 'dashboard\dist'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $distDestination) | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'dashboard\dist') -Destination $distDestination -Recurse -Force

$runtimeIncluded = $false
if(-not [string]::IsNullOrWhiteSpace($PythonRuntimePath)){
    $pythonRoot = [IO.Path]::GetFullPath($PythonRuntimePath)
    if(-not (Test-Path -LiteralPath (Join-Path $pythonRoot 'python.exe'))){
        throw "PythonRuntimePath 中没有 python.exe：$pythonRoot"
    }
    $runtimeDestination = Join-Path $stagingRoot 'runtime\python'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $runtimeDestination) | Out-Null
    Copy-Item -LiteralPath $pythonRoot -Destination $runtimeDestination -Recurse -Force
    $runtimePrunePaths = @(
        'Lib\test', 'Lib\site-packages', 'Scripts', 'include', 'libs', 'Tools', 'Doc'
    )
    foreach($relativePrunePath in $runtimePrunePaths){
        $prunePath = [IO.Path]::GetFullPath((Join-Path $runtimeDestination $relativePrunePath))
        if(-not $prunePath.StartsWith($runtimeDestination + '\', [StringComparison]::OrdinalIgnoreCase)){
            throw '拒绝清理便携 Python 目录以外的路径。'
        }
        if(Test-Path -LiteralPath $prunePath){
            Remove-Item -LiteralPath $prunePath -Recurse -Force
        }
    }
    $runtimeIncluded = Test-Path -LiteralPath (Join-Path $runtimeDestination 'python.exe')
}

$manifest = [ordered]@{
    product = 'SRC-Auto'
    version = $version
    tag = "v$version"
    commit = $commit
    built_at_utc = [DateTime]::UtcNow.ToString('o')
    platform = 'windows-x64'
    dashboard_prebuilt = $true
    python_runtime_included = $runtimeIncluded
    default_network_mode = 'loopback-only'
    automatic_real_target_scan = $false
    automatic_submission = $false
    source_repository = 'https://github.com/xtltt56-cmd/src-auto-authorized-security-testing'
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stagingRoot 'release-manifest.json') -Encoding UTF8

$quickStart = @'
SRC-Auto Windows 快速开始

1. 双击 START_DASHBOARD.bat 打开简体中文可视化控制台。
2. 如果需要本地靶场，请先安装并启动 Docker Desktop；所有靶场端口必须只绑定 127.0.0.1。
3. 真实目标必须先由人工确认授权、范围和时间窗；平台不会自动提交任何报告。
4. 双击 CHECK_UPDATE.bat 可人工检查 GitHub 最新正式版；启动平台不会静默联网更新。

详细说明见 USER_MANUAL.md 和 POLICY.md。
'@
$quickStart | Set-Content -LiteralPath (Join-Path $stagingRoot '快速开始.txt') -Encoding UTF8

$forbidden = @()
Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($stagingRoot.Length).TrimStart('\')
    $isRuntimePath = $relative.StartsWith('runtime\', [StringComparison]::OrdinalIgnoreCase)
    if($isRuntimePath){
        $runtimeAllowed = $runtimeIncluded -and
            $relative.StartsWith('runtime\python\', [StringComparison]::OrdinalIgnoreCase)
        if(-not $runtimeAllowed){ $forbidden += $relative }
    } else {
        foreach($fragment in $deniedFragments){
            if($relative -eq $fragment -or $relative.StartsWith($fragment + '\', [StringComparison]::OrdinalIgnoreCase)){
                $forbidden += $relative
            }
        }
    }
}
if($forbidden.Count -gt 0){
    $forbiddenSample = $forbidden | Select-Object -First 20
    throw "分发包出现禁止路径（共 $($forbidden.Count) 项，仅显示前 20 项）：$($forbiddenSample -join ', ')"
}

$secretPattern = 'sk-or-v1-[A-Za-z0-9_-]{24,}|sk-[0-9A-Fa-f]{32,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----'
$secretHits = @()
Get-ChildItem -LiteralPath $stagingRoot -Recurse -File | Where-Object { $_.Length -le 10MB } | ForEach-Object {
    try {
        if(Select-String -LiteralPath $_.FullName -Pattern $secretPattern -Quiet -ErrorAction Stop){
            $secretHits += $_.FullName.Substring($stagingRoot.Length).TrimStart('\')
        }
    } catch { }
}
if($secretHits.Count -gt 0){
    $secretSample = $secretHits | Select-Object -First 20
    throw "分发包疑似包含敏感凭据（共 $($secretHits.Count) 项，仅显示前 20 项），已停止：$($secretSample -join ', ')"
}

$stableZip = Join-Path $outputFull 'SRC-Auto-Windows-x64.zip'
$versionedZip = Join-Path $outputFull "SRC-Auto-Windows-x64-v$version.zip"
foreach($zip in @($stableZip, $versionedZip)){
    $zipFull = [IO.Path]::GetFullPath($zip)
    if(-not $zipFull.StartsWith($outputFull + '\', [StringComparison]::OrdinalIgnoreCase)){ throw 'ZIP 路径越界。' }
    if(Test-Path -LiteralPath $zipFull){ Remove-Item -LiteralPath $zipFull -Force }
}
Compress-Archive -LiteralPath $stagingRoot -DestinationPath $versionedZip -CompressionLevel Optimal
Copy-Item -LiteralPath $versionedZip -Destination $stableZip -Force

$checksumPath = Join-Path $outputFull 'SHA256SUMS.txt'
$checksumLines = foreach($asset in @($stableZip, $versionedZip)){
    $hash = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $([IO.Path]::GetFileName($asset))"
}
$checksumLines | Set-Content -LiteralPath $checksumPath -Encoding ASCII
Copy-Item -LiteralPath (Join-Path $stagingRoot 'release-manifest.json') -Destination (Join-Path $outputFull 'release-manifest.json') -Force

if(-not $KeepStaging){ Remove-Item -LiteralPath $stagingParent -Recurse -Force }
Write-Host "发布包已生成：$stableZip" -ForegroundColor Green
Write-Host "版本化包：$versionedZip" -ForegroundColor Green
Write-Host "校验文件：$checksumPath" -ForegroundColor Green

[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 4173,
    [switch]$NoBrowser,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DashboardRoot = Join-Path $ProjectRoot 'dashboard'
$DistIndex = Join-Path $DashboardRoot 'dist\index.html'

if(-not (Test-Path -LiteralPath $DashboardRoot)){
    Write-Host "未找到 Dashboard 目录：$DashboardRoot" -ForegroundColor Red
    exit 2
}

$nodeCandidates = @(
    (Join-Path $ProjectRoot 'runtime\node-v22.23.0-win-x64\node.exe'),
    (Get-Command node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
)
$nodeExe = $nodeCandidates | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if(-not $nodeExe){
    Write-Host '未找到项目专用 Node.js 运行时。请先安装到 D 盘 runtime 目录。' -ForegroundColor Red
    exit 3
}

$viteEntry = Join-Path $DashboardRoot 'node_modules\vite\bin\vite.js'
if(-not (Test-Path -LiteralPath $viteEntry)){
    Write-Host '未找到 Vite 依赖；不会联网安装依赖，请先在 dashboard 目录完成离线依赖准备。' -ForegroundColor Red
    exit 4
}

if(-not (Test-Path -LiteralPath $DistIndex)){
    $npmCli = Join-Path (Split-Path -Parent $nodeExe) 'node_modules\npm\bin\npm-cli.js'
    if(-not (Test-Path -LiteralPath $npmCli)){
        Write-Host 'Dashboard 尚未构建，且项目专用 npm 不可用。' -ForegroundColor Red
        exit 5
    }
    Write-Host '首次启动：正在构建本地 Dashboard（不访问真实目标）……' -ForegroundColor Cyan
    & $nodeExe $npmCli run build --prefix $DashboardRoot
    if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $DistIndex)){
        Write-Host 'Dashboard 构建失败，未启动服务。' -ForegroundColor Red
        exit 6
    }
}

$url = "http://127.0.0.1:$Port/"
$arguments = @($viteEntry, '--host', '127.0.0.1', '--port', "$Port")

if($Foreground){
    Write-Host "Dashboard 正在前台运行：$url" -ForegroundColor Green
    Write-Host '仅监听 127.0.0.1；按 Ctrl+C 停止。' -ForegroundColor Yellow
    & $nodeExe @arguments
    exit $LASTEXITCODE
}

$logDirectory = Join-Path $ProjectRoot 'validation\dashboard'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$stdoutLog = Join-Path $logDirectory 'dashboard.stdout.log'
$stderrLog = Join-Path $logDirectory 'dashboard.stderr.log'

try {
    $server = Start-Process -FilePath $nodeExe -ArgumentList $arguments -WorkingDirectory $DashboardRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru
} catch {
    Write-Host "Dashboard 进程启动失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 7
}

$ready = $false
for($attempt = 0; $attempt -lt 30; $attempt++){
    Start-Sleep -Milliseconds 250
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
        if($response.StatusCode -ge 200 -and $response.StatusCode -lt 500){
            $ready = $true
            break
        }
    } catch {
        if($server.HasExited){ break }
    }
}

if(-not $ready){
    if(-not $server.HasExited){ Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
    Write-Host "Dashboard 未在规定时间内就绪；请查看 $stderrLog" -ForegroundColor Red
    exit 8
}

Write-Host "Dashboard 已启动：$url" -ForegroundColor Green
Write-Host "进程 ID：$($server.Id)；日志：$logDirectory" -ForegroundColor DarkGray
Write-Host '网络接触：仅本机回环；此入口不会启动靶场、不会访问真实目标、不会调用远程 AI。' -ForegroundColor Yellow

if(-not $NoBrowser){
    Start-Process -FilePath $url | Out-Null
}
exit 0

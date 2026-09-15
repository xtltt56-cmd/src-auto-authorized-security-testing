[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 4173,
    [ValidateRange(1024, 65535)]
    [int]$ApiPort = 4174,
    [ValidateSet('overview','labs','targets','review','findings','settings')]
    [string]$InitialPage = 'overview',
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
$logDirectory = Join-Path $ProjectRoot 'validation\dashboard'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

if(-not (Test-Path -LiteralPath $DashboardRoot)){
    Write-Host "未找到 Dashboard 目录：$DashboardRoot" -ForegroundColor Red
    exit 2
}

if(-not (Test-Path -LiteralPath $DistIndex)){
    $nodeCandidates = @(
        (Join-Path $ProjectRoot 'runtime\node-v22.23.0-win-x64\node.exe'),
        (Get-Command node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    )
    $nodeExe = $nodeCandidates | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if(-not $nodeExe){
        Write-Host 'Dashboard 尚未构建，且未找到 Node.js。正式分发包应自带预构建页面。' -ForegroundColor Red
        exit 3
    }
    $viteEntry = Join-Path $DashboardRoot 'node_modules\vite\bin\vite.js'
    if(-not (Test-Path -LiteralPath $viteEntry)){
        Write-Host 'Dashboard 尚未构建，且未找到 Vite 依赖；不会自动联网安装。' -ForegroundColor Red
        exit 4
    }
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

$pythonCandidates = @(
    (Join-Path $ProjectRoot 'runtime\python\python.exe'),
    (Join-Path $ProjectRoot '.venv\Scripts\python.exe'),
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
)
$pythonExe = $pythonCandidates | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if(-not $pythonExe){
    Write-Host '未找到 Python 运行时，无法启动本地靶场控制接口。' -ForegroundColor Red
    exit 7
}

$dockerCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
    'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    (Join-Path $ProjectRoot 'vendor\docker-bin\docker.exe')
)
$dockerExe = $dockerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if($dockerExe){
    $dockerBin = Split-Path -Parent $dockerExe
    if(-not (($env:Path -split ';') -contains $dockerBin)){ $env:Path = "$dockerBin;$env:Path" }
}

$apiHealthUrl = "http://127.0.0.1:$ApiPort/health"
$apiStartedHere = $false
$apiServer = $null
function Test-DashboardApiReady {
    try {
        $health = Invoke-RestMethod -Uri $apiHealthUrl -TimeoutSec 2
        return $health.status -eq 'ok' -and $health.service -eq 'src-auto-dashboard-api'
    } catch {
        return $false
    }
}

if(-not (Test-DashboardApiReady)){
    $apiStdoutLog = Join-Path $logDirectory 'dashboard-api.stdout.log'
    $apiStderrLog = Join-Path $logDirectory 'dashboard-api.stderr.log'
    try {
        $apiArguments = @('-m', 'src_auto.dashboard_server', '--port', "$ApiPort")
        $apiServer = Start-Process -FilePath $pythonExe -ArgumentList $apiArguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $apiStdoutLog -RedirectStandardError $apiStderrLog -WindowStyle Hidden -PassThru
        $apiStartedHere = $true
    } catch {
        Write-Host "本地靶场控制接口启动失败：$($_.Exception.Message)" -ForegroundColor Red
        exit 7
    }
    for($attempt = 0; $attempt -lt 40; $attempt++){
        Start-Sleep -Milliseconds 250
        if(Test-DashboardApiReady){ break }
        if($apiServer.HasExited){ break }
    }
    if(-not (Test-DashboardApiReady)){
        if($apiServer -and -not $apiServer.HasExited){ Stop-Process -Id $apiServer.Id -ErrorAction SilentlyContinue }
        Write-Host "本地靶场控制接口未就绪；请查看 $apiStderrLog" -ForegroundColor Red
        exit 7
    }
}

$baseUrl = "http://127.0.0.1:$Port/"
$url = if($InitialPage -eq 'overview'){ $baseUrl } else { $baseUrl + '?page=' + $InitialPage }
$webArguments = @('-m', 'src_auto.dashboard_web', '--port', "$Port", '--api-port', "$ApiPort")

if($Foreground){
    Write-Host "Dashboard 正在前台运行：$url" -ForegroundColor Green
    Write-Host '仅监听 127.0.0.1；按 Ctrl+C 停止。' -ForegroundColor Yellow
    try {
        & $pythonExe @webArguments
        $webExitCode = $LASTEXITCODE
    } finally {
        if($apiStartedHere -and $apiServer -and -not $apiServer.HasExited){ Stop-Process -Id $apiServer.Id -ErrorAction SilentlyContinue }
    }
    exit $webExitCode
}

$stdoutLog = Join-Path $logDirectory 'dashboard-web.stdout.log'
$stderrLog = Join-Path $logDirectory 'dashboard-web.stderr.log'

try {
    $server = Start-Process -FilePath $pythonExe -ArgumentList $webArguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru
} catch {
    if($apiStartedHere -and $apiServer -and -not $apiServer.HasExited){ Stop-Process -Id $apiServer.Id -ErrorAction SilentlyContinue }
    Write-Host "Dashboard 进程启动失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 8
}

$ready = $false
for($attempt = 0; $attempt -lt 30; $attempt++){
    Start-Sleep -Milliseconds 250
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $baseUrl -TimeoutSec 2
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
    if($apiStartedHere -and $apiServer -and -not $apiServer.HasExited){ Stop-Process -Id $apiServer.Id -ErrorAction SilentlyContinue }
    Write-Host "Dashboard 未在规定时间内就绪；请查看 $stderrLog" -ForegroundColor Red
    exit 9
}

Write-Host "Dashboard 已启动：$url" -ForegroundColor Green
Write-Host "进程 ID：$($server.Id)；日志：$logDirectory" -ForegroundColor DarkGray
Write-Host "本地控制接口：http://127.0.0.1:$ApiPort（仅回环；靶场必须由页面人工点击启动）" -ForegroundColor DarkGray
Write-Host '网络接触：仅本机回环；不会自动启动靶场、不会访问真实目标、不会调用远程 AI。' -ForegroundColor Yellow

if(-not $NoBrowser){
    Start-Process -FilePath $url | Out-Null
}
exit 0

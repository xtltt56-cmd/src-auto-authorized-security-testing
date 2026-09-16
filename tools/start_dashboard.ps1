[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 4173,
    [ValidateRange(1024, 65535)]
    [int]$ApiPort = 4174,
    [ValidateSet('overview','labs','targets','review','findings','settings')]
    [string]$InitialPage = 'overview',
    [ValidateSet('ask','enabled','disabled')]
    [string]$RemoteAIConsent = 'ask',
    [switch]$NoBrowser,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

if($RemoteAIConsent -eq 'ask'){
    $answer = (Read-Host '是否允许本次 Dashboard 使用云端 AI？输入 Y/是允许，N/否/回车禁止；连接测试仍需页面再次确认').Trim().ToLowerInvariant()
    $RemoteAIConsent = if($answer -in @('y','yes','是','允许','启用')){ 'enabled' } else { 'disabled' }
}
$remoteAIEnabled = $RemoteAIConsent -eq 'enabled'
$env:SRC_AUTO_REMOTE_AI_CONSENT = if($remoteAIEnabled){ 'enabled' } else { 'disabled' }
$env:SRC_AUTO_DEEPSEEK_CONSENT = if($remoteAIEnabled){ 'enabled' } else { 'disabled' }
$env:SRC_AUTO_ZHIPU_CONSENT = if($remoteAIEnabled){ 'enabled' } else { 'disabled' }
$env:SRC_AUTO_OPENROUTER_CONSENT = if($remoteAIEnabled){ 'enabled' } else { 'disabled' }
$env:SRC_AUTO_OPENAI_CONSENT = 'disabled'
if($remoteAIEnabled){
    Write-Host '本次 Dashboard 已允许云端 AI；只有在系统设置中再次勾选联网测试才会发送请求。' -ForegroundColor Yellow
} else {
    Write-Host '本次 Dashboard 已禁用云端 AI；连接测试接口将被服务端硬拒绝。' -ForegroundColor Green
}

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
function Get-DashboardApiHealth {
    try {
        $health = Invoke-RestMethod -Uri $apiHealthUrl -TimeoutSec 2
        if($health.status -eq 'ok' -and $health.service -eq 'src-auto-dashboard-api'){ return $health }
        return $null
    } catch {
        return $null
    }
}

function Test-DashboardApiReady {
    return $null -ne (Get-DashboardApiHealth)
}

function Test-DashboardHasActiveWork {
    $origin = "http://127.0.0.1:$Port"
    $session = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/session" -Headers @{ Origin = $origin } -TimeoutSec 2
    if([string]::IsNullOrWhiteSpace([string]$session.token)){ throw '旧 Dashboard API 没有返回会话令牌。' }
    $snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/dashboard" -Headers @{ Origin = $origin; 'X-SRC-Auto-Token' = [string]$session.token } -TimeoutSec 3
    return @($snapshot.tasks | Where-Object { $_.state -in @('queued','running','paused','cancelling') }).Count -gt 0
}

function Get-VerifiedDashboardApiProcessId([object]$Health){
    $candidateId = 0
    if($Health -and $Health.PSObject.Properties['processId']){
        $candidateId = [int]$Health.processId
    } else {
        $listener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $ApiPort -ErrorAction SilentlyContinue | Select-Object -First 1
        if($listener){ $candidateId = [int]$listener.OwningProcess }
    }
    if($candidateId -le 0){ return $null }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $candidateId" -ErrorAction SilentlyContinue
    if(-not $processInfo){ return $null }
    $commandLine = [string]$processInfo.CommandLine
    $portPattern = [regex]::Escape([string]$ApiPort)
    if($commandLine -notmatch '(?i)(?:^|\s)-m\s+src_auto\.dashboard_server(?:\s|$)' -or $commandLine -notmatch "(?i)(?:^|\s)--port\s+$portPattern(?:\s|$)"){
        return $null
    }
    return $candidateId
}

$existingApiHealth = Get-DashboardApiHealth
if($existingApiHealth){
    $consentProperty = $existingApiHealth.PSObject.Properties['remoteAiSessionEnabled']
    $consentMatches = $consentProperty -and ([bool]$consentProperty.Value -eq $remoteAIEnabled)
    if(-not $consentMatches){
        try {
            if(Test-DashboardHasActiveWork){
                Write-Host '已有 Dashboard 正在执行任务，且其云端 AI 授权与本次选择不一致。为保护任务和授权状态，本次启动已停止。请先在原 Dashboard 中停止任务后重试。' -ForegroundColor Red
                exit 10
            }
        } catch {
            Write-Host "无法确认旧 Dashboard 是否正在执行任务，已拒绝复用或终止：$($_.Exception.Message)" -ForegroundColor Red
            exit 10
        }
        $existingApiProcessId = Get-VerifiedDashboardApiProcessId $existingApiHealth
        if(-not $existingApiProcessId){
            Write-Host '已有 Dashboard API 的授权状态与本次选择不一致，但无法安全确认其进程身份。请关闭旧 Dashboard 服务后重试。' -ForegroundColor Red
            exit 10
        }
        Write-Host '检测到旧 Dashboard API 的云端 AI 授权与本次选择不一致，正在安全重启本地控制接口……' -ForegroundColor Cyan
        Stop-Process -Id $existingApiProcessId -ErrorAction Stop
        for($attempt = 0; $attempt -lt 20; $attempt++){
            Start-Sleep -Milliseconds 100
            if(-not (Test-DashboardApiReady)){ break }
        }
        if(Test-DashboardApiReady){
            Write-Host '旧 Dashboard API 未能安全停止，本次启动已取消。' -ForegroundColor Red
            exit 10
        }
        $existingApiHealth = $null
    } else {
        Write-Host '现有 Dashboard API 的云端 AI 授权与本次选择一致，安全复用该本机服务。' -ForegroundColor DarkGray
    }
}

if(-not $existingApiHealth){
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

function Test-DashboardWebReady {
    try {
        $session = Invoke-RestMethod -Uri ($baseUrl + 'api/session') -TimeoutSec 2
        return -not [string]::IsNullOrWhiteSpace([string]$session.token)
    } catch {
        return $false
    }
}

if($Foreground){
    if(Test-DashboardWebReady){
        Write-Host "Dashboard 已在运行并将继续复用：$url" -ForegroundColor Green
        if(-not $NoBrowser){ Start-Process -FilePath $url | Out-Null }
        exit 0
    }
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

$webReused = Test-DashboardWebReady
$server = $null
if(-not $webReused){
    try {
        $server = Start-Process -FilePath $pythonExe -ArgumentList $webArguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru
    } catch {
        if($apiStartedHere -and $apiServer -and -not $apiServer.HasExited){ Stop-Process -Id $apiServer.Id -ErrorAction SilentlyContinue }
        Write-Host "Dashboard 进程启动失败：$($_.Exception.Message)" -ForegroundColor Red
        exit 8
    }
}

$ready = $webReused
for($attempt = 0; $attempt -lt 30; $attempt++){
    if($ready){ break }
    Start-Sleep -Milliseconds 250
    if(Test-DashboardWebReady){ $ready = $true; break }
    if($server -and $server.HasExited){ break }
}

if(-not $ready){
    if($server -and -not $server.HasExited){ Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
    if($apiStartedHere -and $apiServer -and -not $apiServer.HasExited){ Stop-Process -Id $apiServer.Id -ErrorAction SilentlyContinue }
    Write-Host "Dashboard 未在规定时间内就绪；请查看 $stderrLog" -ForegroundColor Red
    exit 9
}

Write-Host "Dashboard 已启动：$url" -ForegroundColor Green
if($webReused){ Write-Host "已复用现有 Dashboard 网页服务；日志：$logDirectory" -ForegroundColor DarkGray }
else { Write-Host "进程 ID：$($server.Id)；日志：$logDirectory" -ForegroundColor DarkGray }
Write-Host "本地控制接口：http://127.0.0.1:$ApiPort（仅回环；靶场必须由页面人工点击启动）" -ForegroundColor DarkGray
if($remoteAIEnabled){
    Write-Host '网络接触：靶场仅本机回环；不会自动访问真实目标或调用远程 AI。只有人工在系统设置中再次确认后才会执行连接测试。' -ForegroundColor Yellow
} else {
    Write-Host '网络接触：仅本机回环；不会自动启动靶场、不会访问真实目标；本次会话不会调用远程 AI。' -ForegroundColor Yellow
}

if(-not $NoBrowser){
    Start-Process -FilePath $url | Out-Null
}
exit 0

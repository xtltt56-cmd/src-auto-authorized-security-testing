param(
    [switch]$RunLocalLab,
    [switch]$Dashboard
)

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONIOENCODING = 'utf-8'
if($Dashboard){
    $dashboardLauncher = Join-Path $ScriptRoot 'tools\start_dashboard.ps1'
    if(-not (Test-Path -LiteralPath $dashboardLauncher)){
        Write-Host '未找到 Dashboard 启动脚本，无法启动可视化控制台。' -ForegroundColor Red
        exit 2
    }
    & $dashboardLauncher
    exit $LASTEXITCODE
}
if(-not $RunLocalLab){
    $guiPath = Join-Path $ScriptRoot 'tools\src_auto_gui.ps1'
    if(-not (Test-Path -LiteralPath $guiPath)){
        Write-Host '未找到图形主菜单脚本，无法启动 SRC-Auto。' -ForegroundColor Red
        exit 2
    }
    & $guiPath
    exit $LASTEXITCODE
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeepSeekSecretHelper = Join-Path $ProjectRoot 'tools\deepseek_secret.ps1'
$DeepSeekSecretPath = Join-Path $ProjectRoot 'config\secrets\deepseek_api_key.dpapi'
Set-Location -LiteralPath $ProjectRoot

Write-Host 'SRC-Auto 一键启动系统' -ForegroundColor Cyan
Write-Host "项目目录：$ProjectRoot"
Write-Host '运行模式：仅本机回环靶场，不接触真实目标。' -ForegroundColor Yellow

function Read-DeepSeekSessionKey {
    try {
        $secureKey = Read-Host '请输入新的 DeepSeek API Key（输入不回显，仅当前启动会话，不会写入文件）' -AsSecureString
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

$deepSeekAnswer = (Read-Host '是否启用 DeepSeek v4 Flash 远程 AI？输入 Y/是 启用，N/否/回车 禁用').Trim().ToLowerInvariant()
$deepSeekEnabled = $false
if($deepSeekAnswer -in @('y', 'yes', '是', '启用')){
    if([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)){
        if(Test-Path -LiteralPath $DeepSeekSecretPath){
            try {
                . $DeepSeekSecretHelper
                $deepSeekKey = Unprotect-DeepSeekKey -Path $DeepSeekSecretPath -ProjectRoot $ProjectRoot
                if(-not [string]::IsNullOrWhiteSpace($deepSeekKey)){
                    $env:DEEPSEEK_API_KEY = $deepSeekKey
                    $deepSeekKey = $null
                    $deepSeekEnabled = $true
                    Write-Host '已从当前 Windows 用户的 DPAPI 加密文件加载密钥。' -ForegroundColor Green
                }
            } catch {
                $deepSeekKey = $null
                Write-Host '加密密钥解密失败；不会发起远程请求。请重新输入或运行保存工具。' -ForegroundColor Yellow
            }
        }
        if(-not $deepSeekEnabled){
            Write-Host '需要新的 DEEPSEEK_API_KEY。请在下一行粘贴；留空则本次保持禁用，不会发起远程请求。' -ForegroundColor Yellow
            $deepSeekKey = Read-DeepSeekSessionKey
            if(-not [string]::IsNullOrWhiteSpace($deepSeekKey)){
                $env:DEEPSEEK_API_KEY = $deepSeekKey
                $deepSeekKey = $null
                $deepSeekEnabled = $true
                Write-Host '密钥已加载到本次启动会话，未写入文件。' -ForegroundColor Green
            } else {
                Write-Host '未输入有效密钥，本次保持禁用，不会发起远程请求。' -ForegroundColor Yellow
            }
        }
    } else {
        $deepSeekEnabled = $true
    }
}
if($deepSeekEnabled){
    $env:SRC_AUTO_REMOTE_AI_CONSENT = 'enabled'
    $env:SRC_AUTO_DEEPSEEK_CONSENT = 'enabled'
    $env:SRC_AUTO_OPENAI_CONSENT = 'disabled'
    Write-Host 'DeepSeek v4 Flash 已获本次启动会话授权；仍只允许人工 remote-triage，不会自动调用。' -ForegroundColor Yellow
} else {
    $env:SRC_AUTO_REMOTE_AI_CONSENT = 'disabled'
    $env:SRC_AUTO_DEEPSEEK_CONSENT = 'disabled'
    $env:SRC_AUTO_OPENAI_CONSENT = 'disabled'
    Write-Host 'DeepSeek 已禁用：remote_ai_disabled_for_session；本次启动不会调用任何远程 AI。' -ForegroundColor Green
}

$dockerCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
    'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    (Join-Path $ProjectRoot 'vendor\docker-bin\docker.exe')
)
$dockerExe = $dockerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$dockerRoot = if($dockerExe){ Split-Path -Parent $dockerExe } else { $null }
if($dockerRoot){ $env:Path = "$dockerRoot;$env:Path" }

function Test-DockerReady {
    if(-not $dockerExe){ return $false }
    try {
        & $dockerExe version *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

if(-not (Test-DockerReady)){
    $dockerApp = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'
    if(Test-Path -LiteralPath $dockerApp){
        Write-Host '正在启动 Docker Desktop（本地靶场）……' -ForegroundColor Yellow
        Start-Process -FilePath $dockerApp | Out-Null
    } else {
        Write-Host '未找到 Docker Desktop；将无法启动本地五靶场。' -ForegroundColor Yellow
    }
    $dockerReady = $false
    1..60 | ForEach-Object {
        Start-Sleep -Seconds 1
        if(Test-DockerReady){$dockerReady = $true; break}
    }
    if(-not $dockerReady){
        Write-Host 'Docker Desktop 未在规定时间内就绪，请检查后重试。' -ForegroundColor Red
        Read-Host '按 Enter 键关闭窗口'
        exit 4
    }
}

function Ensure-LocalLabs {
    $composeFile = Join-Path $ProjectRoot 'docker-compose.local-labs.yml'
    if(-not (Test-Path -LiteralPath $composeFile)){ return $false }
    Write-Host '正在启动固定版本的 Juice Shop、DVWA、WebGoat、VAmPI 和业务 API（business-api）（仅回环端口）……' -ForegroundColor Cyan
    & $dockerExe compose -f $composeFile up -d
    if($LASTEXITCODE -ne 0){ return $false }
    $juiceReady = $false
    $dvwaReady = $false
    $webgoatReady = $false
    $vampiReady = $false
    $businessApiReady = $false
    for($i = 0; $i -lt 120; $i++){
        Start-Sleep -Seconds 1
        try {
            $juice = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 2
            if($juice.StatusCode -eq 200){ $juiceReady = $true }
        } catch {}
        try {
            $dvwa = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8081/login.php' -TimeoutSec 2
            if($dvwa.StatusCode -eq 200){ $dvwaReady = $true }
        } catch {}
        try {
            $webgoat = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8082/WebGoat/actuator/health' -TimeoutSec 2
            if($webgoat.StatusCode -eq 200){ $webgoatReady = $true }
        } catch {}
        try {
            $vampi = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8083/ui/' -TimeoutSec 2
            if($vampi.StatusCode -eq 200){ $vampiReady = $true }
        } catch {}
        try {
            $businessApi = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8084/health' -TimeoutSec 2
            if($businessApi.StatusCode -eq 200){ $businessApiReady = $true }
        } catch {}
        if($juiceReady -and $dvwaReady -and $webgoatReady -and $vampiReady -and $businessApiReady){ return $true }
    }
    return $false
}

Write-Host '正在确保五靶场仅绑定到 127.0.0.1:3000、127.0.0.1:8081、127.0.0.1:8082、127.0.0.1:8083 和 127.0.0.1:8084……' -ForegroundColor Cyan
if(-not (Ensure-LocalLabs)){
    Write-Host '本地五靶场未能在回环端口就绪。' -ForegroundColor Red
    Read-Host '按 Enter 键关闭窗口'
    exit 5
}
Write-Host 'Juice Shop、DVWA、WebGoat、VAmPI 和业务 API（business-api）已在回环端口就绪。' -ForegroundColor Green

function Test-OllamaReady {
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
        return $null -ne $response
    } catch {
        return $false
    }
}

$ollamaPath = $null
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if($ollamaCommand){
    $ollamaPath = $ollamaCommand.Source
} else {
    $candidate = 'C:\Users\lenovo\AppData\Local\Programs\Ollama\ollama.exe'
    if(Test-Path -LiteralPath $candidate){
        $ollamaPath = $candidate
    }
}

if(Test-OllamaReady){
    Write-Host 'Ollama 已就绪，将使用 config/models.yaml 中的本地模型。' -ForegroundColor Green
} elseif($ollamaPath){
    Write-Host '正在启动 Ollama（不会创建开机启动任务）……' -ForegroundColor Yellow
    Start-Process -FilePath $ollamaPath -ArgumentList @('serve') -WorkingDirectory $ProjectRoot -WindowStyle Hidden | Out-Null
    $ready = $false
    1..30 | ForEach-Object {
        Start-Sleep -Seconds 1
        if(Test-OllamaReady){$ready = $true; break}
    }
    if($ready){
        Write-Host 'Ollama 已就绪，将使用 config/models.yaml 中的本地模型。' -ForegroundColor Green
    } else {
        Write-Host 'Ollama 未就绪，将使用本地启发式回退。' -ForegroundColor Yellow
    }
} else {
    Write-Host '未找到 Ollama，将使用本地启发式回退。' -ForegroundColor Yellow
}

Write-Host '正在执行五靶场本地验收（发现、受控候选、独立裁决和评分）……' -ForegroundColor Cyan
python tools/run_local_lab_validation.py --local-only --repeat-rounds 2
$validationExit = $LASTEXITCODE
if($validationExit -ne 0){
    Write-Host "五靶场验收结束，退出码：$validationExit；请查看 validation\autotest\LOCAL_LAB_SCORE.json。" -ForegroundColor Yellow
} else {
    Write-Host '五靶场本地验收完成，结果已写入 validation\autotest\LOCAL_LAB_SCORE.json。' -ForegroundColor Green
}

Write-Host '正在执行五靶场非破坏性安全回归（不发送漏洞利用 payload）……' -ForegroundColor Cyan
python tools/run_local_regression.py --local-only --repeat-rounds 2 --json
$regressionExit = $LASTEXITCODE
if($regressionExit -ne 0){
    Write-Host "安全回归结束，退出码：$regressionExit；请查看 validation\autotest\local_regression\LOCAL_REGRESSION_SCORE.json。" -ForegroundColor Yellow
} else {
    Write-Host '五靶场安全回归全部通过。' -ForegroundColor Green
}

Write-Host '正在创建本地运行记录……' -ForegroundColor Cyan
$newRun = python -m src_auto new --target-id local-lab --scope config\targets\local-lab\scope_confirmed.yaml --mode local --json | ConvertFrom-Json
if(-not $newRun.run_id){
    Write-Host '创建运行记录失败。' -ForegroundColor Red
    Read-Host '按 Enter 键退出'
    exit 2
}
$runId = $newRun.run_id
Write-Host "RUN_ID=$runId" -ForegroundColor Green

Write-Host '正在执行本地控制层流程……' -ForegroundColor Cyan
python -m src_auto run --run-id $runId --scope config\targets\local-lab\scope_confirmed.yaml --local-lab --human
$runExit = $LASTEXITCODE

Write-Host '正在显示 Findings……' -ForegroundColor Cyan
python -m src_auto findings --run-id $runId --human
Write-Host '正在显示报告索引……' -ForegroundColor Cyan
python -m src_auto reports --human

if($runExit -eq 0 -and $validationExit -eq 0 -and $regressionExit -eq 0){
    Write-Host "本地运行已完成：$runId" -ForegroundColor Green
} else {
    Write-Host "本地运行结束，控制层退出码：$runExit，五靶场验收退出码：$validationExit，安全回归退出码：$regressionExit；请检查状态和报告。" -ForegroundColor Yellow
}
Read-Host '按 Enter 键关闭窗口'
if($validationExit -ne 0){ exit $validationExit }
if($regressionExit -ne 0){ exit $regressionExit }
exit $runExit

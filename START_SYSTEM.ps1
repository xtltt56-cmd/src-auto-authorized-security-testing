$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

Write-Host 'SRC-Auto one-click launcher' -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host 'Mode: local loopback lab only; no real target contact.' -ForegroundColor Yellow

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
    Write-Host 'Ollama service is already ready.' -ForegroundColor Green
} elseif($ollamaPath){
    Write-Host 'Starting Ollama manually (no startup task is created)...' -ForegroundColor Yellow
    Start-Process -FilePath $ollamaPath -ArgumentList @('serve') -WorkingDirectory $ProjectRoot -WindowStyle Hidden | Out-Null
    $ready = $false
    1..30 | ForEach-Object {
        Start-Sleep -Seconds 1
        if(Test-OllamaReady){$ready = $true; break}
    }
    if($ready){
        Write-Host 'Ollama is ready; model selection comes from config/models.yaml.' -ForegroundColor Green
    } else {
        Write-Host 'Ollama did not become ready; heuristic triage fallback will be used.' -ForegroundColor Yellow
    }
} else {
    Write-Host 'Ollama was not found; heuristic triage fallback will be used.' -ForegroundColor Yellow
}

Write-Host 'Creating a local run record...' -ForegroundColor Cyan
$newRun = python -m src_auto new --target-id local-lab --scope config\targets\local-lab\scope_confirmed.yaml --mode local | ConvertFrom-Json
if(-not $newRun.run_id){
    Write-Host 'Failed to create the run record.' -ForegroundColor Red
    Read-Host 'Press Enter to exit'
    exit 2
}
$runId = $newRun.run_id
Write-Host "RUN_ID=$runId" -ForegroundColor Green

Write-Host 'Running the local E2E pipeline...' -ForegroundColor Cyan
python -m src_auto run --run-id $runId --scope config\targets\local-lab\scope_confirmed.yaml --local-lab
$runExit = $LASTEXITCODE

Write-Host 'Showing Findings...' -ForegroundColor Cyan
python -m src_auto findings --run-id $runId
Write-Host 'Showing report index...' -ForegroundColor Cyan
python -m src_auto reports

if($runExit -eq 0){
    Write-Host "Local run completed: $runId" -ForegroundColor Green
} else {
    Write-Host "Local run ended with exit code $runExit; inspect status and reports." -ForegroundColor Yellow
}
Read-Host 'Press Enter to close this window'
exit $runExit

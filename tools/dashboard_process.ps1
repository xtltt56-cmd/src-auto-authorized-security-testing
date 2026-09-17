# Shared identity checks for manual Dashboard start/stop.
function Get-DashboardProjectId {
    $root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\').ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-VerifiedDashboardProcessId([int]$Port, [string]$ModuleName, [object]$Health) {
    if(-not $Health -or $Health.projectId -ne (Get-DashboardProjectId)) { throw 'Dashboard project identity mismatch; no process was stopped.' }
    $listener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    $candidateId = [int]$listener.OwningProcess
    if($candidateId -le 0 -or $candidateId -ne [int]$Health.processId) { throw 'Dashboard listening PID mismatch.' }
    $info = Get-CimInstance Win32_Process -Filter "ProcessId = $candidateId" -ErrorAction Stop
    $modulePattern = [regex]::Escape($ModuleName)
    $portPattern = [regex]::Escape([string]$Port)
    if(-not $info -or $info.CommandLine -notmatch "(?i)(?:^|\s)-m\s+$modulePattern(?:\s|$)" -or $info.CommandLine -notmatch "(?i)(?:^|\s)--port\s+$portPattern(?:\s|$)") { throw 'Dashboard command line mismatch.' }
    return $candidateId
}

function Stop-IdleDashboardApi([int]$Port, [object]$Health) {
    $verifiedId = Get-VerifiedDashboardProcessId -Port $Port -ModuleName 'src_auto.dashboard_server' -Health $Health
    $headers = @{ Origin = [string]$Health.allowedOrigin }
    $session = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/session" -Headers $headers -TimeoutSec 3
    if([string]::IsNullOrWhiteSpace([string]$session.token)) { throw 'Dashboard session unavailable.' }
    $headers['X-SRC-Auto-Token'] = [string]$session.token
    # API checks idle and freezes submissions atomically.
    $reply = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/shutdown" -Method Post -ContentType 'application/json' -Body '{}' -Headers $headers -TimeoutSec 5
    if(-not $reply.accepted) { throw 'Dashboard refused shutdown.' }
    for($attempt=0; $attempt -lt 50; $attempt++) {
        if(-not (Get-Process -Id $verifiedId -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 100
    }
    throw 'Dashboard shutdown timed out; no force-kill was performed.'
}

[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)] [int]$WebPort = 4173,
    [ValidateRange(1024, 65535)] [int]$ApiPort = 4174
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
. (Join-Path $PSScriptRoot 'dashboard_process.ps1')

try {
    $apiHealth = $null
    $webHealth = $null
    $apiListener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $ApiPort -ErrorAction SilentlyContinue
    $webListener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $WebPort -ErrorAction SilentlyContinue
    if($apiListener) {
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
        if($apiHealth.service -ne 'src-auto-dashboard-api') { throw 'API service mismatch.' }
        $null = Get-VerifiedDashboardProcessId -Port $ApiPort -ModuleName 'src_auto.dashboard_server' -Health $apiHealth
    }
    $webId = $null
    if($webListener) {
        $webHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/health" -TimeoutSec 3
        if($webHealth.service -ne 'src-auto-dashboard-web' -or [int]$webHealth.apiPort -ne $ApiPort) { throw 'Web service or API port mismatch.' }
        $webId = Get-VerifiedDashboardProcessId -Port $WebPort -ModuleName 'src_auto.dashboard_web' -Health $webHealth
    }
    if($apiHealth) { Stop-IdleDashboardApi -Port $ApiPort -Health $apiHealth }
    if($webId) {
        $webId = Get-VerifiedDashboardProcessId -Port $WebPort -ModuleName 'src_auto.dashboard_web' -Health $webHealth
        Stop-Process -Id $webId -ErrorAction Stop
        Wait-Process -Id $webId -Timeout 5 -ErrorAction SilentlyContinue
    }
    Write-Host 'SRC-Auto Dashboard services are stopped. Lab containers and saved reports are retained.' -ForegroundColor Green
    exit 0
} catch {
    Write-Host "Dashboard shutdown refused: $($_.Exception.Message). Stop active tasks first; verify the project and ports." -ForegroundColor Red
    exit 3
}

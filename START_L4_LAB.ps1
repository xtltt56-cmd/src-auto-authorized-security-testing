$ErrorActionPreference = 'Stop'
$srcPython = Join-Path $PSScriptRoot 'runtime\python\python.exe'
if(-not (Test-Path -LiteralPath $srcPython)){
    $srcPython = (Get-Command python.exe -ErrorAction Stop).Source
}
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Push-Location -LiteralPath $PSScriptRoot
try {
    & $srcPython -X utf8 -u (Join-Path $PSScriptRoot 'tools\run_l4_lab.py')
    $srcLabExit = $LASTEXITCODE
} finally { Pop-Location }
exit $srcLabExit

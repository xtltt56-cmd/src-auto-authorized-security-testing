param(
    [switch]$SkipNuclei,
    [switch]$SkipPythonTools,
    [switch]$SkipTestssl
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Fixed project-local layout: vendor\cache\pip, vendor\cache\tmp,
# vendor\pytools\bbot, vendor\pytools\schemathesis and vendor\testssl.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VendorRoot = Join-Path $ProjectRoot 'vendor'
$CacheRoot = Join-Path $VendorRoot 'cache'
$PipCache = Join-Path $CacheRoot 'pip'
$TempRoot = Join-Path $CacheRoot 'tmp'
$BinRoot = Join-Path $VendorRoot 'bin'
$DownloadsRoot = Join-Path $VendorRoot 'downloads'
$PytoolsRoot = Join-Path $VendorRoot 'pytools'

function Assert-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $project = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $full = [IO.Path]::GetFullPath($Path)
    if(-not $full.StartsWith($project + '\', [StringComparison]::OrdinalIgnoreCase)){
        throw 'installer_path_outside_project'
    }
    return $full
}

foreach($directory in @($CacheRoot, $PipCache, $TempRoot, $BinRoot, $DownloadsRoot, $PytoolsRoot)){
    [IO.Directory]::CreateDirectory((Assert-ProjectPath -Path $directory)) | Out-Null
}
$env:PIP_CACHE_DIR = $PipCache
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:PYTHONUTF8 = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

$result = [ordered]@{
    schema_version = 1
    project_root = $ProjectRoot
    created_at = [DateTime]::UtcNow.ToString('o')
    tools = [ordered]@{}
}

if(-not $SkipNuclei){
    $nucleiVersion = '3.11.1'
    $nucleiArchiveSha256 = 'bb6cb9ff8939b753f6fcab06fd30a15f5bc61d8382a597871334c007a85ff9d2'
    $nucleiArchive = Assert-ProjectPath -Path (Join-Path $DownloadsRoot 'nuclei.zip')
    $nucleiUrl = 'https://github.com/projectdiscovery/nuclei/releases/download/v3.11.1/nuclei_3.11.1_windows_amd64.zip'
    if(-not (Test-Path -LiteralPath $nucleiArchive -PathType Leaf)){
        Invoke-WebRequest -UseBasicParsing -Uri $nucleiUrl -OutFile $nucleiArchive
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $nucleiArchive).Hash.ToLowerInvariant()
    if($actualHash -ne $nucleiArchiveSha256){
        throw 'nuclei_checksum_mismatch'
    }
    $staging = Assert-ProjectPath -Path (Join-Path $TempRoot ('nuclei-' + [guid]::NewGuid().ToString('N')))
    [IO.Directory]::CreateDirectory($staging) | Out-Null
    try {
        Expand-Archive -LiteralPath $nucleiArchive -DestinationPath $staging -Force
        $sourceExe = Join-Path $staging 'nuclei.exe'
        $targetExe = Assert-ProjectPath -Path (Join-Path $BinRoot 'nuclei.exe')
        Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force
        $versionOutput = @(& $targetExe -version 2>&1) -join "`n"
        $result.tools.nuclei = [ordered]@{ status = 'installed'; version = $nucleiVersion; sha256 = $actualHash; output = $versionOutput.Trim() }
    } catch {
        $result.tools.nuclei = [ordered]@{ status = 'blocked'; version = $nucleiVersion; sha256 = $actualHash; reason = $_.Exception.Message }
    } finally {
        if((Test-Path -LiteralPath $staging) -and $staging.StartsWith($TempRoot + '\', [StringComparison]::OrdinalIgnoreCase)){
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
    }
}

if(-not $SkipPythonTools){
    $pythonLauncher = (Get-Command py -ErrorAction Stop).Source
    $pythonVersion = @(& $pythonLauncher -3.12 --version 2>&1) -join ' '
    if($LASTEXITCODE -ne 0){ throw 'python_312_required_for_curated_tools' }
    $packageSources = [ordered]@{
        bbot = 'https://github.com/blacklanternsecurity/bbot'
        schemathesis = 'https://github.com/schemathesis/schemathesis'
    }
    $packages = [ordered]@{
        bbot = 'bbot==3.0.1'
        schemathesis = 'schemathesis==4.25.0'
    }
    foreach($name in $packages.Keys){
        $venv = Assert-ProjectPath -Path (Join-Path $PytoolsRoot $name)
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        try {
            if(-not (Test-Path -LiteralPath $venvPython -PathType Leaf)){
                & $pythonLauncher -3.12 -m venv $venv
                if($LASTEXITCODE -ne 0){ throw ('venv_creation_failed: ' + $name) }
            }
            if($name -eq 'bbot'){
                & $venvPython -m pip install --disable-pip-version-check --only-binary=:all: $packages[$name]
                if($LASTEXITCODE -ne 0){ throw 'windows_binary_dependency_unavailable' }
            } else {
                & $venvPython -m pip install --disable-pip-version-check $packages[$name]
                if($LASTEXITCODE -ne 0){ throw ('package_install_failed: ' + $name) }
            }
            $freezePath = Assert-ProjectPath -Path (Join-Path $venv 'installed-packages.txt')
            @(& $venvPython -m pip freeze) | Set-Content -LiteralPath $freezePath -Encoding UTF8
            $command = Join-Path $venv ('Scripts\' + $name + '.exe')
            $versionOutput = if(Test-Path -LiteralPath $command){ @(& $command --version 2>&1) -join "`n" } else { '' }
            $result.tools[$name] = [ordered]@{ status = $(if(Test-Path -LiteralPath $command){'installed'}else{'error'}); package = $packages[$name]; source = $packageSources[$name]; python = $pythonVersion.Trim(); output = $versionOutput.Trim() }
        } catch {
            $result.tools[$name] = [ordered]@{ status = 'blocked'; package = $packages[$name]; source = $packageSources[$name]; python = $pythonVersion.Trim(); reason = $_.Exception.Message }
        }
    }
}

if(-not $SkipTestssl){
    $testsslRoot = Assert-ProjectPath -Path (Join-Path $VendorRoot 'testssl')
    if(-not (Test-Path -LiteralPath (Join-Path $testsslRoot '.git') -PathType Container)){
        & git clone --depth 1 --branch v3.2.4 https://github.com/testssl/testssl.sh $testsslRoot
        if($LASTEXITCODE -ne 0){ throw 'testssl_clone_failed' }
    }
    $revision = @(& git -C $testsslRoot rev-parse HEAD 2>&1) -join ''
    $result.tools.testssl = [ordered]@{ status = 'installed'; version = 'v3.2.4'; revision = $revision.Trim() }
}

$validationRoot = Assert-ProjectPath -Path (Join-Path $ProjectRoot 'validation\tools')
[IO.Directory]::CreateDirectory($validationRoot) | Out-Null
$resultPath = Assert-ProjectPath -Path (Join-Path $validationRoot 'CURATED_TOOL_INSTALL.json')
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($resultPath, (($result | ConvertTo-Json -Depth 8) + "`n"), $utf8)
Write-Output ($result | ConvertTo-Json -Depth 8)

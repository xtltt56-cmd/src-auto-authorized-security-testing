function Get-TargetValue {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [object]$Default = $null
    )
    if($null -eq $Object){ return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if($null -eq $property){ return $Default }
    return $property.Value
}

function Assert-TargetProjectPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    if(-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)){
        throw 'target_config_path_outside_project'
    }
    return $full
}

function ConvertTo-SafeTargetId {
    param([Parameter(Mandatory = $true)][string]$TargetId)
    $value = $TargetId.Trim().ToLowerInvariant()
    if($value -notmatch '^[a-z0-9][a-z0-9_-]{1,39}$'){
        throw 'target_id_invalid'
    }
    return $value
}

function ConvertTo-StringArray {
    param([object]$Value)
    if($null -eq $Value){ return @() }
    return @($Value | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function ConvertTo-PortArray {
    param([object]$Value)
    $ports = @()
    foreach($item in @($Value)){
        try { $port = [int]$item } catch { throw 'allowed_port_invalid' }
        if($port -lt 1 -or $port -gt 65535){ throw 'allowed_port_invalid' }
        $ports += $port
    }
    return @($ports | Sort-Object -Unique)
}

function Test-PlainHost {
    param([string]$HostName)
    if([string]::IsNullOrWhiteSpace($HostName)){ return $false }
    if($HostName -match '[\s\*/?:#@]' -or $HostName -match '^[a-z][a-z0-9+.-]*://'){
        return $false
    }
    try {
        $idn = [System.Uri]::CheckHostName($HostName)
        return $idn -in @([System.UriHostNameType]::Dns, [System.UriHostNameType]::IPv4, [System.UriHostNameType]::IPv6)
    } catch { return $false }
}

function Test-TargetDraft {
    param([Parameter(Mandatory = $true)][object]$Draft)
    $errors = @()
    $targetId = [string](Get-TargetValue -Object $Draft -Name 'target_id' -Default '')
    try { [void](ConvertTo-SafeTargetId -TargetId $targetId) } catch { $errors += $_.Exception.Message }

    $allowedHosts = ConvertTo-StringArray (Get-TargetValue -Object $Draft -Name 'allowed_hosts')
    if($allowedHosts.Count -eq 0){ $errors += 'allowed_hosts_required' }
    foreach($hostName in $allowedHosts){
        if(-not (Test-PlainHost -HostName $hostName)){ $errors += 'allowed_host_invalid'; break }
    }
    $excludedHosts = ConvertTo-StringArray (Get-TargetValue -Object $Draft -Name 'excluded_hosts')
    foreach($hostName in $excludedHosts){
        if(-not (Test-PlainHost -HostName $hostName)){ $errors += 'excluded_host_invalid'; break }
    }
    $ports = @()
    try { $ports = ConvertTo-PortArray (Get-TargetValue -Object $Draft -Name 'allowed_ports') } catch { $errors += $_.Exception.Message }
    if($ports.Count -eq 0){ $errors += 'allowed_ports_required' }

    $targetUrl = [string](Get-TargetValue -Object $Draft -Name 'target_url' -Default '')
    $uri = $null
    if(-not [System.Uri]::TryCreate($targetUrl, [System.UriKind]::Absolute, [ref]$uri)){
        $errors += 'target_url_invalid'
    } elseif($uri.Scheme.ToLowerInvariant() -ne 'https'){
        $errors += 'target_url_must_use_https'
    } elseif(-not [string]::IsNullOrWhiteSpace($uri.UserInfo) -or -not [string]::IsNullOrWhiteSpace($uri.Query) -or -not [string]::IsNullOrWhiteSpace($uri.Fragment)){
        $errors += 'target_url_must_be_clean'
    } else {
        $hostName = $uri.Host.ToLowerInvariant()
        $allowedLower = @($allowedHosts | ForEach-Object { $_.ToLowerInvariant() })
        $excludedLower = @($excludedHosts | ForEach-Object { $_.ToLowerInvariant() })
        if($hostName -notin $allowedLower){ $errors += 'target_host_not_allowed' }
        if($hostName -in $excludedLower){ $errors += 'target_host_excluded' }
        $effectivePort = if($uri.IsDefaultPort){ 443 } else { $uri.Port }
        if($effectivePort -notin $ports){ $errors += 'target_port_not_allowed' }
    }

    [pscustomobject]@{
        valid = ($errors.Count -eq 0)
        errors = @($errors | Select-Object -Unique)
    }
}

function New-ScopeDocument {
    param([Parameter(Mandatory = $true)][object]$Draft)
    $targetId = ConvertTo-SafeTargetId -TargetId ([string](Get-TargetValue -Object $Draft -Name 'target_id'))
    $confirmed = [bool](Get-TargetValue -Object $Draft -Name 'confirmed' -Default $false)
    $networkAllowed = [bool](Get-TargetValue -Object $Draft -Name 'allow_network_contact' -Default $false)
    [ordered]@{
        target_id = $targetId
        vendor = [string](Get-TargetValue -Object $Draft -Name 'vendor' -Default '')
        authorization_source = [string](Get-TargetValue -Object $Draft -Name 'authorization_source' -Default '')
        root_domains = @(ConvertTo-StringArray (Get-TargetValue -Object $Draft -Name 'root_domains'))
        allowed_hosts = @(ConvertTo-StringArray (Get-TargetValue -Object $Draft -Name 'allowed_hosts'))
        excluded_hosts = @(ConvertTo-StringArray (Get-TargetValue -Object $Draft -Name 'excluded_hosts'))
        allowed_ports = @(ConvertTo-PortArray (Get-TargetValue -Object $Draft -Name 'allowed_ports'))
        test_window = [string](Get-TargetValue -Object $Draft -Name 'test_window' -Default '')
        confirmed = ($confirmed -and $networkAllowed)
        allow_network_contact = ($confirmed -and $networkAllowed)
    }
}

function New-LivePlanDocument {
    param([Parameter(Mandatory = $true)][object]$Draft)
    $targetId = ConvertTo-SafeTargetId -TargetId ([string](Get-TargetValue -Object $Draft -Name 'target_id'))
    [ordered]@{
        name = "$targetId-reviewed-plan"
        operator = [string](Get-TargetValue -Object $Draft -Name 'operator' -Default '')
        authorization_note = [string](Get-TargetValue -Object $Draft -Name 'authorization_source' -Default '')
        manual_execution_confirmed = $false
        target_urls = @([string](Get-TargetValue -Object $Draft -Name 'target_url' -Default ''))
        sequence = @()
        commands = [ordered]@{}
    }
}

function Write-TargetConfig {
    param(
        [Parameter(Mandatory = $true)][object]$Draft,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $check = Test-TargetDraft -Draft $Draft
    if(-not $check.valid){ throw (($check.errors -join ',') + '') }
    $targetId = ConvertTo-SafeTargetId -TargetId ([string](Get-TargetValue -Object $Draft -Name 'target_id'))
    $targetDir = Join-Path (Join-Path $ProjectRoot 'config\targets') $targetId
    $scopePath = Assert-TargetProjectPath -Path (Join-Path $targetDir 'scope_confirmed.yaml') -ProjectRoot $ProjectRoot
    $planPath = Assert-TargetProjectPath -Path (Join-Path $targetDir 'live_plan.yaml') -ProjectRoot $ProjectRoot
    [System.IO.Directory]::CreateDirectory($targetDir) | Out-Null
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($scopePath, ((New-ScopeDocument -Draft $Draft) | ConvertTo-Json -Depth 8), $utf8)
    [System.IO.File]::WriteAllText($planPath, ((New-LivePlanDocument -Draft $Draft) | ConvertTo-Json -Depth 8), $utf8)
    [pscustomobject]@{ target_id = $targetId; scope_path = $scopePath; plan_path = $planPath; network_contact = $false }
}

$script:SrcAutoProviderDefaults = @{
    deepseek = [ordered]@{
        displayName = 'DeepSeek V4.1 Flash'
        model = 'deepseek-flash'
        endpoint = 'https://api.deepseek.com/chat/completions'
        modelsEndpoint = 'https://api.deepseek.com/models'
    }
    zhipu = [ordered]@{
        displayName = '智谱 GLM-5.3-Flash'
        model = 'glm-5.3-flash'
        endpoint = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
        modelsEndpoint = ''
    }
    openrouter = [ordered]@{
        displayName = 'OpenRouter'
        model = 'openrouter/free'
        endpoint = 'https://openrouter.ai/api/v1/chat/completions'
        modelsEndpoint = 'https://openrouter.ai/api/v1/models'
    }
}

function Get-SrcAutoProviderDefault {
    param([Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider)
    return [pscustomobject]$script:SrcAutoProviderDefaults[$Provider]
}

function Get-SrcAutoProviderConfig {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $path = Join-Path $ProjectRoot 'config/models.yaml'
    $config = [System.IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json
    $value = $config.remote_providers.$Provider
    if(-not $value){ throw 'provider_config_missing' }
    return $value
}

function Save-SrcAutoProviderModel {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ModelId,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $model = $ModelId.Trim()
    if($model.Length -lt 2 -or $model.Length -gt 160 -or $model -notmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]+$'){
        throw 'provider_model_invalid'
    }
    $path = Join-Path $ProjectRoot 'config/models.yaml'
    $config = [System.IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if(-not $config.remote_providers.$Provider){ throw 'provider_config_missing' }
    $config.remote_providers.$Provider.model = $model
    $temporary = $path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [System.IO.File]::WriteAllText($temporary, (($config | ConvertTo-Json -Depth 12) + "`n"), (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temporary -Destination $path -Force
    } finally {
        if([System.IO.File]::Exists($temporary)){ Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-SrcAutoProviderModels {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [switch]$AllowNetwork
    )
    if(-not $AllowNetwork){ throw 'network_check_not_enabled' }
    $definition = Get-SrcAutoProviderDefault -Provider $Provider
    $key = Unprotect-SrcAutoProviderKey -Provider $Provider -ProjectRoot $ProjectRoot
    try {
        $document = Invoke-RestMethod -Method Get -Uri $definition.modelsEndpoint -Headers @{Authorization=('Bearer ' + $key)} -TimeoutSec 15 -MaximumRedirection 0
        return @($document.data | ForEach-Object { [string]$_.id } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)
    } finally {
        $key = $null
    }
}

function Test-SrcAutoProviderConnection {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('deepseek','zhipu','openrouter')][string]$Provider,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [switch]$AllowNetwork
    )
    if(-not $AllowNetwork){ throw 'network_check_not_enabled' }
    try {
        $config = Get-SrcAutoProviderConfig -Provider $Provider -ProjectRoot $ProjectRoot
        $definition = Get-SrcAutoProviderDefault -Provider $Provider
        if([string]$config.endpoint -ne $definition.endpoint){ return 'endpoint_not_official' }
        $key = Unprotect-SrcAutoProviderKey -Provider $Provider -ProjectRoot $ProjectRoot
        $payload = [ordered]@{
            model = [string]$config.model
            messages = @(@{role='user';content='Reply with OK only.'})
            max_tokens = $(if($Provider -eq 'zhipu'){2048}else{32})
            stream = $false
        }
        if($Provider -eq 'deepseek'){ $payload.thinking = @{type='disabled'} }
        if($Provider -eq 'zhipu'){ $payload.thinking = @{type='enabled'} }
        $body = $payload | ConvertTo-Json -Depth 6 -Compress
        $result = Invoke-RestMethod -Method Post -Uri $definition.endpoint -Headers @{Authorization=('Bearer ' + $key)} -ContentType 'application/json' -Body $body -TimeoutSec 60 -MaximumRedirection 0
        if($result.error){ return 'provider_error' }
        if(@($result.choices).Count -lt 1){ return 'response_invalid' }
        if([string]::IsNullOrWhiteSpace([string]$result.choices[0].message.content)){ return 'empty_or_truncated_response' }
        return 'reachable_model_available'
    } catch [System.Net.WebException] {
        if($_.Exception.Response){ return 'http_' + [int]$_.Exception.Response.StatusCode }
        return 'network_error'
    } catch {
        return 'request_failed'
    } finally {
        $key = $null
    }
}

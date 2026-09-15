. (Join-Path $PSScriptRoot 'openrouter_secret.ps1')

function ConvertTo-OpenRouterModels {
    param($Document)
    foreach($item in $Document.data){
        if($item.architecture.output_modalities -notcontains 'text' -or $item.supported_parameters -notcontains 'response_format'){ continue }
        try {
            $inputRate = [double]::Parse([string]$item.pricing.prompt, [Globalization.CultureInfo]::InvariantCulture) * 1000000
            $outputRate = [double]::Parse([string]$item.pricing.completion, [Globalization.CultureInfo]::InvariantCulture) * 1000000
            if([double]::IsNaN($inputRate) -or [double]::IsInfinity($inputRate) -or $inputRate -lt 0 -or
               [double]::IsNaN($outputRate) -or [double]::IsInfinity($outputRate) -or $outputRate -lt 0){ continue }
        } catch { continue }
        [pscustomobject]@{id=[string]$item.id; name=[string]$item.name; inputRate=$inputRate; outputRate=$outputRate}
    }
}

function Get-OpenRouterModels {
    $document = Invoke-RestMethod -Uri 'https://openrouter.ai/api/v1/models' -TimeoutSec 20 -MaximumRedirection 0
    ConvertTo-OpenRouterModels $document
}

function Save-OpenRouterModel {
    param([string]$ProjectRoot, [string]$ModelId, [array]$Models)
    $selected = @($Models | Where-Object { $_.id -ceq $ModelId })
    if($selected.Count -ne 1){ throw 'model_not_in_catalog' }
    $path = Join-Path $ProjectRoot 'config/models.yaml'
    $config = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if(-not $config.remote_providers.openrouter){ throw 'openrouter_config_missing' }
    $config.remote_providers.openrouter.model = $ModelId
    $config.remote_providers.openrouter.input_usd_per_million = $selected[0].inputRate
    $config.remote_providers.openrouter.output_usd_per_million = $selected[0].outputRate
    $backup = Join-Path $ProjectRoot 'config/secrets/openrouter_models.previous.json'
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup)) | Out-Null
    $temporary = $path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, ($config | ConvertTo-Json -Depth 30), (New-Object Text.UTF8Encoding($false)))
        [IO.File]::Replace($temporary, $path, $backup)
    } finally { if([IO.File]::Exists($temporary)){ [IO.File]::Delete($temporary) } }
}

function Test-OpenRouterSettings {
    param([string]$ProjectRoot, [string]$ModelId, [switch]$AllowNetwork, [switch]$Generate)
    if(-not $AllowNetwork){ throw 'network_check_not_enabled' }
    $plain = $null
    $headers = $null
    try {
        $plain = Unprotect-OpenRouterKey -Path (Join-Path $ProjectRoot 'config/secrets/openrouter_api_key.dpapi') -ProjectRoot $ProjectRoot
        $headers = @{Authorization=('Bearer ' + $plain)}
        $null = Invoke-RestMethod -Uri 'https://openrouter.ai/api/v1/key' -Headers $headers -TimeoutSec 20 -MaximumRedirection 0
        $models = @(Get-OpenRouterModels)
        if(@($models | Where-Object { $_.id -ceq $ModelId }).Count -ne 1){ return 'model_unavailable' }
        if(-not $Generate){ return 'metadata_ok' }
        $body = @{
            model=$ModelId
            messages=@(@{role='user';content='Connectivity check. Return only JSON: {"ok":true}'})
            provider=@{data_collection='deny';allow_fallbacks=$false}
            reasoning=@{effort='low'}
            response_format=@{type='json_object'}
            max_tokens=256
            stream=$false
        } | ConvertTo-Json -Depth 8 -Compress
        $response = Invoke-RestMethod -Uri 'https://openrouter.ai/api/v1/chat/completions' -Method Post -ContentType 'application/json' -Body $body -Headers $headers -TimeoutSec 40 -MaximumRedirection 0
        if($response.error){ return ('http_' + [int]$response.error.code) }
        if(-not $response.choices -or -not $response.choices[0].message.content){return 'response_invalid'}
        try { $answer = $response.choices[0].message.content | ConvertFrom-Json } catch { return 'response_invalid' }
        if($answer.ok -ne $true){ return 'response_invalid' }
        return 'generation_ok'
    } catch {
        if($_.Exception.Response){ return ('http_' + [int]$_.Exception.Response.StatusCode) }
        if($_.Exception.Message -eq 'openrouter_secret_missing'){ return 'key_missing' }
        return 'local_or_network_error'
    } finally {
        if($headers){ $headers.Clear() }
        $plain = $null
    }
}

function Get-OpenRouterCheckMessage {
    param([string]$Code)
    switch($Code){
        'metadata_ok' { '密钥认证通过，模型在兼容目录中；尚未验证实际生成。' }
        'generation_ok' { '最小生成测试通过，返回了有效 JSON；未发送项目数据。' }
        'model_unavailable' { '密钥认证通过，但模型已下架、更名或不支持所需 JSON 输出。请刷新目录并重新选择模型，无需重输密钥。' }
        'key_missing' { '尚未保存密钥。请先粘贴并加密保存。' }
        'http_401' { '密钥认证失败（401）：请核对或更换 OpenRouter 密钥。' }
        'http_402' { '账户额度不足（402）。更换密钥通常无法解决，请检查额度或模型价格。' }
        'http_403' { '访问被拒绝（403）：请检查账户、模型权限或供应商限制。' }
        'http_404' { '没有可用模型端点（404）：可能已下架、更名，或当前隐私设置下没有供应商。' }
        'http_429' { '触发频率或免费配额限制（429），请稍后重试。' }
        'response_invalid' { '服务已响应，但未得到要求的 JSON。可重试或选择其他兼容模型。' }
        default { '检查未通过：请检查网络、代理或本机密钥解密权限。未展示服务器原文或密钥。' }
    }
}

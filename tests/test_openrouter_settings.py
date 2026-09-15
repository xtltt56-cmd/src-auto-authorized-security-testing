import json
import unittest
from tests.test_openrouter_secret import _run_powershell, _ps_quote, PROJECT_ROOT


class OpenRouterSettingsTests(unittest.TestCase):
    def run_ps(self, command):
        helper = PROJECT_ROOT / 'tools' / 'openrouter_settings.ps1'
        result = _run_powershell("$ErrorActionPreference='Stop'; . " + _ps_quote(helper) + '; ' + command)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_catalog_filters_non_text_and_non_json_and_preserves_id(self):
        result = self.run_ps('''
        $document = '{"data":[
          {"id":"vendor/new:free","name":"New","architecture":{"output_modalities":["text"]},"pricing":{"prompt":"0","completion":"0"},"supported_parameters":["response_format"]},
          {"id":"vendor/audio","architecture":{"output_modalities":["audio"]},"supported_parameters":["response_format"]},
          {"id":"vendor/plain","architecture":{"output_modalities":["text"]},"supported_parameters":[]}
        ]}' | ConvertFrom-Json
        @(ConvertTo-OpenRouterModels $document) | ConvertTo-Json -Compress
        ''')
        self.assertEqual(json.loads(result)['id'], 'vendor/new:free')

    def test_save_preserves_other_provider_and_backup_and_rejects_unknown_model(self):
        result = self.run_ps('''
        $root = Join-Path $PWD ('validation/settings-' + [guid]::NewGuid().ToString('N'))
        $null = New-Item -ItemType Directory -Path (Join-Path $root 'config') -Force
        $path = Join-Path $root 'config/models.yaml'
        $initial = '{"lanes":{"primary":{"model":"local"}},"remote_providers":{"deepseek":{"model":"keep"},"openrouter":{"model":"old","enabled":true,"manual_only":true,"input_usd_per_million":0,"output_usd_per_million":0}}}'
        [IO.File]::WriteAllText($path, $initial)
        try {
          $models = @([pscustomobject]@{id='vendor/new'; inputRate=1.5; outputRate=2.5})
          Save-OpenRouterModel -ProjectRoot $root -ModelId 'vendor/new' -Models $models
          $saved = Get-Content -Raw $path | ConvertFrom-Json
          if($saved.remote_providers.deepseek.model -ne 'keep' -or $saved.lanes.primary.model -ne 'local'){throw 'other_provider_changed'}
          if($saved.remote_providers.openrouter.model -ne 'vendor/new' -or $saved.remote_providers.openrouter.output_usd_per_million -ne 2.5){throw 'model_not_saved'}
          if([IO.File]::ReadAllText((Join-Path $root 'config/secrets/openrouter_models.previous.json')) -ne $initial){throw 'backup_wrong'}
          try { Save-OpenRouterModel -ProjectRoot $root -ModelId 'unknown' -Models $models; throw 'accepted_unknown' }
          catch { if($_.Exception.Message -ne 'model_not_in_catalog'){throw} }
          'ok'
        } finally { [IO.Directory]::Delete($root, $true) }
        ''')
        self.assertEqual(result, 'ok')

    def test_probe_requires_explicit_network_permission(self):
        result = self.run_ps('''
        function Invoke-RestMethod { throw 'unexpected_network' }
        try { Test-OpenRouterSettings -ProjectRoot $PWD -ModelId 'old'; throw 'allowed_without_consent' }
        catch { if($_.Exception.Message -ne 'network_check_not_enabled'){throw}; 'blocked' }
        ''')
        self.assertEqual(result, 'blocked')

    def test_metadata_probe_uses_saved_key_without_chat_and_reports_removed_model(self):
        result = self.run_ps('''
        function Unprotect-OpenRouterKey { return 'dummy-test-key' }
        $script:urls = @()
        function Invoke-RestMethod {
          param($Uri,$Headers,$TimeoutSec,$MaximumRedirection,$Method,$Body,$ContentType)
          $script:urls += $Uri
          if($Uri -eq 'https://openrouter.ai/api/v1/key'){
            if($Headers.Authorization -ne 'Bearer dummy-test-key'){throw 'missing_key'}
            return @{data=@{}}
          }
          if($Uri -eq 'https://openrouter.ai/api/v1/models'){return @{data=@()}}
          throw 'unexpected_endpoint'
        }
        $result = Test-OpenRouterSettings -ProjectRoot $PWD -ModelId 'old' -AllowNetwork
        if($result -ne 'model_unavailable' -or $script:urls.Count -ne 2){throw 'incorrect_probe'}
        'ok'
        ''')
        self.assertEqual(result, 'ok')

    def test_smoke_detects_api_error_even_with_http_success(self):
        result = self.run_ps('''
        function Unprotect-OpenRouterKey { return 'dummy-test-key' }
        function Invoke-RestMethod {
          param($Uri,$Headers,$TimeoutSec,$MaximumRedirection,$Method,$Body,$ContentType)
          if($Uri -like '*/key'){return @{data=@{}}}
          if($Uri -like '*/models'){return @{data=@(@{id='vendor/new';architecture=@{output_modalities=@('text')};supported_parameters=@('response_format');pricing=@{prompt='0';completion='0'}})}}
          if($Uri -like '*/chat/completions'){
            $payload = $Body | ConvertFrom-Json
            if($payload.model -ne 'vendor/new' -or $payload.provider.data_collection -ne 'deny'){throw 'incorrect_payload'}
            return @{error=@{code=429;message='sensitive server message'}}
          }
          throw 'unexpected_endpoint'
        }
        Test-OpenRouterSettings -ProjectRoot $PWD -ModelId 'vendor/new' -AllowNetwork -Generate
        ''')
        self.assertEqual(result, 'http_429')

import json
import unittest
import tempfile
from pathlib import Path
from src_auto.provider_credentials import load_saved_provider_key, OFFICIAL_ENDPOINTS
from src_auto.provider_settings import ProviderSettingsStore

from tests.test_openrouter_secret import PROJECT_ROOT, _ps_quote, _run_powershell


class ProviderSettingsTests(unittest.TestCase):
    def test_inline_settings_never_returns_secret_and_saves_official_provider(self):
        parent = PROJECT_ROOT / 'validation'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(parent)) as temporary:
            root = Path(temporary)
            config = root / 'config'
            config.mkdir()
            (config / 'models.yaml').write_text(json.dumps({'remote_providers': {
                'deepseek': {'display_name': 'DeepSeek V4.1 Flash', 'model': 'deepseek-flash',
                             'endpoint': OFFICIAL_ENDPOINTS['deepseek']},
                'zhipu': {'display_name': 'GLM-5.3-Flash', 'model': 'glm-5.3-flash',
                          'endpoint': OFFICIAL_ENDPOINTS['zhipu']},
                'openrouter': {'display_name': 'OpenRouter', 'model': 'openrouter/free',
                               'endpoint': OFFICIAL_ENDPOINTS['openrouter']},
            }}), encoding='utf-8')
            store = ProviderSettingsStore(root)
            before = store.public_status()
            self.assertFalse(before['providers'][0]['keySaved'])
            self.assertNotIn('apiKey', json.dumps(before))
            saved = store.save('deepseek', 'synthetic-browser-key', 'deepseek-flash')
            self.assertTrue(saved['keySaved'])
            self.assertNotIn('synthetic-browser-key', json.dumps(saved))
            self.assertEqual(load_saved_provider_key(root, 'deepseek', OFFICIAL_ENDPOINTS['deepseek']), 'synthetic-browser-key')

    def test_inline_settings_rejects_arbitrary_provider_model_and_endpoint(self):
        with self.assertRaises(ValueError):
            ProviderSettingsStore(PROJECT_ROOT).save('not-a-provider', 'secret', 'model')
        with self.assertRaises(ValueError):
            ProviderSettingsStore(PROJECT_ROOT).save('deepseek', 'secret', '../bad model')

    def test_saved_powershell_key_can_be_read_by_python_but_not_sent_to_custom_host(self):
        parent = PROJECT_ROOT / 'validation'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(parent)) as temporary:
            root = Path(temporary)
            self.run_ps("$secure=ConvertTo-SecureString 'synthetic-integration-key' -AsPlainText -Force; "
                        "[void](Protect-SrcAutoProviderKey -Provider zhipu -SecureKey $secure -ProjectRoot " + _ps_quote(root) + ")")
            self.assertEqual(load_saved_provider_key(root, 'zhipu', OFFICIAL_ENDPOINTS['zhipu']), 'synthetic-integration-key')
            self.assertEqual(load_saved_provider_key(root, 'zhipu', 'https://example.com/chat'), '')

    def run_ps(self, command):
        secret = PROJECT_ROOT / 'tools' / 'provider_secret.ps1'
        settings = PROJECT_ROOT / 'tools' / 'ai_provider_settings.ps1'
        result = _run_powershell(
            "$ErrorActionPreference='Stop'; . " + _ps_quote(secret) + '; . ' + _ps_quote(settings) + '; ' + command
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_provider_secret_round_trip_and_exact_project_path(self):
        result = self.run_ps(r'''
        $root = Join-Path $PWD ('validation/provider-secret-' + [guid]::NewGuid().ToString('N'))
        try {
          $secure = ConvertTo-SecureString 'unit-test-only-key' -AsPlainText -Force
          $path = Protect-SrcAutoProviderKey -Provider zhipu -SecureKey $secure -ProjectRoot $root
          $plain = Unprotect-SrcAutoProviderKey -Provider zhipu -ProjectRoot $root
          if($plain -ne 'unit-test-only-key'){throw 'round_trip_failed'}
          [pscustomobject]@{path=$path;saved=(Test-SrcAutoProviderKeySaved -Provider zhipu -ProjectRoot $root)} | ConvertTo-Json -Compress
        } finally { if(Test-Path -LiteralPath $root){Remove-Item -LiteralPath $root -Recurse -Force} }
        ''')
        value = json.loads(result)
        self.assertTrue(value['saved'])
        self.assertTrue(value['path'].endswith(r'config\secrets\zhipu_api_key.dpapi'))

    def test_model_save_preserves_other_providers_and_rejects_invalid_id(self):
        result = self.run_ps(r'''
        $root = Join-Path $PWD ('validation/provider-config-' + [guid]::NewGuid().ToString('N'))
        $null = New-Item -ItemType Directory -Path (Join-Path $root 'config') -Force
        $initial = '{"remote_providers":{"deepseek":{"model":"keep"},"zhipu":{"model":"glm-4.7-flash"},"openrouter":{"model":"keep-or"}}}'
        [IO.File]::WriteAllText((Join-Path $root 'config/models.yaml'), $initial)
        try {
          Save-SrcAutoProviderModel -Provider zhipu -ModelId 'glm-5.2' -ProjectRoot $root
          $saved = Get-Content -Raw (Join-Path $root 'config/models.yaml') | ConvertFrom-Json
          if($saved.remote_providers.deepseek.model -ne 'keep' -or $saved.remote_providers.openrouter.model -ne 'keep-or'){throw 'other_provider_changed'}
          try { Save-SrcAutoProviderModel -Provider zhipu -ModelId '../bad model' -ProjectRoot $root; throw 'invalid_model_accepted' }
          catch { if($_.Exception.Message -ne 'provider_model_invalid'){throw} }
          $saved.remote_providers.zhipu.model
        } finally { [IO.Directory]::Delete($root, $true) }
        ''')
        self.assertEqual(result, 'glm-5.2')

    def test_catalog_lookup_requires_explicit_network_permission(self):
        result = self.run_ps(r'''
        try { Get-SrcAutoProviderModels -Provider deepseek -ProjectRoot $PWD; throw 'network_allowed' }
        catch { if($_.Exception.Message -ne 'network_check_not_enabled'){throw}; 'blocked' }
        ''')
        self.assertEqual(result, 'blocked')

    def test_connection_requires_permission_and_returns_safe_missing_key_error(self):
        result = self.run_ps(r'''
        try { Test-SrcAutoProviderConnection -Provider zhipu -ProjectRoot $PWD; throw 'network_allowed' }
        catch { if($_.Exception.Message -ne 'network_check_not_enabled'){throw} }
        function Unprotect-SrcAutoProviderKey { throw 'secret-body-never-display' }
        Test-SrcAutoProviderConnection -Provider zhipu -ProjectRoot $PWD -AllowNetwork
        ''')
        self.assertEqual(result, 'request_failed')

    def test_zhipu_probe_uses_saved_key_and_fixed_minimal_message(self):
        result = self.run_ps(r'''
        $root = Join-Path $PWD ('validation/provider-probe-' + [guid]::NewGuid().ToString('N'))
        $null = New-Item -ItemType Directory -Path (Join-Path $root 'config') -Force
        [IO.File]::WriteAllText((Join-Path $root 'config/models.yaml'), '{"remote_providers":{"zhipu":{"model":"glm-4.7-flash","endpoint":"https://open.bigmodel.cn/api/paas/v4/chat/completions"}}}')
        try {
          $secure = ConvertTo-SecureString 'dummy-zhipu-key' -AsPlainText -Force
          [void](Protect-SrcAutoProviderKey -Provider zhipu -SecureKey $secure -ProjectRoot $root)
          function Invoke-RestMethod {
            param($Method,$Uri,$Headers,$ContentType,$Body,$TimeoutSec,$MaximumRedirection)
            $payload = $Body | ConvertFrom-Json
            if($Headers.Authorization -ne 'Bearer dummy-zhipu-key'){throw 'missing_key'}
            if($payload.model -ne 'glm-4.7-flash' -or $payload.messages[0].content -ne 'Reply with OK only.'){throw 'incorrect_payload'}
            return @{choices=@(@{message=@{content='OK'}})}
          }
          Test-SrcAutoProviderConnection -Provider zhipu -ProjectRoot $root -AllowNetwork
        } finally { if(Test-Path -LiteralPath $root){Remove-Item -LiteralPath $root -Recurse -Force} }
        ''')
        self.assertEqual(result, 'reachable_model_available')


if __name__ == '__main__':
    unittest.main()

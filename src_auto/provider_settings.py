"""Loopback-only provider settings and explicit minimal connection probes."""

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .provider_credentials import (
    OFFICIAL_ENDPOINTS,
    load_saved_provider_key,
    save_provider_key,
    saved_provider_key_exists,
)

OFFICIAL_MODELS = {
    'deepseek': 'deepseek-flash',
    'zhipu': 'glm-5.3-flash',
    'openrouter': 'openrouter/free',
}
_MODEL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]{1,159}$')


class ProviderSettingsStore:
    def __init__(self, project_root: Path, opener=None):
        self.root = Path(project_root).resolve()
        self.path = (self.root / 'config' / 'models.yaml').resolve()
        self.path.relative_to(self.root)
        self.opener = opener or urlopen
        self._write_lock = threading.Lock()

    def _document(self) -> Dict[str, Any]:
        value = json.loads(self.path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict) or not isinstance(value.get('remote_providers'), dict):
            raise ValueError('provider_config_invalid')
        return value

    def _provider(self, provider: str, document=None) -> Mapping[str, Any]:
        if provider not in OFFICIAL_MODELS:
            raise ValueError('provider_not_supported')
        config = (document or self._document())['remote_providers'].get(provider)
        if not isinstance(config, dict):
            raise ValueError('provider_config_missing')
        return config

    def _public_provider(self, provider: str, config: Mapping[str, Any]) -> Dict[str, Any]:
        endpoint = OFFICIAL_ENDPOINTS[provider]
        return {
            'id': provider,
            'displayName': str(config.get('display_name') or provider),
            'model': str(config.get('model') or OFFICIAL_MODELS[provider]),
            'officialModel': OFFICIAL_MODELS[provider],
            'keySaved': saved_provider_key_exists(self.root, provider),
            'endpointHost': str(urlsplit(endpoint).hostname or ''),
            'manualOnly': True,
            'pricingNote': str(config.get('pricing_note') or '费用与额度以服务商账户为准'),
        }

    def public_status(self) -> Dict[str, Any]:
        document = self._document()
        return {'providers': [self._public_provider(name, self._provider(name, document)) for name in OFFICIAL_MODELS]}

    def save(self, provider: str, api_key: str, model: str) -> Dict[str, Any]:
        with self._write_lock:
            document = self._document()
            config = self._provider(provider, document)
            model_id = str(model or OFFICIAL_MODELS[provider]).strip()
            if not _MODEL_ID.fullmatch(model_id):
                raise ValueError('provider_model_invalid')
            api_key = str(api_key or '').strip()
            if api_key:
                save_provider_key(self.root, provider, api_key)
            config['model'] = model_id
            config['endpoint'] = OFFICIAL_ENDPOINTS[provider]
            temporary = self.path.with_suffix(self.path.suffix + '.tmp')
            temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            os.replace(str(temporary), str(self.path))
            return self._public_provider(provider, config)

    def test_connection(self, provider: str) -> Dict[str, Any]:
        config = self._provider(provider)
        endpoint = OFFICIAL_ENDPOINTS[provider]
        key = load_saved_provider_key(self.root, provider, endpoint)
        if not key:
            return {'ok': False, 'code': 'provider_key_missing'}
        payload = {
            'model': str(config.get('model') or OFFICIAL_MODELS[provider]),
            'messages': [{'role': 'user', 'content': 'Reply with OK only.'}],
            'max_tokens': 2048 if provider == 'zhipu' else 32,
            'stream': False,
        }
        if provider == 'deepseek':
            payload['thinking'] = {'type': 'disabled'}
        elif provider == 'zhipu':
            payload['thinking'] = {'type': 'enabled'}
        request = Request(endpoint, data=json.dumps(payload).encode('utf-8'), headers={
            'Accept': 'application/json', 'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + key,
        }, method='POST')
        try:
            with self.opener(request, timeout=90) as response:
                value = json.loads(response.read().decode('utf-8'))
            choices = value.get('choices') if isinstance(value, dict) else None
            content = choices[0].get('message', {}).get('content') if isinstance(choices, list) and choices else None
            if not str(content or '').strip():
                return {'ok': False, 'code': 'empty_or_truncated_response'}
            return {'ok': True, 'code': 'reachable_model_available'}
        except HTTPError as exc:
            return {'ok': False, 'code': 'http_{}'.format(int(exc.code))}
        except (OSError, URLError, ValueError, UnicodeError):
            return {'ok': False, 'code': 'request_failed'}

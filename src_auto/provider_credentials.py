"""Read PowerShell SecureString DPAPI files only for a pinned official endpoint.

Callers must check per-session consent before calling this function. No secret
is logged, returned to HTTP clients, or written to process environment variables.
"""

import os
from pathlib import Path

from .session_vault import _dpapi_protect, _dpapi_unprotect

OFFICIAL_ENDPOINTS = {
    'deepseek': 'https://api.deepseek.com/chat/completions',
    'zhipu': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
    'openrouter': 'https://openrouter.ai/api/v1/chat/completions',
}


def load_saved_provider_key(root: Path, provider: str, endpoint: str) -> str:
    if os.name != 'nt' or OFFICIAL_ENDPOINTS.get(provider) != endpoint:
        return ''
    try:
        root = Path(root).resolve()
        path = root / 'config' / 'secrets' / (provider + '_api_key.dpapi')
        if path.is_symlink():
            return ''
        path.resolve().relative_to(root)
        if not path.is_file() or path.stat().st_size > 65536:
            return ''
        ciphertext = bytes.fromhex(path.read_text(encoding='utf-8-sig').strip())
        return _dpapi_unprotect(ciphertext, b'').decode('utf-16-le').strip()
    except (OSError, ValueError, UnicodeError):
        return ''


def saved_provider_key_exists(root: Path, provider: str) -> bool:
    if provider not in OFFICIAL_ENDPOINTS:
        return False
    try:
        root = Path(root).resolve()
        path = root / 'config' / 'secrets' / (provider + '_api_key.dpapi')
        path.resolve().relative_to(root)
        return not path.is_symlink() and path.is_file() and 0 < path.stat().st_size <= 65536
    except (OSError, ValueError):
        return False


def save_provider_key(root: Path, provider: str, api_key: str) -> Path:
    if os.name != 'nt' or provider not in OFFICIAL_ENDPOINTS:
        raise ValueError('provider_secret_not_supported')
    key = str(api_key or '').strip()
    if not 8 <= len(key) <= 2048 or '\x00' in key or '\r' in key or '\n' in key:
        raise ValueError('provider_secret_invalid')
    root = Path(root).resolve()
    directory = root / 'config' / 'secrets'
    if directory.exists() and directory.is_symlink():
        raise ValueError('provider_secret_directory_not_allowed')
    directory.mkdir(parents=True, exist_ok=True)
    directory.resolve().relative_to(root)
    path = directory / (provider + '_api_key.dpapi')
    if path.is_symlink():
        raise ValueError('provider_secret_symlink_not_allowed')
    encrypted = _dpapi_protect(key.encode('utf-16-le'), b'').hex()
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(encrypted, encoding='ascii')
    os.replace(str(temporary), str(path))
    return path

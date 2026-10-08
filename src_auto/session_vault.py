import base64
import ctypes
import hashlib
import json
import os
import re
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping
from urllib.parse import urlsplit

from .local_scope import aware_timestamp


class SessionVaultError(ValueError):
    pass


@dataclass(frozen=True)
class SessionProfile:
    name: str
    role: str
    headers: Mapping[str, str]
    target_id: str = ''
    origin: str = ''
    expires_at: str = ''


def bound_origin(value):
    if not isinstance(value, str) or not re.fullmatch(r'https?://(127\.0\.0\.1|\[::1\]):[0-9]{1,5}', value):
        raise SessionVaultError('session_origin_invalid')
    parsed = urlsplit(value)
    if not 1 <= parsed.port <= 65535:
        raise SessionVaultError('session_origin_invalid')
    return value


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(value: bytes):
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi_protect(value: bytes, entropy: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, source_buffer = _blob(value)
    extra, extra_buffer = _blob(entropy)
    output = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        "SRC-Auto test session",
        ctypes.byref(extra),
        None,
        None,
        0x1,
        ctypes.byref(output),
    )
    if not ok:
        raise SessionVaultError("dpapi_protect_failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        del source_buffer, extra_buffer


def _dpapi_unprotect(value: bytes, entropy: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, source_buffer = _blob(value)
    extra, extra_buffer = _blob(entropy)
    output = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(extra),
        None,
        None,
        0x1,
        ctypes.byref(output),
    )
    if not ok:
        raise SessionVaultError("dpapi_unprotect_failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        del source_buffer, extra_buffer


class SessionVault:
    _NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

    def __init__(self, project_root: Path, vault_dir: Path = None):
        self.project_root = Path(project_root).resolve()
        self.vault_dir = Path(vault_dir or (self.project_root / "config" / "sessions")).resolve()
        try:
            self.vault_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise SessionVaultError("vault_outside_project") from exc
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._entropy = hashlib.sha256(
            (str(self.project_root).lower() + "|SRC-Auto|test-session-v1").encode("utf-8")
        ).digest()

    def _path(self, name: str) -> Path:
        if not isinstance(name, str):
            raise SessionVaultError('invalid_profile_name')
        normalized = (name or "").strip().lower()
        if not self._NAME.fullmatch(normalized):
            raise SessionVaultError("invalid_profile_name")
        return self.vault_dir / (normalized + ".dpapi.json")

    @staticmethod
    def _clean_profile(profile: SessionProfile) -> SessionProfile:
        name = (profile.name or "").strip().lower()
        role = (profile.role or "").strip()
        if not role:
            raise SessionVaultError("profile_role_required")
        headers = {}
        for raw_name, raw_value in dict(profile.headers or {}).items():
            header_name = str(raw_name).strip()
            header_value = str(raw_value)
            if not header_name or "\r" in header_name or "\n" in header_name:
                raise SessionVaultError("invalid_header_name")
            if "\r" in header_value or "\n" in header_value:
                raise SessionVaultError("invalid_header_value")
            headers[header_name] = header_value
        if not headers:
            raise SessionVaultError("profile_headers_required")
        if profile.target_id or profile.origin or profile.expires_at:
            if not re.fullmatch(r'custom-[a-f0-9]{32}', profile.target_id or ''):
                raise SessionVaultError('session_binding_required')
            bound_origin(profile.origin)
            try:
                aware_timestamp(profile.expires_at, 'expiresAt')
            except ValueError:
                raise SessionVaultError('session_expiry_invalid') from None
            if (set(headers) - {'Authorization', 'Cookie'} or any(not x or len(x) > 8192 or
                    any(ord(c) < 32 or ord(c) > 255 or ord(c) == 127 for c in x) for x in headers.values())
                    or any(type(x) is not str for x in profile.headers.values())):
                raise SessionVaultError('session_headers_invalid')
        return SessionProfile(name, role, headers, profile.target_id, profile.origin, profile.expires_at)

    def save(self, profile: SessionProfile) -> Path:
        clean = self._clean_profile(profile)
        path = self._path(clean.name)
        bound = bool(clean.target_id)
        # Bind context inside DPAPI as well as public metadata: editing the
        # JSON target/role/expiry must never rebind decrypted credentials.
        protected = dict(headers=dict(clean.headers), name=clean.name, role=clean.role,
                         target_id=clean.target_id, origin=clean.origin, expires_at=clean.expires_at) if bound else dict(clean.headers)
        plaintext = json.dumps(protected, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = _dpapi_protect(plaintext, self._entropy)
        document = {
            "schema_version": 2 if bound else 1,
            "name": clean.name,
            "role": clean.role,
            "header_names": sorted(clean.headers),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if bound:
            document.update(target_id=clean.target_id, origin=clean.origin, expires_at=clean.expires_at)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(self.vault_dir),
                                             prefix=clean.name + '-', suffix='.tmp', delete=False) as stream:
                temp = Path(stream.name)
                stream.write(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            os.replace(str(temp), str(path))
        finally:
            if temp is not None and temp.exists():
                temp.unlink()
        return path

    def load(self, name: str) -> SessionProfile:
        path = self._path(name)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            ciphertext = base64.b64decode(document["ciphertext"], validate=True)
            plaintext = _dpapi_unprotect(ciphertext, self._entropy)
            protected = json.loads(plaintext.decode("utf-8"))
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SessionVaultError("session_profile_unavailable") from exc
        if not isinstance(protected, dict):
            raise SessionVaultError("session_profile_invalid")
        if document.get('schema_version') == 2:
            fields = ('name', 'role', 'target_id', 'origin', 'expires_at')
            if any(protected.get(key) != document.get(key) for key in fields) or protected.get('name') != name:
                raise SessionVaultError('session_profile_invalid')
            try:
                return self._clean_profile(SessionProfile(protected['name'], protected['role'], protected['headers'],
                    protected['target_id'], protected['origin'], protected['expires_at']))
            except (KeyError, TypeError, ValueError):
                raise SessionVaultError('session_profile_invalid') from None
        if document.get('schema_version') != 1:
            raise SessionVaultError('session_profile_invalid')
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in protected.items()):
            # A schema-2 envelope is not a legacy header dictionary, even if
            # somebody changes the unauthenticated public schema number.
            raise SessionVaultError('session_profile_invalid')
        return SessionProfile(str(document.get("name", "")), str(document.get("role", "")), protected)

    def load_for_target(self, name, target_id, origin, role, now=None):
        profile = self.load(name)
        if not profile.target_id:
            raise SessionVaultError('session_binding_required')
        if (profile.target_id, profile.origin, profile.role) != (target_id, origin, role):
            raise SessionVaultError('session_target_mismatch')
        if aware_timestamp(profile.expires_at, 'expiresAt') <= (now or datetime.now(timezone.utc)):
            raise SessionVaultError('session_expired')
        return profile

    def list_profiles(self) -> List[Dict[str, object]]:
        result = []
        for path in sorted(self.vault_dir.glob("*.dpapi.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                metadata = {
                        "name": str(document.get("name", "")),
                        "role": str(document.get("role", "")),
                        "header_names": sorted(str(value) for value in document.get("header_names", [])),
                    }
                if document.get('schema_version') == 2:
                    profile = self.load(metadata['name'])
                    metadata.update(bound=True, targetId=profile.target_id, origin=profile.origin, expiresAt=profile.expires_at,
                                    expired=aware_timestamp(profile.expires_at, 'expiresAt') <= datetime.now(timezone.utc),
                                    revision=hashlib.sha256(path.read_bytes()).hexdigest())
                result.append(metadata)
            except (OSError, ValueError, TypeError):
                continue
        return result

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.exists():
            return False
        path.unlink()
        return True

import base64
import ctypes
import hashlib
import json
import os
import re
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping


class SessionVaultError(ValueError):
    pass


@dataclass(frozen=True)
class SessionProfile:
    name: str
    role: str
    headers: Mapping[str, str]


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
        return SessionProfile(name, role, headers)

    def save(self, profile: SessionProfile) -> Path:
        clean = self._clean_profile(profile)
        path = self._path(clean.name)
        plaintext = json.dumps(dict(clean.headers), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = _dpapi_protect(plaintext, self._entropy)
        document = {
            "schema_version": 1,
            "name": clean.name,
            "role": clean.role,
            "header_names": sorted(clean.headers),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(str(temp), str(path))
        return path

    def load(self, name: str) -> SessionProfile:
        path = self._path(name)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            ciphertext = base64.b64decode(document["ciphertext"], validate=True)
            plaintext = _dpapi_unprotect(ciphertext, self._entropy)
            headers = json.loads(plaintext.decode("utf-8"))
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SessionVaultError("session_profile_unavailable") from exc
        if not isinstance(headers, dict):
            raise SessionVaultError("session_profile_invalid")
        return SessionProfile(str(document.get("name", "")), str(document.get("role", "")), headers)

    def list_profiles(self) -> List[Dict[str, object]]:
        result = []
        for path in sorted(self.vault_dir.glob("*.dpapi.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                result.append(
                    {
                        "name": str(document.get("name", "")),
                        "role": str(document.get("role", "")),
                        "header_names": sorted(str(value) for value in document.get("header_names", [])),
                    }
                )
            except (OSError, ValueError, TypeError):
                continue
        return result

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.exists():
            return False
        path.unlink()
        return True

"""Versioned, fail-closed permissions for an operator-owned loopback Web app."""

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple
from urllib.parse import urlsplit


LOCAL_WEB_TYPE = "local_web"
READONLY_PROFILE = "readonly-baseline-v1"
PASSIVE_PROFILE = "bounded-passive-v1"
_FIELDS = {
    "schema_version", "target_type", "target_id", "origin", "confirmed", "allow_network_contact",
    "automation_allowed", "allowed_paths", "excluded_paths", "allowed_methods", "window_start",
    "window_end", "authorization_note", "profile_id", "limits",
}
_ORIGIN = re.compile(r"^(http|https)://(127\.0\.0\.1|\[::1\]):([0-9]{1,5})/?$")
_PATH = re.compile(r"/[A-Za-z0-9/._~-]*\Z")


def strict_boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(field + " must be boolean")
    return value


def safe_local_path(value: Any) -> str:
    # Exact ASCII routes in v1: rejecting encoded/ambiguous paths is preferable
    # to guessing which decoding/normalization the application will perform.
    if (not isinstance(value, str) or len(value) > 1024 or not _PATH.fullmatch(value)
            or "//" in value or any(part in (".", "..") for part in value.split("/"))):
        raise ValueError("local_path_invalid")
    return value


def aware_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError(field + " must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone_required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError(field + " must be an aware ISO timestamp") from None


def _paths(value: Any, field: str, required: bool) -> Tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 64 or (required and not value):
        raise ValueError(field + " must be a bounded list")
    return tuple(sorted({safe_local_path(item) for item in value}))


@dataclass(frozen=True)
class LocalRequestLimits:
    concurrency: int
    request_limit: int
    task_timeout_seconds: int
    request_timeout_seconds: int
    response_limit_bytes: int
    output_limit_bytes: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LocalRequestLimits":
        ceilings = {"concurrency": 1, "request_limit": 1000, "task_timeout_seconds": 900,
                    "request_timeout_seconds": 10, "response_limit_bytes": 65536,
                    "output_limit_bytes": 1048576}
        if not isinstance(value, Mapping) or set(value) != set(ceilings):
            raise ValueError("local_limits_fields_invalid")
        for key, ceiling in ceilings.items():
            if type(value[key]) is not int or not 1 <= value[key] <= ceiling:
                raise ValueError("local_limit_invalid_" + key)
        if value["request_timeout_seconds"] > value["task_timeout_seconds"]:
            raise ValueError("local_request_timeout_exceeds_task")
        return cls(**dict(value))


@dataclass(frozen=True)
class LocalWebScope:
    origin: str
    automation_allowed: bool
    allowed_paths: Tuple[str, ...]
    excluded_paths: Tuple[str, ...]
    allowed_methods: Tuple[str, ...]
    window_start: datetime
    window_end: datetime
    authorization_note: str
    profile_id: str
    limits: LocalRequestLimits

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LocalWebScope":
        if set(value) != _FIELDS:
            raise ValueError("local_scope_fields_invalid")
        if type(value["schema_version"]) is not int or value["schema_version"] != 2:
            raise ValueError("local_scope_version_unsupported")
        if value["target_type"] != LOCAL_WEB_TYPE:
            raise ValueError("local_target_type_unsupported")
        target = value["target_id"]
        if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", target):
            raise ValueError("local_target_id_invalid")
        origin = value["origin"]
        match = _ORIGIN.fullmatch(origin) if isinstance(origin, str) else None
        if match is None or not 1 <= int(match.group(3)) <= 65535:
            raise ValueError("local_origin_requires_literal_loopback_and_explicit_port")
        origin = "{}://{}:{}".format(match.group(1), match.group(2), int(match.group(3)))
        methods = value["allowed_methods"]
        if (not isinstance(methods, list) or not methods or len(methods) > 2
                or any(method not in ("GET", "HEAD") for method in methods)):
            raise ValueError("local_readonly_methods_required")
        start, end = (aware_timestamp(value[key], key) for key in ("window_start", "window_end"))
        if end <= start:
            raise ValueError("local_time_window_invalid")
        note = value["authorization_note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 2000 or any(ord(c) < 32 for c in note):
            raise ValueError("local_authorization_note_required")
        if value["profile_id"] not in (READONLY_PROFILE, PASSIVE_PROFILE):
            raise ValueError("local_profile_unsupported")
        return cls(origin, strict_boolean(value["automation_allowed"], "automation_allowed"),
                   _paths(value["allowed_paths"], "allowed_paths", True),
                   _paths(value["excluded_paths"], "excluded_paths", False), tuple(sorted(set(methods))),
                   start, end, note.strip(), value["profile_id"], LocalRequestLimits.from_mapping(value["limits"]))

    def canonical(self) -> Mapping[str, Any]:
        return {"origin": self.origin, "automation_allowed": self.automation_allowed,
                "allowed_paths": list(self.allowed_paths), "excluded_paths": list(self.excluded_paths),
                "allowed_methods": list(self.allowed_methods), "window_start": self.window_start.isoformat(),
                "window_end": self.window_end.isoformat(), "authorization_note": self.authorization_note,
                "profile_id": self.profile_id, "limits": asdict(self.limits)}

    def denial_reason(self, url: str, method: str, now: Optional[datetime] = None) -> str:
        if not self.automation_allowed:
            return "automation_not_allowed"
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            return "invalid_current_time"
        if not self.window_start <= now.astimezone(timezone.utc) < self.window_end:
            return "outside_test_window"
        parsed, approved = urlsplit(url), urlsplit(self.origin)
        if (parsed.scheme, parsed.netloc) != (approved.scheme, approved.netloc):
            return "origin_not_in_scope"
        if method not in self.allowed_methods:
            return "method_not_in_scope"
        if "?" in url or "#" in url:
            return "local_query_or_fragment_not_allowed"
        try:
            path = safe_local_path(parsed.path or "/")
        except ValueError:
            return "local_path_invalid"
        for excluded in self.excluded_paths:
            base = excluded.rstrip("/")
            if not base or path == base or path.startswith(base + "/"):
                return "path_excluded"
        if path not in self.allowed_paths:
            return "path_not_in_scope"
        return ""

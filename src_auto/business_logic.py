"""Conservative helpers for offline business-logic review.

This module deliberately stops at candidate generation.  It never labels an
authorization issue as confirmed and it never returns response bodies or
secret values in a report.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .scope import ScopeGuard


class BusinessLogicError(ValueError):
    """Raised when a requested check crosses a safety gate."""


@dataclass(frozen=True)
class RequestTemplate:
    name: str
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Any = None


@dataclass(frozen=True)
class ResponseSnapshot:
    status_code: int
    headers: Mapping[str, str]
    body: Any


@dataclass(frozen=True)
class AuthorizationCase:
    name: str
    expected_roles: Tuple[str, ...]
    owner: ResponseSnapshot
    peer: ResponseSnapshot
    anonymous: ResponseSnapshot


_SENSITIVE_FIELDS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
}


def validate_request(
    request: RequestTemplate,
    guard: ScopeGuard,
    allow_mutation: bool = False,
    manual_confirmed: bool = False,
    synthetic_object: bool = False,
) -> RequestTemplate:
    """Validate a single, explicit request against scope and mutation gates."""

    method = request.method.strip().upper()
    decision = guard.decide(request.url)
    if not decision.allowed:
        raise BusinessLogicError("scope_denied: {}".format(decision.reason))
    if method in {"DELETE", "CONNECT", "TRACE"}:
        raise BusinessLogicError("destructive_method_blocked")
    if method not in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH"}:
        raise BusinessLogicError("unsupported_method")
    if method in {"POST", "PUT", "PATCH"}:
        if not allow_mutation or not manual_confirmed:
            raise BusinessLogicError("mutation_not_approved")
        if not synthetic_object:
            raise BusinessLogicError("synthetic_object_required")
    return RequestTemplate(request.name, method, request.url, request.headers, request.body)


def _excluded_fields(volatile_fields: Optional[Iterable[str]]) -> Set[str]:
    result = set(_SENSITIVE_FIELDS)
    if volatile_fields:
        result.update(str(item).lower() for item in volatile_fields)
    return result


def _sanitise(value: Any, excluded: Set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitise(item, excluded)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).lower() not in excluded
        }
    if isinstance(value, (list, tuple)):
        return [_sanitise(item, excluded) for item in value]
    return value


def _digest(value: Any, excluded: Set[str]) -> str:
    payload = json.dumps(_sanitise(value, excluded), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_authorization_responses(
    owner: ResponseSnapshot,
    peer: ResponseSnapshot,
    anonymous: ResponseSnapshot,
    volatile_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Compare three already-captured responses without exposing their bodies."""

    excluded = _excluded_fields(volatile_fields)
    owner_digest = _digest(owner.body, excluded)
    peer_digest = _digest(peer.body, excluded)
    anonymous_digest = _digest(anonymous.body, excluded)
    equivalent = owner_digest == peer_digest

    if peer.status_code in {401, 403}:
        disposition = "authorization_enforced"
        next_action = "record_control"
    elif 200 <= owner.status_code < 300 and 200 <= peer.status_code < 300 and equivalent:
        disposition = "candidate_broken_object_authorization"
        next_action = "manual_review"
    else:
        disposition = "inconclusive"
        next_action = "manual_review"

    return {
        "owner_status": int(owner.status_code),
        "peer_status": int(peer.status_code),
        "anonymous_status": int(anonymous.status_code),
        "owner_peer_equivalent": equivalent,
        "owner_anonymous_equivalent": owner_digest == anonymous_digest,
        "body_fingerprints": {
            "owner": owner_digest,
            "peer": peer_digest,
            "anonymous": anonymous_digest,
        },
        "disposition": disposition,
        "confirmed": False,
        "next_action": next_action,
    }


def _flatten(value: Any, path: str, excluded: Set[str], output: Dict[str, str]) -> None:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            key_text = str(key)
            if key_text.lower() in excluded:
                continue
            _flatten(value[key], "{}.{}".format(path, key_text), excluded, output)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _flatten(item, "{}[{}]".format(path, index), excluded, output)
        return
    output[path] = _digest(value, excluded)


def compare_api_objects(
    before: Any,
    after: Any,
    volatile_fields: Optional[Iterable[str]] = None,
) -> Dict[str, List[str]]:
    """Return structural JSON-path differences, never raw object values."""

    excluded = _excluded_fields(volatile_fields)
    left: Dict[str, str] = {}
    right: Dict[str, str] = {}
    _flatten(before, "$", excluded, left)
    _flatten(after, "$", excluded, right)
    left_paths = set(left)
    right_paths = set(right)
    return {
        "added_paths": sorted(right_paths - left_paths),
        "removed_paths": sorted(left_paths - right_paths),
        "changed_paths": sorted(path for path in left_paths & right_paths if left[path] != right[path]),
    }


def evaluate_authorization_matrix(
    cases: Sequence[AuthorizationCase],
    volatile_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Evaluate independent cases and keep candidate findings human-reviewed."""

    rows: List[Dict[str, Any]] = []
    summary = {"candidate": 0, "enforced": 0, "inconclusive": 0}
    for case in cases:
        result = compare_authorization_responses(case.owner, case.peer, case.anonymous, volatile_fields)
        if result["disposition"] == "candidate_broken_object_authorization":
            summary["candidate"] += 1
        elif result["disposition"] == "authorization_enforced":
            summary["enforced"] += 1
        else:
            summary["inconclusive"] += 1
        rows.append(
            {
                "name": case.name,
                "expected_roles": list(case.expected_roles),
                "result": result,
            }
        )
    return {
        "cases": rows,
        "summary": summary,
        "manual_review_required": summary["candidate"] > 0,
        "confirmed_findings": 0,
    }

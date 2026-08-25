"""Offline human target-selection review.

This module deliberately has no HTTP, subprocess, or adapter dependency.  It
only validates a human-authored Scope and live plan and asks ``ScopeGuard``
whether each URL would be allowed.  A successful review is not execution
authorization; ``run-live --execute-live`` remains the separate execution gate.
"""

import ipaddress
from pathlib import Path
from typing import Any, Dict, Mapping
from urllib.parse import urlsplit

from .config import load_mapping
from .live_plan import LivePlanError, validate_live_plan
from .scope import ScopeGuard, ScopePolicy, normalize_host


class TargetReviewError(ValueError):
    """Raised for invalid or unsafe offline target-review input."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _inside_project(project_root: Path, path: Path) -> bool:
    try:
        _resolved(path).relative_to(_resolved(project_root))
        return True
    except ValueError:
        return False


def _target_kind(url: str) -> str:
    try:
        host = normalize_host(urlsplit(url).hostname or "")
        if host == "localhost":
            return "loopback"
        try:
            return "loopback" if ipaddress.ip_address(host).is_loopback else "nonlocal"
        except ValueError:
            return "nonlocal"
    except ValueError:
        return "unknown"


def _blocked(status: str, reason: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "reason": reason,
        "network_contact": False,
        "selection_confirmed": False,
    }
    result.update(extra)
    return result

def review_target_selection(
    project_root: Path,
    scope_path: Path,
    plan_path: Path,
    confirm_selection: bool = False,
) -> Dict[str, Any]:
    """Review a Scope/plan pair without making any network contact.

    The returned document is stable enough for CLI/audit use but intentionally
    excludes command arguments.  ``confirm_selection`` records only the human
    selection step; it never turns on live execution.
    """

    root = _resolved(Path(project_root))
    scope = _resolved(Path(scope_path))
    plan = _resolved(Path(plan_path))
    if not _inside_project(root, scope):
        return _blocked("blocked_scope", "scope_outside_project_root")
    if not _inside_project(root, plan):
        return _blocked("blocked_plan", "plan_outside_project_root")

    try:
        scope_policy = ScopePolicy.from_file(scope)
    except (OSError, ValueError, TypeError) as exc:
        return _blocked("blocked_scope", "scope_invalid", detail=str(exc)[:240])
    guard = ScopeGuard(scope_policy)
    if not scope_policy.confirmed or not scope_policy.allow_network_contact:
        return _blocked(
            "blocked_scope",
            "scope_confirmation_required",
            scope_digest=scope_policy.digest(),
        )

    try:
        plan_document: Mapping[str, Any] = load_mapping(plan)
        canonical_plan = validate_live_plan(plan_document)
    except (OSError, ValueError, TypeError, LivePlanError) as exc:
        return _blocked("blocked_plan", str(exc)[:240])

    decisions = []
    denied_reason = ""
    for target_url in canonical_plan["target_urls"]:
        decision = guard.decide(target_url)
        item = {
            "url": target_url,
            "kind": _target_kind(target_url),
            "host": decision.host,
            "port": decision.port,
            "allowed": bool(decision.allowed),
            "reason": decision.reason,
        }
        decisions.append(item)
        if not decision.allowed and not denied_reason:
            denied_reason = decision.reason

    result: Dict[str, Any] = {
        "status": "selection_reviewed" if not denied_reason and confirm_selection else "awaiting_selection" if not denied_reason else "blocked_selection",
        "reason": denied_reason or ("confirm_selection_required" if not confirm_selection else "selection_reviewed"),
        "network_contact": False,
        "selection_confirmed": bool(confirm_selection and not denied_reason),
        "scope_target_id": scope_policy.target_id,
        "scope_digest": scope_policy.digest(),
        "plan_digest": canonical_plan["plan_digest"],
        "operator": canonical_plan["operator"],
        "target_count": len(decisions),
        "targets": decisions,
        "tools": list(canonical_plan["sequence"]),
        "manual_execution_required": True,
    }
    if not denied_reason:
        result["next_step"] = "run-live --execute-live"
    return result

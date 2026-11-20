"""Human confirmation that turns a non-authorizing candidate into a confirmed scope.

Confirmation is an auditable, scope-level decision only. It never executes tools
or contacts the network; execution still requires the separate run-live gates
(policy switch, confirmed scope, reviewed plan and ``--execute-live``).
"""
import json
import os
from pathlib import Path
from typing import Mapping

from .config import load_mapping
from .scope import ScopePolicy


class ScopeConfirmError(ValueError):
    """Raised when a candidate cannot be human-confirmed into a scope."""


def confirm_scope(candidate_path, output_dir, *, operator, authorization_note, confirm):
    """Write a confirmed legacy scope and return its path/hash, or raise.

    The candidate must currently be unconfirmed. Confirmation flips the two deny
    flags to ``True`` and records who authorized it; it performs no network I/O.
    """
    if not confirm:
        raise ScopeConfirmError("explicit_confirmation_required")
    operator = str(operator or "").strip()
    authorization_note = str(authorization_note or "").strip()
    if not operator or not authorization_note:
        raise ScopeConfirmError("operator_and_authorization_note_required")

    try:
        candidate = load_mapping(Path(candidate_path))
    except Exception:
        raise ScopeConfirmError("candidate_load_failed")
    if not isinstance(candidate, Mapping):
        raise ScopeConfirmError("candidate_load_failed")
    if candidate.get("confirmed") is True:
        raise ScopeConfirmError("candidate_already_confirmed")

    # Reuse the strict parser to normalize hosts/ports and reject malformed values.
    policy = ScopePolicy.from_mapping(candidate)
    if policy.target_type != "legacy":
        raise ScopeConfirmError("only_legacy_scope_supported")
    if not policy.target_id:
        raise ScopeConfirmError("target_id_required")
    if not policy.allowed_hosts and not policy.root_domains:
        raise ScopeConfirmError("empty_scope_hosts")
    if not policy.allowed_ports:
        raise ScopeConfirmError("empty_scope_ports")

    confirmed = ScopePolicy(
        target_id=policy.target_id,
        root_domains=policy.root_domains,
        allowed_hosts=policy.allowed_hosts,
        excluded_hosts=policy.excluded_hosts,
        allowed_ports=policy.allowed_ports,
        confirmed=True,
        allow_network_contact=True,
    )
    # canonical() carries exactly the fields that feed digest(); the audit metadata
    # below is written alongside but never changes the scope hash run-live relies on.
    document = dict(confirmed.canonical())
    document.update({
        "schema_version": 1,
        "target_type": "legacy",
        "vendor": str(candidate.get("vendor", "")),
        "authorization_source": str(candidate.get("authorization_source", candidate.get("source_url", ""))),
        "test_window": str(candidate.get("test_window", "")),
        "operator": operator,
        "authorization_note": authorization_note,
    })

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "scope_confirmed.yaml"
    try:
        # 'x' mode: never overwrite an existing confirmed scope.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise ScopeConfirmError("confirmed_scope_already_exists")

    return {
        "scope_path": str(path),
        "scope_hash": confirmed.digest(),
        "target_id": confirmed.target_id,
    }

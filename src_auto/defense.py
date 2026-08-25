"""Owned-domain observation planning with explicit authorization gates."""

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping

from .business_logic import compare_api_objects
from .scope import normalize_host


class DefenseError(ValueError):
    pass


_ASSET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


@dataclass(frozen=True)
class DefenseAsset:
    asset_id: str
    domain: str
    authorization_source: str = ""
    confirmed_owned: bool = False
    allow_automated_observation: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DefenseAsset":
        asset_id = str(value.get("asset_id", "")).strip().lower()
        raw_domain = str(value.get("domain", "")).strip()
        if raw_domain.startswith("*."):
            raise DefenseError("wildcard_not_allowed")
        domain = normalize_host(raw_domain)
        if not _ASSET_ID.fullmatch(asset_id):
            raise DefenseError("invalid_asset_id")
        if not _DOMAIN.fullmatch(domain):
            raise DefenseError("invalid_domain")
        return cls(
            asset_id=asset_id,
            domain=domain,
            authorization_source=str(value.get("authorization_source", "")).strip(),
            confirmed_owned=bool(value.get("confirmed_owned", False)),
            allow_automated_observation=bool(value.get("allow_automated_observation", False)),
        )


def build_defense_plan(asset: DefenseAsset) -> Dict[str, Any]:
    if not asset.confirmed_owned or not asset.authorization_source:
        raise DefenseError("ownership_confirmation_required")
    if not asset.allow_automated_observation:
        raise DefenseError("automated_observation_permission_required")
    return {
        "asset_id": asset.asset_id,
        "domain": asset.domain,
        "mode": "defense_observation",
        "authorization_source": asset.authorization_source,
        "rate_limit_per_second": 1,
        "max_concurrency": 1,
        "redirect_policy": "same_registered_domain_only",
        "steps": ["dns_snapshot", "tls_snapshot", "http_headers", "asset_diff", "log_review"],
        "excluded_actions": [
            "credential_testing",
            "content_mutation",
            "destructive_testing",
            "denial_of_service",
            "proof_of_impact_actions",
        ],
        "manual_review_required": True,
    }


def compare_defense_snapshots(before: Any, after: Any) -> Dict[str, Any]:
    result = compare_api_objects(
        before,
        after,
        volatile_fields={"body", "response_body", "authorization", "cookie", "token", "secret"},
    )
    result["manual_review_required"] = bool(
        result["added_paths"] or result["removed_paths"] or result["changed_paths"]
    )
    return result

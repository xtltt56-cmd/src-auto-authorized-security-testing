import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .scope import ScopePolicy


class ScopeResolver:
    """Convert an explicit platform-rule snapshot into a non-authorizing candidate."""

    def resolve(self, snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        target_id = str(snapshot.get("target_id", "")).strip()
        if not target_id:
            raise ValueError("target_id is required")
        candidate = {
            "target_id": target_id,
            "vendor": str(snapshot.get("vendor", "")),
            "authorization_source": str(snapshot.get("authorization_source", snapshot.get("source_url", ""))),
            "source_url": str(snapshot.get("source_url", "")),
            "root_domains": list(snapshot.get("root_domains", [])),
            "allowed_hosts": list(snapshot.get("allowed_hosts", [])),
            "excluded_hosts": list(snapshot.get("excluded_hosts", [])),
            "allowed_ports": list(snapshot.get("allowed_ports", [])),
            "test_window": str(snapshot.get("test_window", "")),
            "confirmed": False,
            "allow_network_contact": False,
        }
        # Reuse the strict parser to normalize and reject malformed ports, but force deny flags again.
        policy = ScopePolicy.from_mapping(candidate)
        candidate.update(policy.canonical())
        candidate["confirmed"] = False
        candidate["allow_network_contact"] = False
        return candidate

    def write_candidate(self, output_dir: Path, snapshot: Mapping[str, Any]) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "scope_candidate.yaml"
        candidate = self.resolve(snapshot)
        path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

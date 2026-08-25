from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Set
from urllib.parse import urlsplit, urlunsplit

from .scope import ScopeGuard, normalize_host
from .store import Store


SAFE_ASSET_METADATA = ("title", "status_code", "server", "tls_issuer", "tls_expiry", "technology")
SAFE_TEMPLATE_TAGS = ("ssl", "misconfig", "exposure")


class AttackSurfaceError(ValueError):
    pass


@dataclass(frozen=True)
class AttackSurfaceTarget:
    target_id: str
    root_url: str
    hostname: str

    @classmethod
    def from_url(cls, target_id: str, value: str) -> "AttackSurfaceTarget":
        try:
            parsed = urlsplit((value or "").strip())
        except ValueError as exc:
            raise AttackSurfaceError("invalid_target_url") from exc
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            raise AttackSurfaceError("invalid_target_url")
        if parsed.username or parsed.password:
            raise AttackSurfaceError("credentials_not_allowed")
        hostname = normalize_host(parsed.hostname)
        try:
            port = parsed.port
        except ValueError as exc:
            raise AttackSurfaceError("invalid_target_port") from exc
        host_part = hostname
        if ":" in hostname and not hostname.startswith("["):
            host_part = "[{}]".format(hostname)
        if port is not None:
            host_part = "{}:{}".format(host_part, port)
        canonical = urlunsplit((parsed.scheme.lower(), host_part, "/", "", ""))
        identifier = (target_id or "").strip().lower()
        if not identifier:
            raise AttackSurfaceError("target_id_required")
        return cls(identifier, canonical, hostname)


@dataclass(frozen=True)
class AttackSurfacePlan:
    target_id: str
    target_urls: List[str]
    sequence: List[str]
    commands: Mapping[str, List[str]]
    max_requests_per_second: int = 2
    execute: bool = False
    manual_execution_required: bool = True

    def to_mapping(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "name": "attack-surface-{}".format(self.target_id),
            "target_id": self.target_id,
            "target_urls": list(self.target_urls),
            "sequence": list(self.sequence),
            "commands": {name: list(args) for name, args in self.commands.items()},
            "max_requests_per_second": self.max_requests_per_second,
            "execute": self.execute,
            "manual_execution_required": self.manual_execution_required,
            "template_tags": list(SAFE_TEMPLATE_TAGS),
        }


def build_attack_surface_plan(
    target: AttackSurfaceTarget,
    scope_guard: ScopeGuard,
    automation_allowed: bool,
    available_tools: Set[str],
) -> AttackSurfacePlan:
    decision = scope_guard.decide(target.root_url)
    if not decision.allowed:
        if decision.reason == "scope_not_confirmed":
            raise AttackSurfaceError("scope_confirmation_required")
        raise AttackSurfaceError("target_out_of_scope: {}".format(decision.reason))
    if not automation_allowed:
        raise AttackSurfaceError("automation_permission_required")

    commands = {}
    sequence = []

    def add(name: str, args: List[str]) -> None:
        if name in available_tools:
            sequence.append(name)
            commands[name] = args

    add("subfinder", ["-silent", "-d", target.hostname])
    add("bbot", ["-t", target.hostname, "-p", "passive"])
    add("httpx", ["-silent", "-u", target.root_url, "-rl", "2", "-threads", "1", "-json"])
    add(
        "katana",
        ["-u", target.root_url, "-d", "2", "-c", "1", "-p", "1", "-rl", "2", "-jsonl"],
    )
    add(
        "nuclei",
        [
            "-u",
            target.root_url,
            "-tags",
            ",".join(SAFE_TEMPLATE_TAGS),
            "-pt",
            "http,ssl,dns",
            "-rl",
            "2",
            "-c",
            "1",
            "-bs",
            "1",
            "-timeout",
            "5",
            "-retries",
            "1",
            "-no-interactsh",
            "-disable-unsigned-templates",
            "-jsonl",
        ],
    )
    return AttackSurfacePlan(target.target_id, [target.root_url], sequence, commands)


def _bounded_asset(asset: Mapping[str, Any]) -> Dict[str, Any]:
    host = normalize_host(str(asset.get("host", "")))
    url = str(asset.get("url", "")).strip()
    if not host or not url:
        raise AttackSurfaceError("asset_host_and_url_required")
    try:
        port = int(asset.get("port")) if asset.get("port") is not None else None
    except (TypeError, ValueError) as exc:
        raise AttackSurfaceError("asset_port_invalid") from exc
    metadata = {key: asset[key] for key in SAFE_ASSET_METADATA if key in asset}
    return {"host": host, "port": port, "url": url, "kind": str(asset.get("kind", "web")), "metadata": metadata}


def save_asset_snapshot(store: Store, run_id: str, assets: Iterable[Mapping[str, Any]]) -> List[str]:
    return store.snapshot_assets(run_id, [_bounded_asset(asset) for asset in assets])


def render_asset_diff_report(store: Store, previous_run_id: str, current_run_id: str) -> Dict[str, Any]:
    diff = store.diff_assets(previous_run_id, current_run_id)
    return {
        "schema_version": 1,
        "previous_run_id": previous_run_id,
        "current_run_id": current_run_id,
        "summary": {key: len(diff[key]) for key in ("added", "removed", "unchanged")},
        "fingerprints": diff,
        "verdict": "manual_review_required" if diff["added"] or diff["removed"] else "no_asset_change",
    }

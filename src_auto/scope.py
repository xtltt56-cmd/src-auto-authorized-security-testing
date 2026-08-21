import hashlib
import ipaddress
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional
from urllib.parse import SplitResult, urlsplit

from .config import load_mapping
from .models import ScopeDecision


def normalize_host(value: str) -> str:
    host = (value or "").strip().lower().rstrip(".")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _as_hosts(values: Iterable[Any]) -> List[str]:
    return sorted({normalize_host(str(value)) for value in values if str(value).strip()})


@dataclass
class ScopePolicy:
    target_id: str
    root_domains: List[str] = field(default_factory=list)
    allowed_hosts: List[str] = field(default_factory=list)
    excluded_hosts: List[str] = field(default_factory=list)
    allowed_ports: List[int] = field(default_factory=list)
    confirmed: bool = False
    allow_network_contact: bool = False
    source: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], source: str = "") -> "ScopePolicy":
        ports = []
        for raw in value.get("allowed_ports", []):
            try:
                port = int(raw)
            except (TypeError, ValueError):
                raise ValueError("allowed_ports must contain integers")
            if not 1 <= port <= 65535:
                raise ValueError("allowed_ports contains an invalid port")
            ports.append(port)
        return cls(
            target_id=str(value.get("target_id", "")).strip(),
            root_domains=_as_hosts(value.get("root_domains", [])),
            allowed_hosts=_as_hosts(value.get("allowed_hosts", [])),
            excluded_hosts=_as_hosts(value.get("excluded_hosts", [])),
            allowed_ports=sorted(set(ports)),
            confirmed=bool(value.get("confirmed", False)),
            allow_network_contact=bool(value.get("allow_network_contact", False)),
            source=source,
        )

    @classmethod
    def from_file(cls, path: Path) -> "ScopePolicy":
        return cls.from_mapping(load_mapping(path), str(path))

    def canonical(self) -> Mapping[str, Any]:
        return {
            "target_id": self.target_id,
            "root_domains": self.root_domains,
            "allowed_hosts": self.allowed_hosts,
            "excluded_hosts": self.excluded_hosts,
            "allowed_ports": self.allowed_ports,
            "confirmed": self.confirmed,
            "allow_network_contact": self.allow_network_contact,
        }

    def digest(self) -> str:
        payload = json.dumps(self.canonical(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScopeGuard:
    def __init__(self, policy: ScopePolicy):
        self.policy = policy

    def _host_allowed(self, host: str) -> bool:
        host = normalize_host(host)
        if not host:
            return False
        for excluded in self.policy.excluded_hosts:
            if host == excluded or host.endswith("." + excluded):
                return False
        if host in self.policy.allowed_hosts:
            return True
        for root in self.policy.root_domains:
            if host == root or host.endswith("." + root):
                return True
        return False

    def _split(self, url: str) -> Optional[SplitResult]:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        return parsed

    def decide(self, url: str) -> ScopeDecision:
        parsed = self._split(url)
        if parsed is None:
            return ScopeDecision(False, "invalid_or_unsupported_url", url=url)
        host = normalize_host(parsed.hostname or "")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            return ScopeDecision(False, "invalid_port", url=url, host=host)
        if not self.policy.confirmed or not self.policy.allow_network_contact:
            return ScopeDecision(False, "scope_not_confirmed", url=url, host=host, port=port)
        if not self._host_allowed(host):
            return ScopeDecision(False, "host_not_in_scope", url=url, host=host, port=port)
        if self.policy.allowed_ports and port not in self.policy.allowed_ports:
            return ScopeDecision(False, "port_not_in_scope", url=url, host=host, port=port)
        return ScopeDecision(True, "allowed", url=url, host=host, port=port)

    def check_redirect(self, original_url: str, location: str) -> ScopeDecision:
        original = self.decide(original_url)
        if not original.allowed:
            return ScopeDecision(False, "original_not_in_scope", url=location)
        return self.decide(location)

    def assert_allowed(self, url: str) -> None:
        decision = self.decide(url)
        if not decision.allowed:
            raise PermissionError("scope guard denied {}: {}".format(url, decision.reason))


def scope_from_file(path: Path) -> ScopeGuard:
    return ScopeGuard(ScopePolicy.from_file(path))

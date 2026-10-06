import hashlib
import ipaddress
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional
from datetime import datetime
from urllib.parse import SplitResult, urljoin, urlsplit

from .config import load_mapping
from .models import ScopeDecision
from .local_scope import LOCAL_WEB_TYPE, LocalWebScope, strict_boolean


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
    schema_version: int = 1
    target_type: str = "legacy"
    local_web: Optional[LocalWebScope] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], source: str = "") -> "ScopePolicy":
        if not isinstance(value, Mapping):
            raise ValueError("scope root must be a mapping")
        confirmed = strict_boolean(value.get("confirmed", False), "confirmed")
        contact = strict_boolean(value.get("allow_network_contact", False), "allow_network_contact")
        version, kind = value.get("schema_version", 1), value.get("target_type", "legacy")
        if kind == LOCAL_WEB_TYPE:
            local = LocalWebScope.from_mapping(value)
            parsed = urlsplit(local.origin)
            return cls(target_id=value["target_id"], allowed_hosts=[parsed.hostname], allowed_ports=[parsed.port],
                       confirmed=confirmed, allow_network_contact=contact, source=source,
                       schema_version=2, target_type=LOCAL_WEB_TYPE, local_web=local)
        if type(version) is not int or version != 1 or kind != "legacy":
            raise ValueError("scope_version_or_target_type_unsupported")
        ports = []
        for raw in value.get("allowed_ports", []):
            if type(raw) is not int and not (isinstance(raw, str) and raw.isdigit()):
                raise ValueError("allowed_ports must contain integers")
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
            confirmed=confirmed,
            allow_network_contact=contact,
            source=source,
        )

    @classmethod
    def from_file(cls, path: Path) -> "ScopePolicy":
        return cls.from_mapping(load_mapping(path), str(path))

    def canonical(self) -> Mapping[str, Any]:
        if self.target_type == LOCAL_WEB_TYPE and self.local_web is not None:
            return dict(self.local_web.canonical(), schema_version=2, target_type=LOCAL_WEB_TYPE,
                        target_id=self.target_id, confirmed=self.confirmed,
                        allow_network_contact=self.allow_network_contact)
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
        if not isinstance(url, str) or any(ord(char) < 32 or ord(char) == 127 for char in url) or "\\" in url:
            return None
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        return parsed

    def decide(self, url: str, method: str = "GET", now: Optional[datetime] = None) -> ScopeDecision:
        parsed = self._split(url)
        if parsed is None:
            return ScopeDecision(False, "invalid_or_unsupported_url", url=url)
        host = normalize_host(parsed.hostname or "")
        try:
            port = parsed.port
            if port is None:
                port = 443 if parsed.scheme == "https" else 80
            if not 1 <= port <= 65535:
                raise ValueError("invalid_port")
        except ValueError:
            return ScopeDecision(False, "invalid_port", url=url, host=host)
        if self.policy.confirmed is not True or self.policy.allow_network_contact is not True:
            return ScopeDecision(False, "scope_not_confirmed", url=url, host=host, port=port)
        if self.policy.target_type == LOCAL_WEB_TYPE:
            if self.policy.local_web is None:
                return ScopeDecision(False, "local_scope_missing", url=url, host=host, port=port)
            reason = self.policy.local_web.denial_reason(url, method, now)
            return ScopeDecision(not reason, reason or "allowed", url=url, host=host, port=port)
        if self.policy.target_type != "legacy":
            return ScopeDecision(False, "unsupported_target_type", url=url, host=host, port=port)
        if not self._host_allowed(host):
            return ScopeDecision(False, "host_not_in_scope", url=url, host=host, port=port)
        if port not in self.policy.allowed_ports:
            return ScopeDecision(False, "port_not_in_scope", url=url, host=host, port=port)
        return ScopeDecision(True, "allowed", url=url, host=host, port=port)

    def check_redirect(self, original_url: str, location: str, method: str = "GET", now: Optional[datetime] = None) -> ScopeDecision:
        original = self.decide(original_url, method=method, now=now)
        if not original.allowed:
            return ScopeDecision(False, "original_not_in_scope", url=location)
        if not isinstance(location, str) or any(ord(c) < 32 or ord(c) == 127 for c in location) or "\\" in location:
            return ScopeDecision(False, "invalid_redirect", url="")
        try:
            destination = urljoin(original_url, location)
        except ValueError:
            return ScopeDecision(False, "invalid_redirect", url="")
        return self.decide(destination, method=method, now=now)

    def assert_allowed(self, url: str, method: str = "GET", now: Optional[datetime] = None) -> None:
        decision = self.decide(url, method=method, now=now)
        if not decision.allowed:
            raise PermissionError("scope guard denied {}: {}".format(url, decision.reason))


def scope_from_file(path: Path) -> ScopeGuard:
    return ScopeGuard(ScopePolicy.from_file(path))

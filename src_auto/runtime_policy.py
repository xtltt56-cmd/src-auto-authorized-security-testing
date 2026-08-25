"""Hard runtime gates for a bounded local validation profile."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Tuple
from urllib.parse import urlsplit

from .config import load_mapping
from .scope import normalize_host


def _hosts(values: Iterable[Any]) -> Tuple[str, ...]:
    return tuple(sorted({normalize_host(str(value)) for value in values if str(value).strip()}))


def _ports(values: Iterable[Any]) -> Tuple[int, ...]:
    result = []
    for value in values:
        try:
            port = int(value)
        except (TypeError, ValueError):
            raise ValueError("allowed_ports must contain integers")
        if not 1 <= port <= 65535:
            raise ValueError("allowed_ports contains an invalid port")
        result.append(port)
    return tuple(sorted(set(result)))


@dataclass(frozen=True)
class RuntimePolicy:
    ai_provider: str
    local_llm_only: bool
    allow_remote_llm: bool
    allowed_hosts: Tuple[str, ...]
    allowed_ports: Tuple[int, ...]
    max_concurrency: int = 5

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RuntimePolicy":
        ai_provider = str(value.get("AI_PROVIDER", value.get("ai_provider", "local"))).strip().lower()
        local_llm_only = bool(value.get("LOCAL_LLM_ONLY", value.get("local_llm_only", True)))
        allow_remote_llm = bool(value.get("ALLOW_REMOTE_LLM", value.get("allow_remote_llm", False)))
        if ai_provider not in {"local", "remote"}:
            raise ValueError("AI_PROVIDER must be local or remote")
        if local_llm_only and ai_provider != "local":
            raise ValueError("LOCAL_LLM_ONLY requires AI_PROVIDER=local")
        if local_llm_only and allow_remote_llm:
            raise ValueError("LOCAL_LLM_ONLY cannot allow remote LLM")
        try:
            max_concurrency = int(value.get("max_concurrency", 5))
        except (TypeError, ValueError):
            raise ValueError("max_concurrency must be an integer")
        if not 1 <= max_concurrency <= 5:
            raise ValueError("max_concurrency must be between 1 and 5")
        return cls(
            ai_provider=ai_provider,
            local_llm_only=local_llm_only,
            allow_remote_llm=allow_remote_llm,
            allowed_hosts=_hosts(value.get("allowed_hosts", [])),
            allowed_ports=_ports(value.get("allowed_ports", [])),
            max_concurrency=max_concurrency,
        )

    @classmethod
    def from_file(cls, path: Path) -> "RuntimePolicy":
        return cls.from_mapping(load_mapping(Path(path)))

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "AI_PROVIDER": self.ai_provider,
            "LOCAL_LLM_ONLY": self.local_llm_only,
            "ALLOW_REMOTE_LLM": self.allow_remote_llm,
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_ports": list(self.allowed_ports),
            "max_concurrency": self.max_concurrency,
        }

    def decide_url(self, url: str) -> Tuple[bool, str]:
        if any(ord(char) < 32 for char in str(url or "")):
            return False, "invalid_url"
        try:
            parsed = urlsplit(str(url or ""))
        except ValueError:
            return False, "invalid_url"
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False, "invalid_or_unsupported_url"
        if parsed.username or parsed.password:
            return False, "credentials_in_url"
        host = normalize_host(parsed.hostname)
        if host not in self.allowed_hosts:
            return False, "host_not_allowlisted"
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            return False, "invalid_port"
        if self.allowed_ports and port not in self.allowed_ports:
            return False, "port_not_allowlisted"
        return True, "allowed"

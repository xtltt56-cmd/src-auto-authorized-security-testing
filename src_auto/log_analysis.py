"""Bounded, privacy-preserving analysis of local JSONL security logs."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlsplit


class LogAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class DefensiveEvent:
    """Normalized metadata for one defensive event; no raw body or credential."""

    timestamp: str
    source: str
    category: str
    status_class: str
    path: str
    client_fingerprint: str


def _contained_log_path(path: Path, project_root: Optional[Path]) -> Path:
    candidate = Path(path).resolve()
    if project_root is not None:
        root = Path(project_root).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise LogAnalysisError("log_path_outside_project") from exc
    return candidate


def _nested_value(event: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = event.get(key)
        if value is not None:
            return value
    for container_key in ("http", "network", "alert", "request"):
        nested = event.get(container_key)
        if isinstance(nested, Mapping):
            for key in keys:
                value = nested.get(key)
                if value is not None:
                    return value
    return None


def _event_path(event: Mapping[str, Any]) -> str:
    raw = str(_nested_value(event, "path", "uri", "url", "request_uri") or "/").strip()
    parsed = urlsplit(raw)
    path = parsed.path or raw.split("?", 1)[0] or "/"
    if not path.startswith("/"):
        path = "/" + path
    return path[:200]


def parse_defensive_log(path: Path, max_events: int = 10000, project_root: Optional[Path] = None) -> List[DefensiveEvent]:
    """Parse bounded Nginx/Wazuh/Zeek/Suricata-style JSONL to safe metadata."""

    if not 1 <= int(max_events) <= 50000:
        raise LogAnalysisError("max_events_out_of_range")
    source_path = _contained_log_path(Path(path), project_root)
    if not source_path.is_file():
        raise LogAnalysisError("log_file_not_found")
    events: List[DefensiveEvent] = []
    with source_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if len(events) >= int(max_events):
                break
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if not isinstance(raw, Mapping):
                continue
            source = str(raw.get("source", raw.get("service", raw.get("log_type", "generic")))).strip().lower()
            if source not in {"nginx", "wazuh", "zeek", "suricata"}:
                source = "generic"
            event_type = str(raw.get("event_type", raw.get("type", raw.get("category", "observation")))).strip().lower()
            category = "alert" if event_type in {"alert", "signature", "intrusion", "anomaly"} else "observation"
            status_class = _status_class(_nested_value(raw, "status", "status_code", "http_status"))
            raw_ip = str(_nested_value(raw, "ip", "client_ip", "src_ip", "source_ip") or "").strip()
            fingerprint = _short_hash(raw_ip) if raw_ip else ""
            events.append(
                DefensiveEvent(
                    timestamp=str(raw.get("timestamp", raw.get("ts", "")))[:80],
                    source=source,
                    category=category,
                    status_class=status_class,
                    path=_event_path(raw),
                    client_fingerprint=fingerprint,
                )
            )
    return events


def summarize_defensive_events(events: Iterable[DefensiveEvent]) -> Dict[str, Any]:
    """Aggregate defensive events into recommendation-only metadata."""

    statuses: Counter = Counter()
    sources: Counter = Counter()
    categories: Counter = Counter()
    paths: Counter = Counter()
    clients: Counter = Counter()
    count = 0
    for event in events:
        if not isinstance(event, DefensiveEvent):
            raise LogAnalysisError("defensive_event_invalid")
        count += 1
        statuses[event.status_class] += 1
        sources[event.source] += 1
        categories[event.category] += 1
        paths[event.path] += 1
        if event.client_fingerprint:
            clients[event.client_fingerprint] += 1
    requires_review = bool(statuses.get("4xx", 0) or statuses.get("5xx", 0) or categories.get("alert", 0))
    recommendations = []
    if statuses.get("4xx", 0) or statuses.get("5xx", 0):
        recommendations.append("人工核对异常状态码的业务变更、认证事件和限流记录")
    if categories.get("alert", 0):
        recommendations.append("人工复核告警签名与资产变更，不自动执行处置")
    return {
        "status": "COMPLETED",
        "event_count": count,
        "status_classes": dict(sorted(statuses.items())),
        "source_counts": dict(sorted(sources.items())),
        "category_counts": dict(sorted(categories.items())),
        "top_paths": paths.most_common(20),
        "top_client_fingerprints": clients.most_common(20),
        "recommendations": recommendations,
        "manual_review_required": requires_review,
        "automated_actions": [],
        "privacy": "client addresses hashed; query strings, headers and bodies omitted",
    }


def _status_class(raw: Any) -> str:
    try:
        status = int(raw)
    except (TypeError, ValueError):
        return "unknown"
    if 100 <= status <= 599:
        return "{}xx".format(status // 100)
    return "unknown"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def analyse_jsonl_security_log(path: Path, max_events: int = 10000) -> Dict[str, Any]:
    if not 1 <= int(max_events) <= 50000:
        raise LogAnalysisError("max_events_out_of_range")
    source = Path(path)
    if not source.is_file():
        raise LogAnalysisError("log_file_not_found")
    statuses: Counter = Counter()
    paths: Counter = Counter()
    client_hashes: Counter = Counter()
    malformed = 0
    count = 0
    with source.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if count >= max_events:
                break
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                malformed += 1
                continue
            if not isinstance(event, Mapping):
                malformed += 1
                continue
            count += 1
            statuses[_status_class(event.get("status"))] += 1
            raw_path = str(event.get("path", "")).split("?", 1)[0][:200] or "/unknown"
            paths[raw_path] += 1
            raw_ip = str(event.get("ip", event.get("client_ip", ""))).strip()
            if raw_ip:
                client_hashes[_short_hash(raw_ip)] += 1
    suspicious = statuses.get("4xx", 0) + statuses.get("5xx", 0)
    return {
        "status": "COMPLETED",
        "source_name": source.name,
        "event_count": count,
        "malformed_lines": malformed,
        "truncated": count >= max_events,
        "status_classes": dict(sorted(statuses.items())),
        "top_paths": paths.most_common(20),
        "top_client_fingerprints": client_hashes.most_common(20),
        "signals": {
            "error_responses": suspicious,
            "unique_client_fingerprints": len(client_hashes),
        },
        "manual_review_required": suspicious > 0 or malformed > 0,
        "privacy": "client addresses hashed; query strings, headers and bodies omitted",
    }

"""Bounded, privacy-preserving analysis of local JSONL security logs."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping


class LogAnalysisError(ValueError):
    pass


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

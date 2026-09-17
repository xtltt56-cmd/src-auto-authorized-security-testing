"""Redacted persistence for Dashboard task continuity.

The journal never resumes work after a process restart. It preserves only safe
task metadata and a bounded event stream so unfinished work becomes visibly
interrupted instead of remaining "running" forever.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


_MAX_JOURNAL_BYTES = 512 * 1024
_ACTIVE_STATES = frozenset(("queued", "running", "cancelling", "paused"))


class DashboardStateJournal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > _MAX_JOURNAL_BYTES:
            raise ValueError("dashboard_journal_too_large")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError("dashboard_journal_invalid_version")
        for name in ("operations", "detections", "events"):
            records = value.get(name, [])
            if not isinstance(records, list) or len(records) > 200:
                raise ValueError("dashboard_journal_invalid_records")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("dashboard_journal_invalid_record")
                for field in ("id", "elapsedSeconds", "progress"):
                    if field in record and (type(record[field]) is not int or record[field] < 0):
                        raise ValueError("dashboard_journal_invalid_number")
                if name != "events":
                    if record.get("state") not in _ACTIVE_STATES | {"completed", "failed", "cancelled", "idle"}:
                        raise ValueError("dashboard_journal_invalid_state")
                    counters = record.get("counters", {})
                    if not isinstance(counters, dict) or any(type(v) is not int or v < 0 for v in counters.values()):
                        raise ValueError("dashboard_journal_invalid_counters")
        if type(value.get("nextEventId", 1)) is not int:
            raise ValueError("dashboard_journal_invalid_event_id")
        return value

    def save(
        self,
        operations: Mapping[str, Mapping[str, Any]],
        detections: Mapping[str, Mapping[str, Any]],
        events: Iterable[Mapping[str, Any]],
        next_event_id: int,
        now: float,
    ) -> None:
        document = {
            "version": 1,
            "operations": [_safe_operation(item, now) for item in operations.values()],
            "detections": [_safe_detection(item, now) for item in detections.values()],
            "events": [_safe_event(item) for item in list(events)[-200:]],
            "nextEventId": max(1, int(next_event_id)),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def restored_state(record: Mapping[str, Any]) -> str:
    state = str(record.get("state", "idle"))
    return "failed" if state in _ACTIVE_STATES else state


def was_interrupted(record: Mapping[str, Any]) -> bool:
    return str(record.get("state", "")) in _ACTIVE_STATES


def _elapsed(item: Mapping[str, Any], now: float) -> int:
    started = float(item.get("started") or now)
    finished = item.get("finished")
    endpoint = float(finished) if finished is not None else now
    return max(0, int(endpoint - started))


def _safe_operation(item: Mapping[str, Any], now: float) -> Dict[str, Any]:
    return {
        "labId": str(item.get("lab_id", ""))[:80],
        "action": str(item.get("action", ""))[:20],
        "state": str(item.get("state", "idle"))[:20],
        "message": str(item.get("message", ""))[:200],
        "elapsedSeconds": _elapsed(item, now),
    }


def _safe_detection(item: Mapping[str, Any], now: float) -> Dict[str, Any]:
    counters = item.get("counters", {}) if isinstance(item.get("counters"), Mapping) else {}
    return {
        "labId": str(item.get("lab_id", ""))[:80],
        "action": "detect",
        "state": str(item.get("state", "idle"))[:20],
        "stage": str(item.get("stage", ""))[:80],
        "progress": max(0, min(100, int(item.get("progress", 0)))),
        "message": str(item.get("message", ""))[:200],
        "elapsedSeconds": _elapsed(item, now),
        "counters": {
            key: max(0, int(counters.get(key, 0)))
            for key in ("endpoints", "api", "candidates", "blocked", "errors")
        },
        "runId": str(item.get("run_id", ""))[:100],
        "reportId": str(item.get("report_id", ""))[:500],
        "networkContact": str(item.get("network_contact", "none"))[:20],
    }


def _safe_event(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": max(1, int(item.get("id", 1))),
        "taskId": str(item.get("taskId", ""))[:120],
        "time": str(item.get("time", ""))[:20],
        "level": str(item.get("level", "info"))[:20],
        "stage": str(item.get("stage", ""))[:80],
        "message": str(item.get("message", ""))[:200],
        "tool": "local-lab-controller",
        "redacted": True,
    }

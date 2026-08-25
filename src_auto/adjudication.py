"""Evidence-gated local finding adjudication and benchmark scoring."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set


ALLOWED_ADJUDICATION_STATUSES = frozenset({"TRUE_POSITIVE", "FALSE_POSITIVE", "POSSIBLE", "NOT_VERIFIED"})
_REDACTION_RE = re.compile(r"(?i)(authorization|cookie|set-cookie|x-api-key|token|secret|password)\s*[:=]\s*[^\s,;]+")


def _safe_text(value: Any, limit: int = 1600) -> str:
    text = str(value or "")
    text = _REDACTION_RE.sub(lambda match: match.group(1) + "=<redacted>", text)
    return text[:limit]


def adjudicate_finding(raw: Mapping[str, Any]) -> Dict[str, Any]:
    status = str(raw.get("status", "NOT_VERIFIED")).strip().upper() or "NOT_VERIFIED"
    record = {
        "title": _safe_text(raw.get("title", ""), 300),
        "endpoint": _safe_text(raw.get("endpoint", raw.get("url", "")), 800),
        "status": status,
        "expected_case_id": _safe_text(raw.get("expected_case_id", ""), 160),
        "evidence": _safe_text(raw.get("evidence", "")),
        "baseline": _safe_text(raw.get("baseline", "")),
        "reproduction": _safe_text(raw.get("reproduction", "")),
        "impact": _safe_text(raw.get("impact", "")),
        "submission_ready": bool(raw.get("submission_ready", False)),
        "reviewer": _safe_text(raw.get("reviewer", ""), 120),
        "reviewed_at": _safe_text(raw.get("reviewed_at", datetime.now(timezone.utc).isoformat()), 80),
        "notes": _safe_text(raw.get("notes", ""), 800),
    }
    return record


def validate_adjudication_record(record: Mapping[str, Any]) -> None:
    required = ("title", "endpoint", "status", "evidence", "baseline", "reproduction", "impact", "reviewer")
    missing = [key for key in required if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError("adjudication_missing:" + ",".join(missing))
    status = str(record.get("status", "")).strip().upper()
    if status not in ALLOWED_ADJUDICATION_STATUSES:
        raise ValueError("adjudication_status_invalid")
    if not isinstance(record.get("submission_ready", False), bool):
        raise ValueError("submission_ready_must_be_boolean")
    if bool(record.get("submission_ready")) and status != "TRUE_POSITIVE":
        raise ValueError("submission_requires_true_positive")
    endpoint = str(record.get("endpoint", ""))
    if any(ord(char) < 32 for char in endpoint):
        raise ValueError("adjudication_endpoint_invalid")


def benchmark_metrics(records: Iterable[Mapping[str, Any]], expected_cases: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = []
    for raw in records:
        record = adjudicate_finding(raw)
        validate_adjudication_record(record)
        normalized.append(record)
    positives: Set[str] = {
        str(case.get("case_id", "")).strip()
        for case in expected_cases
        if bool(case.get("positive")) and str(case.get("case_id", "")).strip()
    }
    true_ids = {
        str(item.get("expected_case_id", "")).strip()
        for item in normalized
        if item["status"] == "TRUE_POSITIVE" and str(item.get("expected_case_id", "")).strip()
    }
    true_positive = len(true_ids & positives)
    unmatched_true = sum(1 for item in normalized if item["status"] == "TRUE_POSITIVE" and str(item.get("expected_case_id", "")).strip() not in positives)
    false_positive = sum(1 for item in normalized if item["status"] == "FALSE_POSITIVE") + unmatched_true
    false_negative = len(positives - true_ids)
    possible = sum(1 for item in normalized if item["status"] == "POSSIBLE")
    not_verified = sum(1 for item in normalized if item["status"] == "NOT_VERIFIED")
    precision_denominator = true_positive + false_positive
    verified_denominator = true_positive + false_positive
    precision = true_positive / float(precision_denominator) if precision_denominator else None
    recall = true_positive / float(len(positives)) if positives else None
    f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and (precision + recall) else None
    verification_success_rate = true_positive / float(verified_denominator) if verified_denominator else None
    return {
        "status": "COMPLETED_ADJUDICATED" if possible == 0 and not_verified == 0 else "PARTIALLY_ADJUDICATED",
        "record_count": len(normalized),
        "benchmark_positive_count": len(positives),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "possible": possible,
        "not_verified": not_verified,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "f1": round(f1, 6) if f1 is not None else None,
        "verification_success_rate": round(verification_success_rate, 6) if verification_success_rate is not None else None,
        "bounty_ready_count": sum(1 for item in normalized if item["submission_ready"] and item["status"] == "TRUE_POSITIVE"),
    }

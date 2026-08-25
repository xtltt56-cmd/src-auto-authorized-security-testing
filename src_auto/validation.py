"""Post-scan validation and conservative Ground Truth comparison helpers."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


ALLOWED_STATUSES = frozenset({"TRUE_POSITIVE", "FALSE_POSITIVE", "POSSIBLE", "NOT_VERIFIED"})
GROUND_TRUTH_FIELDS = (
    "challenge_id",
    "challenge_name",
    "category",
    "difficulty",
    "expected_vulnerability_type",
    "scanner_detectable",
    "requires_business_logic",
    "requires_authentication",
    "notes",
)


def _scalar(value: str) -> Any:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(text)
    except ValueError:
        return text


def _challenge_from_record(record: Mapping[str, Any], tags: Sequence[str]) -> Dict[str, Any]:
    name = str(record.get("name", "")).strip()
    key = str(record.get("key", "")).strip()
    category = str(record.get("category", "Unknown")).strip() or "Unknown"
    tag_text = " ".join(tags).lower()
    lower_name = name.lower()
    lower_category = category.lower()
    manual_categories = {
        "broken access control",
        "broken authentication",
        "broken anti automation",
        "miscellaneous",
        "security through obscurity",
        "observability failures",
    }
    business_logic = (
        lower_category in manual_categories
        or "business" in lower_category
        or "business" in tag_text
        or "business" in lower_name
    )
    authentication = lower_category in {
        "broken access control",
        "broken authentication",
        "broken anti automation",
    } or any(
        marker in (tag_text + " " + lower_name)
        for marker in ("auth", "login", "admin", "authenticated", "logged-in")
    )
    detectable_categories = {
        "security misconfiguration",
        "sensitive data exposure",
        "injection",
        "xss",
        "vulnerable components",
        "improper input validation",
        "broken access control",
        "api security",
        "xxe",
        "unvalidated redirects",
        "cross-site request forgery",
        "cryptographic issues",
    }
    scanner_detectable = (
        lower_category in detectable_categories
        and not business_logic
        and not authentication
        and "coding" not in tag_text
    )
    difficulty = record.get("difficulty", 0)
    try:
        difficulty = int(difficulty)
    except (TypeError, ValueError):
        difficulty = 0
    return {
        "challenge_id": key or name,
        "challenge_name": name or key,
        "category": category,
        "difficulty": difficulty,
        "expected_vulnerability_type": category,
        "scanner_detectable": bool(scanner_detectable),
        "requires_business_logic": bool(business_logic),
        "requires_authentication": bool(authentication),
        "notes": "Derived from official challenge metadata; scanner_detectable is conservative and requires post-scan evidence.",
    }


def generate_ground_truth_from_yaml(text: str) -> List[Dict[str, Any]]:
    """Extract challenge metadata from Juice Shop's simple static YAML format.

    The parser intentionally reads only top-level name/category/difficulty/key/tags
    fields. It does not read hints, descriptions, payloads, or solution material.
    """
    records: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    tags: List[str] = []
    in_tags = False

    def flush() -> None:
        nonlocal current, tags
        if current.get("name") or current.get("key"):
            records.append(_challenge_from_record(current, tags))
        current = {}
        tags = []

    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        inline_start = re.match(r"^-\s*(name|category|difficulty|key):\s*(.+?)\s*$", line)
        if inline_start:
            flush()
            in_tags = False
            current[inline_start.group(1)] = _scalar(inline_start.group(2))
            continue
        if re.match(r"^-\s*$", line):
            flush()
            in_tags = False
            continue
        match = re.match(r"^\s{2}(name|category|difficulty|key):\s*(.+?)\s*$", line)
        if match:
            current[match.group(1)] = _scalar(match.group(2))
            in_tags = False
            continue
        if re.match(r"^\s{2}tags:\s*$", line):
            in_tags = True
            continue
        if in_tags:
            tag_match = re.match(r"^\s{4}-\s*(.+?)\s*$", line)
            if tag_match:
                tags.append(str(_scalar(tag_match.group(1))))
                continue
            if line.strip():
                in_tags = False
    flush()
    return records


def validate_ground_truth(entries: Iterable[Mapping[str, Any]]) -> None:
    seen = set()
    for entry in entries:
        missing = [field for field in GROUND_TRUTH_FIELDS if field not in entry]
        if missing:
            raise ValueError("ground truth missing fields: " + ",".join(missing))
        challenge_id = str(entry["challenge_id"]).strip()
        if not challenge_id or challenge_id in seen:
            raise ValueError("ground truth challenge_id must be unique and non-empty")
        seen.add(challenge_id)
        try:
            difficulty = int(entry["difficulty"])
        except (TypeError, ValueError):
            raise ValueError("ground truth difficulty must be an integer")
        if difficulty < 0:
            raise ValueError("ground truth difficulty cannot be negative")
        for field in ("scanner_detectable", "requires_business_logic", "requires_authentication"):
            if not isinstance(entry[field], bool):
                raise ValueError("ground truth {} must be boolean".format(field))


def normalize_finding(finding: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        confidence = float(finding.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if not math.isfinite(confidence):
        confidence = 0.0
    status = str(finding.get("status", "NOT_VERIFIED")).strip().upper() or "NOT_VERIFIED"
    if status not in ALLOWED_STATUSES:
        raise ValueError("invalid validation status")
    return {
        "title": str(finding.get("title", "")).strip()[:300],
        "category": str(finding.get("category", "")).strip()[:120],
        "endpoint": str(finding.get("endpoint", finding.get("url", ""))).strip()[:800],
        "parameter": str(finding.get("parameter", "")).strip()[:200],
        "method": str(finding.get("method", "GET")).strip().upper()[:12],
        "severity": str(finding.get("severity", "info")).strip().lower()[:40],
        "confidence": max(0.0, min(1.0, confidence)),
        "evidence": str(finding.get("evidence", "")).strip()[:1600],
        "scanner": str(finding.get("scanner", "unknown")).strip()[:80],
        "ai_analysis": str(finding.get("ai_analysis", "")).strip()[:800],
        "ground_truth_match": str(finding.get("ground_truth_match", "")).strip(),
        "status": status,
    }


def _tokens(value: str) -> set:
    return {token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(token) > 2}


def _best_match(finding: Mapping[str, Any], ground_truth: Sequence[Mapping[str, Any]]) -> str:
    explicit = str(finding.get("ground_truth_match", "")).strip()
    ids = {str(entry["challenge_id"]) for entry in ground_truth}
    if explicit in ids:
        return explicit
    finding_tokens = _tokens(
        " ".join(
            [
                str(finding.get("title", "")),
                str(finding.get("category", "")),
                str(finding.get("evidence", "")),
            ]
        )
    )
    best_id = ""
    best_score = 0.0
    for entry in ground_truth:
        expected_tokens = _tokens(
            " ".join(
                [
                    str(entry.get("challenge_name", "")),
                    str(entry.get("category", "")),
                    str(entry.get("expected_vulnerability_type", "")),
                ]
            )
        )
        if not expected_tokens:
            continue
        score = len(finding_tokens & expected_tokens) / float(len(expected_tokens))
        if score > best_score:
            best_score = score
            best_id = str(entry["challenge_id"])
    return best_id if best_score >= 0.5 else ""


def compare_findings(
    findings: Iterable[Mapping[str, Any]], ground_truth: Iterable[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    truth = [dict(entry) for entry in ground_truth]
    validate_ground_truth(truth)
    compared = []
    for raw in findings:
        item = normalize_finding(raw)
        item["ground_truth_match"] = _best_match(item, truth)
        compared.append(item)
    return compared


def metrics_for(findings: Iterable[Mapping[str, Any]], ground_truth: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    truth = [dict(entry) for entry in ground_truth]
    validate_ground_truth(truth)
    normalized = [normalize_finding(item) for item in findings]
    detectable_ids = {str(entry["challenge_id"]) for entry in truth if entry["scanner_detectable"]}
    true_positive_ids = {
        str(item.get("ground_truth_match"))
        for item in normalized
        if item["status"] == "TRUE_POSITIVE" and str(item.get("ground_truth_match", ""))
    }
    true_positive = len(true_positive_ids & {str(entry["challenge_id"]) for entry in truth})
    false_positive = sum(1 for item in normalized if item["status"] == "FALSE_POSITIVE")
    false_negative = len(detectable_ids - true_positive_ids)
    precision_denominator = true_positive + false_positive
    precision = true_positive / float(precision_denominator) if precision_denominator else 0.0
    recall = true_positive / float(len(truth)) if truth else 0.0
    scanner_recall = true_positive / float(len(detectable_ids)) if detectable_ids else 0.0
    f1_denominator = precision + recall
    f1 = (2.0 * precision * recall / f1_denominator) if f1_denominator else 0.0
    return {
        "ground_truth_count": len(truth),
        "scanner_detectable_count": len(detectable_ids),
        "finding_count": len(normalized),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "possible": sum(1 for item in normalized if item["status"] == "POSSIBLE"),
        "not_verified": sum(1 for item in normalized if item["status"] == "NOT_VERIFIED"),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "scanner_detectable_recall": round(scanner_recall, 6),
    }


def ground_truth_document(source_text: str, source_url: str) -> Dict[str, Any]:
    entries = generate_ground_truth_from_yaml(source_text)
    validate_ground_truth(entries)
    return {
        "source_url": str(source_url),
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "entry_count": len(entries),
        "entries": entries,
    }


def write_ground_truth(path: Path, source_text: str, source_url: str) -> Path:
    document = ground_truth_document(source_text, source_url)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

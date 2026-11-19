"""Ingest parsed scanner candidates into the Finding store with minimal evidence.

This is the missing last mile between "a tool ran" and "a candidate exists":
parsed scanner alerts become deduplicated, scope-checked Finding rows, each with
a minimal evidence pack. Candidates stay ``candidate`` until a human confirms;
nothing here submits to 补天 or contacts a target.
"""
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .reporting import EvidencePackager
from .scope import ScopeGuard
from .store import Store


def _vuln_type(title: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(title or "").lower()).strip("-")
    return slug[:80] or "zap-alert"


def _ingest_candidates(
    store: Store,
    root: Path,
    run_id: str,
    scope_guard: ScopeGuard,
    candidates: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Shared last mile: scope re-check, insert_candidate, minimal evidence."""
    packager = EvidencePackager(Path(root), store)
    inserted = 0
    merged = 0
    skipped = 0
    fingerprints: List[str] = []
    for candidate in candidates:
        url = str(candidate.get("url", ""))
        decision = scope_guard.decide(url, method=str(candidate.get("method", "GET")))
        if not decision.allowed:
            skipped += 1
            store.record_event(run_id, "warning", "finding_out_of_scope", {"url": url, "reason": decision.reason})
            continue
        item = dict(candidate)
        item["run_id"] = run_id
        result = store.insert_candidate(item)
        if result.inserted:
            inserted += 1
            packager.package(
                run_id,
                {
                    "fingerprint": result.fingerprint,
                    "title": item.get("title", ""),
                    "url": url,
                    "severity": item.get("severity", "info"),
                    "evidence": item.get("evidence", ""),
                },
            )
        else:
            merged += 1
        fingerprints.append(result.fingerprint)
    return {
        "status": "completed_ingest",
        "inserted": inserted,
        "merged": merged,
        "skipped_out_of_scope": skipped,
        "finding_count": len(store.list_findings(run_id)),
        "fingerprints": sorted(set(fingerprints)),
    }


def ingest_zap_candidates(
    store: Store,
    root: Path,
    run_id: str,
    scope_guard: ScopeGuard,
    parsed: Mapping[str, Any],
    scanner_version: str = "",
) -> Dict[str, Any]:
    """Persist ``parse_zap_report`` output as candidates + minimal evidence.

    ``parse_zap_report`` already filters by the runtime policy; ScopeGuard is
    re-applied here because it is the authoritative authorization gate.
    Out-of-scope endpoints are dropped and audited, never stored.
    """
    candidates = []
    for item in parsed.get("findings", []):
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("endpoint", ""))
        candidates.append(
            {
                "title": str(item.get("title", ""))[:300],
                "url": url,
                "parameter": str(item.get("parameter", "")),
                "method": str(item.get("method", "GET")),
                "severity": str(item.get("severity", "info")),
                "evidence": str(item.get("evidence", ""))[:1600],
                "vuln_type": _vuln_type(item.get("title")),
                "scanner": "zap",
                "template_id": str(item.get("scanner_alert_id", "")),
                "matched_at": url,
                "confidence": float(item.get("confidence", 0.3) or 0.3),
                "status": "candidate",
                "triage": {
                    "confirmed": False,
                    "submission_ready": False,
                    "source": "zap-quick-scan",
                    "scanner_version": str(scanner_version),
                },
            }
        )
    return _ingest_candidates(store, root, run_id, scope_guard, candidates)


def ingest_nuclei_candidates(
    store: Store,
    root: Path,
    run_id: str,
    scope_guard: ScopeGuard,
    items: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Persist ``parse_nuclei_candidates`` output through the same last mile."""
    return _ingest_candidates(store, root, run_id, scope_guard, items)
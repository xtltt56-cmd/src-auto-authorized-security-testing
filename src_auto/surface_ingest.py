"""L2: parse httpx/katana/nuclei tool output and ingest assets + candidates.

Closes the "recon results evaporate" gap: httpx/katana output becomes bounded
asset snapshots (attack_surface framework), nuclei JSONL becomes deduplicated
Finding candidates via the L1 insert_candidate lane. Out-of-scope items are
dropped and audited; failed tools and parser-less tools are never ingested.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping
from urllib.parse import urlsplit

from .attack_surface import save_asset_snapshot
from .finding_ingest import ingest_nuclei_candidates
from .models import ToolResult
from .redaction import redact_tool_output
from .scope import ScopeGuard
from .store import Store

_SEVERITIES = {"info", "low", "medium", "high", "critical"}


def _json_lines(text: str):
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            yield value


def parse_httpx_assets(text: str) -> List[Dict[str, Any]]:
    assets = []
    for row in _json_lines(text):
        url = str(row.get("url", "")).strip()
        host = str(row.get("host", "")).strip()
        if not url or not host:
            continue
        port = row.get("port")
        try:
            port = int(port) if port not in (None, "") else None
        except (TypeError, ValueError):
            port = None
        asset = {"url": url, "host": host, "port": port, "kind": "web", "metadata": {}}
        metadata = asset["metadata"]
        if row.get("title"):
            metadata["title"] = str(row["title"])[:200]
        if row.get("status_code") is not None:
            metadata["status_code"] = row["status_code"]
        if row.get("webserver"):
            metadata["server"] = str(row["webserver"])[:120]
        if row.get("tech"):
            metadata["technology"] = row["tech"] if isinstance(row["tech"], list) else str(row["tech"])
        assets.append(asset)
    return assets


def parse_katana_assets(text: str) -> List[Dict[str, Any]]:
    assets = []
    seen = set()
    for row in _json_lines(text):
        request = row.get("request") if isinstance(row.get("request"), dict) else row
        url = str(request.get("endpoint") or request.get("url") or "").strip()
        if not url or url in seen:
            continue
        try:
            parsed = urlsplit(url)
            if not parsed.hostname:
                continue
            port = parsed.port
        except ValueError:
            continue
        seen.add(url)
        assets.append({"url": url, "host": parsed.hostname, "port": port, "kind": "endpoint", "metadata": {}})
    return assets


def parse_nuclei_candidates(text: str) -> List[Dict[str, Any]]:
    items = []
    for row in _json_lines(text):
        template_id = str(row.get("template-id") or row.get("templateID") or "").strip().lower()
        matched_at = str(row.get("matched-at") or row.get("host") or "").strip()
        if not template_id or not matched_at:
            continue
        info = row.get("info") if isinstance(row.get("info"), dict) else {}
        severity = str(info.get("severity", "info")).lower()
        if severity not in _SEVERITIES:
            severity = "info"
        classification = info.get("classification") if isinstance(info.get("classification"), dict) else {}
        cwe_ids = classification.get("cwe-id") or []
        matcher = str(row.get("matcher-name") or "")
        items.append(
            {
                "title": str(info.get("name") or template_id)[:300],
                "url": matched_at,
                # matcher-name is a matcher, not an injection parameter; keeping
                # it out of the fingerprint lets ZAP/nuclei merge the same hole.
                "parameter": "",
                "severity": severity,
                "evidence": redact_tool_output("{} {} at {}".format(template_id, matcher, matched_at), 1600),
                "vuln_type": template_id[:80],
                "scanner": "nuclei",
                "template_id": template_id,
                "matched_at": matched_at,
                "confidence": 0.6,
                "cwe": str(cwe_ids[0]) if cwe_ids else "",
                "status": "candidate",
                "triage": {"confirmed": False, "submission_ready": False, "source": "nuclei-jsonl"},
            }
        )
    return items


def _empty(tool: str, reason: str) -> Dict[str, Any]:
    return {"tool": tool, "ingested": False, "reason": reason, "assets": 0, "inserted": 0, "merged": 0, "skipped_out_of_scope": 0}


def ingest_tool_output(
    store: Store,
    root: Path,
    run_id: str,
    scope_guard: ScopeGuard,
    tool: str,
    result: Any,
) -> Dict[str, Any]:
    """Ingest one completed tool's stdout. Never raises on parser-less tools."""
    data = result if isinstance(result, Mapping) else getattr(result, "__dict__", {})
    if data.get("status") != "completed":
        return _empty(tool, "tool_not_completed")
    stdout = str(data.get("stdout", ""))
    if tool in ("httpx", "katana"):
        parsed = parse_httpx_assets(stdout) if tool == "httpx" else parse_katana_assets(stdout)
        allowed = []
        skipped = 0
        for asset in parsed:
            decision = scope_guard.decide(asset["url"])
            if decision.allowed:
                allowed.append(asset)
            else:
                skipped += 1
                store.record_event(run_id, "warning", "asset_out_of_scope", {"tool": tool, "url": asset["url"], "reason": decision.reason})
        if allowed:
            save_asset_snapshot(store, run_id, allowed)
        return {"tool": tool, "ingested": bool(allowed), "reason": "assets_ingested", "assets": len(allowed),
                "inserted": 0, "merged": 0, "skipped_out_of_scope": skipped}
    if tool == "nuclei":
        items = parse_nuclei_candidates(stdout)
        summary = ingest_nuclei_candidates(store, root, run_id, scope_guard, items)
        return {"tool": tool, "ingested": bool(items), "reason": "candidates_ingested", "assets": 0,
                "inserted": summary["inserted"], "merged": summary["merged"],
                "skipped_out_of_scope": summary["skipped_out_of_scope"]}
    return _empty(tool, "no_parser")

"""Bounded, read-only validation helpers for an operator-started local Juice Shop.

This module deliberately does not start Docker, expand links to other hosts, or
send any request outside the exact runtime allowlist.  It is a small preflight
and discovery runner which can be used after the operator starts the local
container.  Vulnerability confirmation and Butian submission remain manual.
"""

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .adapters import SafeToolAdapter, ToolRegistry
from .i18n import with_zh_fields
from .runtime_policy import RuntimePolicy
from .scope import ScopeGuard


DEFAULT_JUICE_SHOP_URL = "http://127.0.0.1:3000/"
DEFAULT_SAFE_TOOLS = ("httpx", "katana")
MAX_RESPONSE_BYTES = 256 * 1024
MAX_TOOL_OUTPUT_BYTES = 64 * 1024


class LocalTargetError(PermissionError):
    """A local validation request was denied before or after network contact."""

    def __init__(self, reason: str, url: str = "", detail: str = ""):
        self.reason = str(reason)
        self.url = str(url)
        self.detail = str(detail)
        message = self.reason
        if self.url:
            message += " for " + self.url
        if self.detail:
            message += ": " + self.detail
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    """Do not let urllib follow a redirect before the destination is checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise LocalTargetError("redirect_requires_explicit_check", req.full_url, str(newurl))


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        if self.in_title and len("".join(self.parts)) < 300:
            self.parts.append(str(data))

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()[:300]


def _safe_urlopen(request: Request, timeout: int):
    opener = build_opener(_NoRedirect)
    return opener.open(request, timeout=timeout)


def _header_value(headers: Any, name: str) -> str:
    try:
        value = headers.get(name, "")
    except AttributeError:
        return ""
    return str(value or "")[:500]


def _response_metadata(response: Any, requested_url: str) -> Dict[str, Any]:
    final_url = str(response.geturl() if hasattr(response, "geturl") else requested_url)
    status = getattr(response, "status", None)
    if status is None:
        status = getattr(response, "code", 0)
    try:
        status = int(status or 0)
    except (TypeError, ValueError):
        status = 0
    try:
        body = response.read(MAX_RESPONSE_BYTES)
    except (OSError, TypeError, ValueError):
        body = b""
    if isinstance(body, str):
        body_bytes = body.encode("utf-8", errors="replace")
    else:
        body_bytes = bytes(body or b"")
    parser = _TitleParser()
    try:
        parser.feed(body_bytes.decode("utf-8", errors="replace"))
    except (ValueError, TypeError):
        pass
    return {
        "status": "reachable",
        "url": requested_url,
        "final_url": final_url,
        "redirected": final_url.rstrip("/") != requested_url.rstrip("/"),
        "http_status": status,
        "reason": str(getattr(response, "reason", "") or "")[:120],
        "content_type": _header_value(getattr(response, "headers", {}), "Content-Type"),
        "content_length": len(body_bytes),
        "title": parser.title,
        "headers": {
            "content-security-policy": _header_value(getattr(response, "headers", {}), "Content-Security-Policy"),
            "strict-transport-security": _header_value(getattr(response, "headers", {}), "Strict-Transport-Security"),
            "x-content-type-options": _header_value(getattr(response, "headers", {}), "X-Content-Type-Options"),
            "x-frame-options": _header_value(getattr(response, "headers", {}), "X-Frame-Options"),
        },
        "network_contact": True,
    }


def probe_local_target(
    policy: RuntimePolicy,
    url: str = DEFAULT_JUICE_SHOP_URL,
    urlopen_fn: Optional[Callable[..., Any]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Perform one bounded GET and return metadata without storing the body."""

    allowed, reason = policy.decide_url(url)
    if not allowed:
        raise LocalTargetError(reason, url)
    try:
        request = Request(
            str(url),
            method="GET",
            headers={
                "User-Agent": "SRC-Auto/juice-shop-local-validation",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
                "Accept-Encoding": "identity",
            },
        )
    except (TypeError, ValueError):
        raise LocalTargetError("invalid_url", str(url))
    opener = urlopen_fn or _safe_urlopen
    try:
        response = opener(request, timeout=timeout)
        try:
            result = _response_metadata(response, str(url))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except LocalTargetError:
        raise
    except HTTPError as exc:
        # HTTP errors still prove that the local service is reachable.  The
        # response body is intentionally not retained.
        result = {
            "status": "reachable",
            "url": str(url),
            "final_url": str(url),
            "redirected": False,
            "http_status": int(getattr(exc, "code", 0) or 0),
            "reason": str(getattr(exc, "reason", "") or "")[:120],
            "content_type": _header_value(getattr(exc, "headers", {}), "Content-Type"),
            "content_length": 0,
            "title": "",
            "headers": {},
            "network_contact": True,
        }
    except (OSError, URLError, TimeoutError) as exc:
        return {
            "status": "unreachable",
            "url": str(url),
            "final_url": str(url),
            "redirected": False,
            "http_status": 0,
            "reason": "connection_failed",
            "error": str(exc)[:300],
            "network_contact": True,
        }

    final_url = result.get("final_url", str(url))
    final_allowed, final_reason = policy.decide_url(final_url)
    if not final_allowed:
        raise LocalTargetError("redirect_out_of_scope", str(url), final_reason)
    return result


def safe_scan_urls(
    policy: RuntimePolicy,
    urls: Iterable[str],
    urlopen_fn: Optional[Callable[..., Any]] = None,
    timeout: int = 10,
    concurrency: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Probe an already enumerated URL list with strict preflight and a cap of five workers."""

    values = [str(url).strip() for url in urls if str(url).strip()]
    for url in values:
        allowed, reason = policy.decide_url(url)
        if not allowed:
            raise LocalTargetError(reason, url)
    requested = policy.max_concurrency if concurrency is None else int(concurrency)
    workers = max(1, min(policy.max_concurrency, requested))
    if workers == 1 or len(values) <= 1:
        return [probe_local_target(policy, url, urlopen_fn=urlopen_fn, timeout=timeout) for url in values]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(probe_local_target, policy, url, urlopen_fn, timeout)
            for url in values
        ]
        return [future.result() for future in futures]


def _redact_tool_output(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)(authorization|cookie|set-cookie|x-api-key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
    return text[:MAX_TOOL_OUTPUT_BYTES]


def _tool_result_dict(result: Any) -> Dict[str, Any]:
    value = getattr(result, "__dict__", result)
    if not isinstance(value, Mapping):
        return {"status": "error", "detail": "invalid_tool_result"}
    return {
        "status": str(value.get("status", "unknown")),
        "returncode": value.get("returncode"),
        "detail": _redact_tool_output(value.get("detail", "")),
        "stdout": _redact_tool_output(value.get("stdout", "")),
        "stderr": _redact_tool_output(value.get("stderr", "")),
    }


def run_discovery_tools(
    root: Path,
    scope_guard: ScopeGuard,
    target_url: str,
    registry: Optional[ToolRegistry] = None,
    sequence: Sequence[str] = DEFAULT_SAFE_TOOLS,
    timeout: int = 120,
) -> List[Dict[str, Any]]:
    """Run only passive/surface discovery tools with fixed bounded arguments."""

    registry = registry or ToolRegistry(search_paths=[Path(root) / "vendor" / "bin"])
    adapters = {name: SafeToolAdapter(name, registry) for name in sequence}
    arguments = {
        "httpx": ["-silent", "-no-color", "-u", target_url],
        "katana": ["-silent", "-no-color", "-u", target_url, "-d", "2", "-jc", "false"],
    }
    results = []
    for name in sequence:
        adapter = adapters[name]
        if not registry.command_for(name):
            results.append({"tool": name, "result": {"status": "unavailable", "detail": "binary_not_found"}})
            continue
        result = adapter.run(arguments.get(name, ["-silent", "-u", target_url]), scope_guard, [target_url], timeout=timeout, cwd=Path(root))
        results.append({"tool": name, "result": _tool_result_dict(result)})
    return results


def baseline_document(
    path: Path,
    status: str,
    reason: str,
    target_url: str,
    probe: Mapping[str, Any],
    tools: Iterable[Mapping[str, Any]],
    findings: Iterable[Mapping[str, Any]],
    metrics: Optional[Mapping[str, Any]],
    environment: Optional[Mapping[str, Any]] = None,
    scan_metadata: Optional[Mapping[str, Any]] = None,
) -> Path:
    """Write a bounded JSON baseline artifact; never silently converts a blocker to a pass."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = with_zh_fields({
        "status": str(status),
        "reason": str(reason),
        "target_url": str(target_url),
        "network_contact": bool(probe.get("network_contact", False)),
        "probe": dict(probe),
        "tools": [dict(item) for item in tools],
        "findings": [dict(item) for item in findings],
        "metrics": dict(metrics) if metrics is not None else None,
        "environment": dict(environment or {}),
        "scan_metadata": dict(scan_metadata or {}),
    })
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validation_metrics_document(
    status: str,
    reason: str,
    target_url: str,
    ground_truth_count: int,
    scanner_detectable_count: int,
    notes: str,
    scan_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return an explicit metrics placeholder until an adjudicated scan exists."""

    return with_zh_fields({
        "status": str(status),
        "reason": str(reason),
        "target": str(target_url),
        "ground_truth_count": int(ground_truth_count),
        "scanner_detectable_count": int(scanner_detectable_count),
        "true_positive": None,
        "false_positive": None,
        "false_negative": None,
        "precision": None,
        "recall": None,
        "f1": None,
        "scanner_detectable_recall": None,
        "remote_ai_calls": 0,
        "remote_ai_cost_usd": 0.0,
        "local_model_calls": 0,
        "scan_metadata": dict(scan_metadata or {}),
        "notes": str(notes),
    })


def write_validation_metrics(path: Path, document: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def local_dependency_status(extra_paths: Optional[Iterable[Path]] = None) -> Dict[str, Any]:
    """Return non-invasive local dependency information without starting anything."""

    docker = shutil.which("docker")
    if docker:
        return {
            "docker_available_on_path": True,
            "docker_command": docker,
            "docker_source": "path",
        }
    explicit = [Path(item) for item in (extra_paths or [])]
    for candidate in explicit:
        if candidate.is_file():
            return {
                "docker_available_on_path": True,
                "docker_command": str(candidate),
                "docker_source": "explicit_candidate",
            }
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe")
    candidates.extend(
        [
            Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return {
                "docker_available_on_path": True,
                "docker_command": str(candidate),
                "docker_source": "known_location",
            }
    return {
        "docker_available_on_path": False,
        "docker_command": "",
        "docker_source": "unavailable",
    }


def summarize_discovery_tools(
    policy: RuntimePolicy,
    tools: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Extract URLs from tool output without contacting any extracted URL.

    Tool output can contain links to documentation, media, or third-party
    services embedded in the local application's JavaScript.  The summary
    keeps only exact allowlisted URLs as candidates and records everything
    else as excluded evidence.  This function is intentionally parse-only.
    """

    url_pattern = re.compile(r"https?://[^\s<>\"']+")
    discovered = set()
    excluded = set()
    tool_names = []
    for item in tools:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("tool", "")).strip()
        if name:
            tool_names.append(name)
        result = item.get("result", {})
        if not isinstance(result, Mapping):
            continue
        text = "\n".join([str(result.get("stdout", "") or ""), str(result.get("stderr", "") or "")])
        for raw_url in url_pattern.findall(text):
            url = raw_url.rstrip(".,;:)]}")
            allowed, _reason = policy.decide_url(url)
            if allowed:
                discovered.add(url)
            else:
                excluded.add(url)
    return {
        "discovered_urls": sorted(discovered),
        "external_urls_excluded": sorted(excluded),
        "discovered_url_count": len(discovered),
        "external_excluded_count": len(excluded),
        "tools_run": sorted(set(tool_names)),
    }


def parse_zap_report(report: Mapping[str, Any], policy: RuntimePolicy) -> Dict[str, Any]:
    """Convert a ZAP JSON report into bounded, unverified local findings.

    ZAP may include links discovered in scripts or response bodies.  Only
    alert instances whose URI passes the exact runtime policy are retained;
    all other URIs are reported as excluded and are never requested here.
    Findings are deliberately marked ``POSSIBLE`` until a human or a separate
    safe verifier adjudicates them.
    """

    risk_severity = {"3": "high", "2": "medium", "1": "low", "0": "info"}
    confidence = {"3": 0.9, "2": 0.7, "1": 0.5, "0": 0.3}
    sites = report.get("site", []) if isinstance(report, Mapping) else []
    if isinstance(sites, Mapping):
        sites = [sites]
    findings: List[Dict[str, Any]] = []
    excluded = set()
    alert_count = 0
    for site in sites if isinstance(sites, list) else []:
        if not isinstance(site, Mapping):
            continue
        site_name = str(site.get("@name", "")).strip()
        site_allowed, _site_reason = policy.decide_url(site_name) if site_name else (False, "missing_site")
        if not site_allowed and site_name:
            excluded.add(site_name)
        alerts = site.get("alerts", [])
        if isinstance(alerts, Mapping):
            alerts = [alerts]
        for alert in alerts if isinstance(alerts, list) else []:
            if not isinstance(alert, Mapping):
                continue
            alert_count += 1
            instances = alert.get("instances", [])
            if isinstance(instances, Mapping):
                instances = [instances]
            selected = None
            for instance in instances if isinstance(instances, list) else []:
                if not isinstance(instance, Mapping):
                    continue
                uri = str(instance.get("uri", "")).strip()
                allowed, _reason = policy.decide_url(uri)
                if not allowed:
                    if uri:
                        excluded.add(uri)
                    continue
                if selected is None:
                    selected = instance
            if selected is None:
                continue
            risk_code = str(alert.get("riskcode", "0"))
            confidence_code = str(alert.get("confidence", "0"))
            evidence = str(selected.get("evidence", "") or alert.get("otherinfo", ""))[:1600]
            findings.append(
                {
                    "title": str(alert.get("name", alert.get("alert", "ZAP alert")))[:300],
                    "category": "ZAP passive/active alert",
                    "endpoint": str(selected.get("uri", ""))[:800],
                    "parameter": str(selected.get("param", ""))[:200],
                    "method": str(selected.get("method", "GET")).upper()[:12],
                    "severity": risk_severity.get(risk_code, "info"),
                    "confidence": confidence.get(confidence_code, 0.3),
                    "evidence": evidence,
                    "scanner": "zap",
                    "ai_analysis": "",
                    "ground_truth_match": "",
                    "status": "POSSIBLE",
                    "scanner_alert_id": str(alert.get("pluginid", ""))[:80],
                    "scanner_instance_count": len(instances) if isinstance(instances, list) else 0,
                }
            )
    return {
        "findings": findings,
        "finding_count": len(findings),
        "alert_count": alert_count,
        "external_urls_excluded": sorted(excluded),
        "external_excluded_count": len(excluded),
    }


def run_zap_quick_scan(
    root: Path,
    target_url: str,
    output_path: Path,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Run ZAP's bounded quick scan with telemetry disabled.

    The caller must perform runtime and scope validation before invoking this
    function.  The command is fixed to the project-pinned JAR and a single
    target URL; it does not accept arbitrary extra arguments or follow-up
    commands.
    """

    root = Path(root).resolve()
    output_path = Path(output_path).resolve()
    try:
        output_path.relative_to(root)
    except ValueError:
        return {"status": "blocked_output", "detail": "output_outside_project_root"}
    jar = root / "vendor" / "zap" / "ZAP_2.17.0" / "zap-2.17.0.jar"
    if not jar.is_file():
        return {"status": "unavailable", "detail": "zap_jar_not_found", "report_path": str(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    zap_dir = output_path.parent / ".zap-work"
    zap_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "java",
        "-jar",
        str(jar),
        "-dir",
        str(zap_dir),
        "-cmd",
        "-notel",
        "-quickurl",
        str(target_url),
        "-quickout",
        str(output_path),
        "-quickprogress",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(jar.parent),
            capture_output=True,
            text=True,
            timeout=int(timeout),
            check=False,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "detail": "java_not_found", "report_path": str(output_path)}
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "detail": "zap_timeout",
            "returncode": None,
            "stdout": str(exc.stdout or "")[-16000:],
            "stderr": str(exc.stderr or "")[-16000:],
            "report_path": str(output_path),
        }
    return {
        "status": "completed" if completed.returncode == 0 else "error",
        "detail": "",
        "returncode": completed.returncode,
        "stdout": str(completed.stdout or "")[-16000:],
        "stderr": str(completed.stderr or "")[-16000:],
        "report_path": str(output_path),
    }

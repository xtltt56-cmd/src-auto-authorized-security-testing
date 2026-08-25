"""Bounded OpenAPI contract smoke checks for project-owned loopback labs."""

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit


class ApiSchemaError(ValueError):
    pass


_LOOPBACK = {"127.0.0.1", "localhost"}


def _project_path(project_root: Path, value: Path) -> Path:
    root = Path(project_root).resolve()
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ApiSchemaError("output_outside_project") from exc
    return candidate


def build_local_schema_smoke_command(project_root: Path, schema_url: str, output_dir: Path) -> List[str]:
    parsed = urlsplit(str(schema_url))
    if parsed.scheme != "http" or (parsed.hostname or "").lower() not in _LOOPBACK:
        raise ApiSchemaError("schema_url_must_be_loopback")
    if parsed.username or parsed.password or not parsed.path.endswith("openapi.json"):
        raise ApiSchemaError("schema_url_invalid")
    safe_output = _project_path(project_root, output_dir)
    wrapper = _project_path(project_root, Path(project_root) / "vendor" / "bin" / "schemathesis.cmd")
    return [
        str(wrapper),
        "run",
        str(schema_url),
        "--include-method",
        "GET",
        "--phases",
        "examples",
        "--workers",
        "1",
        "--max-examples",
        "1",
        "--max-failures",
        "3",
        "--rate-limit",
        "20/m",
        "--request-timeout",
        "3",
        "--request-retries",
        "0",
        "--max-redirects",
        "0",
        "--output-sanitize",
        "true",
        "--output-truncate",
        "true",
        "--generation-deterministic",
        "--report",
        "junit",
        "--report-junit-path",
        str(safe_output / "schemathesis.junit.xml"),
        "--no-color",
    ]


def classify_schema_smoke_result(returncode: int, report_exists: bool) -> Dict[str, Any]:
    if report_exists and int(returncode) == 0:
        status = "COMPLETED"
        reason = "schema_examples_conform"
        manual = False
    elif report_exists and int(returncode) == 1:
        status = "POSSIBLE_SCHEMA_CONTRACT_ISSUES"
        reason = "schema_examples_reported_candidates"
        manual = True
    else:
        status = "FAILED_RUNTIME"
        reason = "schema_report_not_created"
        manual = True
    return {
        "status": status,
        "reason": reason,
        "returncode": int(returncode),
        "report_created": bool(report_exists),
        "confirmed": False,
        "manual_review_required": manual,
        "network_contact": True,
        "request_profile": "loopback_get_examples_only",
    }


def run_local_schema_smoke(project_root: Path, schema_url: str, output_dir: Path, timeout: int = 90) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    safe_output = _project_path(root, output_dir)
    safe_output.mkdir(parents=True, exist_ok=True)
    command = build_local_schema_smoke_command(root, schema_url, safe_output)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["TERM"] = "dumb"
    wrapper = command[0]
    invocation = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", wrapper] + command[1:]
    try:
        completed = subprocess.run(
            invocation,
            cwd=str(root),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(10, int(timeout)),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "FAILED_RUNTIME",
            "reason": "schema_command_failed",
            "detail": str(exc)[:300],
            "confirmed": False,
            "manual_review_required": True,
            "network_contact": False,
        }
    report = safe_output / "schemathesis.junit.xml"
    result = classify_schema_smoke_result(completed.returncode, report.is_file())
    result.update(
        {
            "schema_url": schema_url,
            "report_path": str(report) if report.is_file() else "",
            "command": ["schemathesis", "run", "loopback-openapi", "GET/examples"],
            "output_retained": "no_raw_scanner_output_in_summary",
        }
    )
    return result

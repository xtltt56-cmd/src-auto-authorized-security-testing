"""Fail-closed, non-destructive regression checks for the local OWASP labs.

The regression runner is deliberately narrower than a vulnerability scanner. It
proves that a lab is reachable, that an unauthenticated request is kept behind
the expected login boundary, and that a harmless marker reaches a deliberately
vulnerable local training page. It never follows redirects, executes a command,
uploads a file, changes a password, or submits a report.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

from .local_labs import LabSpec, LocalLabManager
from .runtime_policy import RuntimePolicy


MAX_CASES = 64
MAX_BODY = 512 * 1024
MAX_TEXT_ASSERTION = 160
MAX_QUERY_ITEMS = 12
MAX_ROUNDS = 3
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}
)
_ALLOWED_KINDS = frozenset(
    {"public-surface", "auth-boundary", "authenticated-surface", "safe-reflection"}
)
_ALLOWED_AUTH = frozenset({"none", "dvwa-default", "webgoat-synthetic"})
_EXPECTED_KEYS = frozenset(
    {
        "status_in",
        "body_contains",
        "body_not_contains",
        "location_contains",
        "location_not_contains",
        "body_size_min",
    }
)


class RegressionError(RuntimeError):
    """An expected local regression operation could not be completed."""


class RegressionScopeError(RegressionError):
    """A request or redirect would leave the local runtime policy."""


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    lab_id: str
    kind: str
    method: str
    path: str
    query: Mapping[str, str]
    auth: str
    expected: Mapping[str, Any]
    destructive: bool
    description: str


def _safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if not _ID_RE.fullmatch(text):
        raise ValueError("{}_invalid".format(field))
    return text


def safe_case_path(value: Any) -> str:
    """Return a relative HTTP path, rejecting absolute URLs and traversal."""

    path = str(value or "").strip()
    if not path or len(path) > 500 or any(ord(char) < 32 for char in path):
        raise ValueError("case_path_invalid")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("case_path_must_be_absolute_path")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ValueError("case_path_must_not_be_external_url")
    if "\\" in path:
        raise ValueError("case_path_backslash_forbidden")
    if any(part == ".." for part in parsed.path.split("/")):
        raise ValueError("case_path_traversal_forbidden")
    if not parsed.path.startswith("/"):
        raise ValueError("case_path_invalid")
    # Query parameters belong in the structured query mapping so that they can
    # be bounded and audited independently of the endpoint path.
    if parsed.query:
        raise ValueError("case_query_must_be_structured")
    return parsed.path


def _bounded_text_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise ValueError("{}_must_be_non_empty_list".format(field))
    result = []
    for item in value:
        text = str(item)
        if not text or len(text) > MAX_TEXT_ASSERTION or any(ord(char) < 32 for char in text):
            raise ValueError("{}_item_invalid".format(field))
        result.append(text)
    return result


def _validate_expected(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("expected_assertions_required")
    unknown = set(value) - _EXPECTED_KEYS
    if unknown:
        raise ValueError("unsupported_expectation")
    result: Dict[str, Any] = {}
    if "status_in" in value:
        statuses = value["status_in"]
        if not isinstance(statuses, list) or not statuses or len(statuses) > 10:
            raise ValueError("status_in_invalid")
        normalized = []
        for item in statuses:
            try:
                status = int(item)
            except (TypeError, ValueError):
                raise ValueError("status_in_invalid")
            if not 100 <= status <= 599:
                raise ValueError("status_in_invalid")
            normalized.append(status)
        result["status_in"] = normalized
    for field in ("body_contains", "body_not_contains", "location_contains", "location_not_contains"):
        if field in value:
            result[field] = _bounded_text_list(value[field], field)
    if "body_size_min" in value:
        try:
            size = int(value["body_size_min"])
        except (TypeError, ValueError):
            raise ValueError("body_size_min_invalid")
        if not 0 <= size <= MAX_BODY:
            raise ValueError("body_size_min_invalid")
        result["body_size_min"] = size
    if not result:
        raise ValueError("expected_assertions_required")
    return result


def _query_mapping(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or len(value) > MAX_QUERY_ITEMS:
        raise ValueError("case_query_invalid")
    result: Dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        item = str(raw_value)
        if not key or len(key) > 80 or len(item) > 300 or any(ord(char) < 32 for char in key + item):
            raise ValueError("case_query_item_invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", key):
            raise ValueError("case_query_key_invalid")
        result[key] = item
    return result


def load_regression_cases(path: Path) -> List[RegressionCase]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("regression_inventory_invalid: {}".format(exc))
    raw_cases = document.get("cases") if isinstance(document, Mapping) else None
    if not isinstance(raw_cases, list) or not raw_cases or len(raw_cases) > MAX_CASES:
        raise ValueError("regression_inventory_requires_bounded_cases")
    cases: List[RegressionCase] = []
    seen = set()
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            raise ValueError("regression_case_must_be_object")
        case_id = _safe_id(raw.get("case_id"), "case_id")
        if case_id in seen:
            raise ValueError("duplicate_case_id")
        lab_id = _safe_id(raw.get("lab_id"), "lab_id")
        kind = str(raw.get("kind", "")).strip().lower()
        if kind not in _ALLOWED_KINDS:
            raise ValueError("case_kind_invalid")
        method = str(raw.get("method", "GET")).strip().upper()
        if method not in {"GET", "POST"}:
            raise ValueError("case_method_invalid")
        path_value = safe_case_path(raw.get("path"))
        auth = str(raw.get("auth", "none")).strip().lower()
        if auth not in _ALLOWED_AUTH:
            raise ValueError("case_auth_invalid")
        destructive = raw.get("destructive", False)
        if destructive is not False:
            raise ValueError("destructive_cases_forbidden")
        description = str(raw.get("description", "")).strip()
        if len(description) > 500:
            raise ValueError("case_description_too_long")
        cases.append(
            RegressionCase(
                case_id=case_id,
                lab_id=lab_id,
                kind=kind,
                method=method,
                path=path_value,
                query=_query_mapping(raw.get("query")),
                auth=auth,
                expected=_validate_expected(raw.get("expected")),
                destructive=False,
                description=description,
            )
        )
        seen.add(case_id)
    return cases


def redact_regression_headers(headers: Mapping[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        if not name:
            continue
        result[name] = "<redacted>" if name in _SENSITIVE_HEADERS else str(raw_value or "")[:300]
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        # Returning None makes urllib expose the 3xx response to the caller.
        # The caller records the Location but never follows it automatically.
        return None


def _evidence_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return "<invalid-url>"
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return "<non-loopback-url>"
    port = parsed.port
    netloc = parsed.hostname or ""
    if port:
        netloc += ":{}".format(port)
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


def _evidence_location(requested_url: str, value: str) -> str:
    """Keep safe relative redirects readable without exposing external URLs."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "<invalid-location>"
    if not parsed.scheme and not parsed.netloc:
        return raw[:500]
    return _evidence_url(raw)


class LocalHTTPClient:
    """HTTP client with no redirects and a RuntimePolicy preflight."""

    def __init__(self, policy: RuntimePolicy, base_url: str, cookie_jar: Optional[CookieJar] = None):
        self.policy = policy
        self.base_url = str(base_url).rstrip("/") + "/"
        allowed, reason = policy.decide_url(self.base_url)
        if not allowed:
            raise RegressionScopeError("base_url_not_allowlisted: {}".format(reason))
        self.cookie_jar = cookie_jar or CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar), _NoRedirect())

    def request(
        self,
        path: str,
        method: str = "GET",
        query: Optional[Mapping[str, str]] = None,
        form: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        endpoint = safe_case_path(path)
        method = str(method or "GET").strip().upper()
        if method not in {"GET", "POST"}:
            raise ValueError("request_method_invalid")
        url = urljoin(self.base_url, endpoint)
        query = _query_mapping(query)
        if query:
            url += ("&" if "?" in url else "?") + urlencode(query)
        allowed, reason = self.policy.decide_url(url)
        if not allowed:
            raise RegressionScopeError("request_not_allowlisted: {}".format(reason))
        body = None
        headers = {
            "User-Agent": "SRC-Auto/local-regression",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
            "Accept-Encoding": "identity",
        }
        if form is not None:
            if method != "POST":
                raise ValueError("form_requires_post")
            safe_form = _query_mapping(form)
            body = urlencode(safe_form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=10)
            return self._read_response(url, response, 200)
        except HTTPError as exc:
            return self._read_response(url, exc, int(exc.code))
        except (URLError, OSError) as exc:
            raise RegressionError("local_request_failed: {}".format(str(exc)[:240]))

    def _read_response(self, requested_url: str, response: Any, status: int) -> Dict[str, Any]:
        try:
            raw_body = response.read(MAX_BODY + 1)
            headers = getattr(response, "headers", {}) or {}
            location = str(headers.get("Location", "") or "").strip()
        finally:
            try:
                response.close()
            except (AttributeError, OSError):
                pass
        if len(raw_body) > MAX_BODY:
            raw_body = raw_body[:MAX_BODY]
            truncated = True
        else:
            truncated = False
        if location:
            redirect_url = urljoin(requested_url, location)
            allowed, reason = self.policy.decide_url(redirect_url)
            if not allowed:
                return {
                    "status": status,
                    "body": "",
                    "body_length": len(raw_body),
                    "body_sha256": hashlib.sha256(raw_body).hexdigest(),
                    "location": _evidence_location(requested_url, location),
                    "headers": redact_regression_headers(headers),
                    "response_url": _evidence_url(requested_url),
                    "truncated": truncated,
                    "network_contact": True,
                    "blocked_reason": "redirect_not_allowlisted: {}".format(reason),
                }
        body_text = raw_body.decode("utf-8", errors="replace")
        return {
            "status": status,
            "body": body_text,
            "body_length": len(raw_body),
            "body_sha256": hashlib.sha256(raw_body).hexdigest(),
            "location": _evidence_location(requested_url, location) if location else "",
            "headers": redact_regression_headers(headers),
            "response_url": _evidence_url(requested_url),
            "truncated": truncated,
            "network_contact": True,
        }


def _assertion_items(expected: Mapping[str, Any]) -> Iterable[Tuple[str, Any]]:
    for key, value in expected.items():
        if isinstance(value, list):
            for item in value:
                yield key, item
        else:
            yield key, value


def evaluate_expectations(case: RegressionCase, response: Mapping[str, Any]) -> Dict[str, Any]:
    status_value = response.get("status")
    try:
        status_code = int(status_value)
    except (TypeError, ValueError):
        status_code = 0
    body = str(response.get("body", ""))
    location = str(response.get("location", ""))
    failed: List[str] = []
    blocked_reason = str(response.get("blocked_reason", ""))
    matched = 0
    total = sum(1 for _ in _assertion_items(case.expected))
    statuses = case.expected.get("status_in")
    if statuses is not None:
        if status_code in statuses:
            matched += 1
        else:
            failed.append("status_in")
    for field in ("body_contains", "body_not_contains", "location_contains", "location_not_contains"):
        values = case.expected.get(field, [])
        for needle in values:
            haystack = body if field.startswith("body") else location
            if field.endswith("contains") and not field.endswith("not_contains"):
                ok = str(needle) in haystack
            else:
                ok = str(needle) not in haystack
            if ok:
                matched += 1
            else:
                failed.append(field)
    if "body_size_min" in case.expected:
        minimum = int(case.expected["body_size_min"])
        if len(body.encode("utf-8")) >= minimum:
            matched += 1
        else:
            failed.append("body_size_min")
    result = {
        "case_id": case.case_id,
        "lab_id": case.lab_id,
        "kind": case.kind,
        "auth": case.auth,
        "status": "BLOCKED_SCOPE" if blocked_reason else ("PASS" if not failed else "FAIL"),
        "response_status": status_code,
        "response_length": int(response.get("body_length", len(body.encode("utf-8"))) or 0),
        "response_sha256": str(response.get("body_sha256", hashlib.sha256(body.encode("utf-8")).hexdigest())),
        "response_url": str(response.get("response_url", "")),
        "location": location,
        "headers": redact_regression_headers(response.get("headers", {}) if isinstance(response.get("headers"), Mapping) else {}),
        "matched_assertions": matched,
        "total_assertions": total,
        "failed_assertions": sorted(set(failed)),
        "network_contact": bool(response.get("network_contact", False)),
        "blocked_reason": blocked_reason,
        "truncated": bool(response.get("truncated", False)),
    }
    return result


def _hidden_value(body: str, name: str) -> str:
    pattern = re.compile(
        r"<input[^>]+name=[\"']{}[\"'][^>]+value=[\"']([^\"']+)[\"']".format(re.escape(name)),
        re.I,
    )
    match = pattern.search(body)
    if match:
        return match.group(1)
    reverse = re.compile(
        r"<input[^>]+value=[\"']([^\"']+)[\"'][^>]+name=[\"']{}[\"']".format(re.escape(name)),
        re.I,
    )
    match = reverse.search(body)
    return match.group(1) if match else ""


def _dvwa_login(policy: RuntimePolicy, base_url: str) -> Tuple[LocalHTTPClient, Dict[str, Any]]:
    client = LocalHTTPClient(policy, base_url)
    login_page = client.request("/login.php")
    token = _hidden_value(str(login_page.get("body", "")), "user_token")
    if not token:
        raise RegressionError("dvwa_login_token_missing")
    login = client.request(
        "/login.php",
        method="POST",
        form={"username": "admin", "password": "password", "Login": "Login", "user_token": token},
    )
    location = str(login.get("location", "")).lower()
    body = str(login.get("body", ""))
    if "setup.php" in location or "database setup" in body.lower():
        setup = client.request("/setup.php")
        setup_token = _hidden_value(str(setup.get("body", "")), "user_token")
        if not setup_token:
            raise RegressionError("dvwa_setup_token_missing")
        reset = client.request(
            "/setup.php",
            method="POST",
            form={"create_db": "Create / Reset Database", "user_token": setup_token},
        )
        reset_body = str(reset.get("body", ""))
        if "setup successful" not in reset_body.lower() and "database has been created" not in reset_body.lower():
            raise RegressionError("dvwa_setup_failed")
        login_page = client.request("/login.php")
        token = _hidden_value(str(login_page.get("body", "")), "user_token")
        login = client.request(
            "/login.php",
            method="POST",
            form={"username": "admin", "password": "password", "Login": "Login", "user_token": token},
        )
        location = str(login.get("location", "")).lower()
        body = str(login.get("body", ""))
    if "login.php" in location or "login failed" in body.lower() or not list(client.cookie_jar):
        # A successful DVWA login is normally a 302 to index.php and sets a
        # PHP session cookie. The cookie jar is intentionally never serialized.
        raise RegressionError("dvwa_login_failed")
    return client, {"status": "READY", "fixture": "dvwa-local-default", "network_contact": True}


def _webgoat_login(policy: RuntimePolicy, base_url: str) -> Tuple[LocalHTTPClient, Dict[str, Any]]:
    client = LocalHTTPClient(policy, base_url)
    register_page = client.request("/WebGoat/register.mvc")
    username = "codex-" + secrets.token_hex(4)
    password = "A1b2c3!"
    registered = client.request(
        "/WebGoat/register.mvc",
        method="POST",
        form={"username": username, "password": password, "matchingPassword": password, "agree": "agree"},
    )
    if int(registered.get("status", 0)) not in {200, 201, 302, 303}:
        raise RegressionError("webgoat_registration_failed")
    start = client.request("/WebGoat/start.mvc")
    if int(start.get("status", 0)) not in {200, 204}:
        raise RegressionError("webgoat_login_failed")
    return client, {"status": "READY", "fixture": "webgoat-synthetic-session", "network_contact": True}


def _base_url(spec: LabSpec) -> str:
    return "http://{}:{}/".format(spec.host, spec.host_port)


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"(?i)(password|token|cookie|authorization)\s*[:=]\s*[^ ]+", r"\1=<redacted>", text)
    return text[:300]


def _write_json(path: Path, value: Mapping[str, Any], project_root: Path) -> None:
    target = Path(path).resolve()
    try:
        target.relative_to(Path(project_root).resolve())
    except ValueError:
        raise ValueError("regression_artifact_outside_project")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str, project_root: Path) -> None:
    target = Path(path).resolve()
    try:
        target.relative_to(Path(project_root).resolve())
    except ValueError:
        raise ValueError("regression_artifact_outside_project")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(value), encoding="utf-8")


def _run_one_case(case: RegressionCase, manager: LocalLabManager, policy: RuntimePolicy) -> Dict[str, Any]:
    spec = manager.spec(case.lab_id)
    base_url = _base_url(spec)
    fixture: Dict[str, Any] = {"status": "NOT_REQUIRED", "fixture": "none", "network_contact": False}
    try:
        if case.auth == "dvwa-default":
            client, fixture = _dvwa_login(policy, base_url)
        elif case.auth == "webgoat-synthetic":
            client, fixture = _webgoat_login(policy, base_url)
        else:
            client = LocalHTTPClient(policy, base_url)
        response = client.request(case.path, method=case.method, query=case.query)
        result = evaluate_expectations(case, response)
        result["fixture"] = fixture.get("fixture", "none")
        result["fixture_status"] = fixture.get("status", "NOT_REQUIRED")
        result["fixture_network_contact"] = bool(fixture.get("network_contact", False))
        result["description"] = case.description
        result["path"] = case.path
        return result
    except (RegressionError, OSError, ValueError, TypeError) as exc:
        return {
            "case_id": case.case_id,
            "lab_id": case.lab_id,
            "kind": case.kind,
            "auth": case.auth,
            "status": "BLOCKED_DEPENDENCY",
            "reason": _safe_error(exc),
            "fixture": fixture.get("fixture", "none"),
            "fixture_status": "FAILED",
            "fixture_network_contact": bool(fixture.get("network_contact", False)),
            "description": case.description,
            "path": case.path,
            "network_contact": bool(fixture.get("network_contact", False)),
        }


def run_regression(
    project_root: Path,
    cases_path: Optional[Path] = None,
    repeat_rounds: int = 0,
    labs: Optional[Sequence[str]] = None,
    case_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Start selected local labs and execute bounded regression cases."""

    if not 0 <= int(repeat_rounds) <= MAX_ROUNDS:
        raise ValueError("repeat_rounds_out_of_range")
    root = Path(project_root).resolve()
    inventory = root / "config" / "labs" / "local_labs.json"
    compose = root / "docker-compose.local-labs.yml"
    policy = RuntimePolicy.from_file(root / "config" / "validation" / "local_only.json")
    cases = load_regression_cases(cases_path or (root / "config" / "validation" / "local_regression_cases.json"))
    wanted_labs = {str(item).strip().lower() for item in labs or [] if str(item).strip()}
    wanted_cases = {str(item).strip().lower() for item in case_ids or [] if str(item).strip()}
    selected = [
        item
        for item in cases
        if (not wanted_labs or item.lab_id in wanted_labs) and (not wanted_cases or item.case_id in wanted_cases)
    ]
    if not selected:
        raise ValueError("no_regression_cases_selected")
    manager = LocalLabManager(root, inventory, compose)
    for item in selected:
        manager.spec(item.lab_id)
    lifecycle: Dict[str, Any] = {}
    for lab_id in sorted({item.lab_id for item in selected}):
        lifecycle[lab_id] = manager.operate("up", lab_id, wait=True)
    rounds: List[Dict[str, Any]] = []
    artifact_root = root / "validation" / "autotest" / "local_regression"
    for round_index in range(int(repeat_rounds) + 1):
        round_result: Dict[str, Any] = {"round": round_index, "cases": [], "network_contact": False}
        for case in selected:
            result = _run_one_case(case, manager, policy)
            result["round"] = round_index
            path = artifact_root / case.lab_id / "round_{:02d}".format(round_index) / (case.case_id + ".json")
            _write_json(path, result, root)
            result["artifact"] = str(path)
            round_result["cases"].append(result)
            round_result["network_contact"] = bool(round_result["network_contact"] or result.get("network_contact") or result.get("fixture_network_contact"))
        rounds.append(round_result)
    all_results = [item for round_result in rounds for item in round_result["cases"]]
    passed = sum(1 for item in all_results if item.get("status") == "PASS")
    failed = sum(1 for item in all_results if item.get("status") == "FAIL")
    blocked = sum(1 for item in all_results if item.get("status") == "BLOCKED_DEPENDENCY")
    status = "COMPLETED" if passed == len(all_results) else ("BLOCKED_DEPENDENCY" if blocked and not failed else "PARTIAL")
    final = {
        "status": status,
        "mode": "local-only",
        "profile": "owasp-local-regression",
        "case_count": len(selected),
        "round_count": len(rounds),
        "executed_count": len(all_results),
        "passed_count": passed,
        "failed_count": failed,
        "blocked_count": blocked,
        "pass_rate": round(passed / float(len(all_results)), 6) if all_results else None,
        "labs": sorted({item.lab_id for item in selected}),
        "lifecycle": lifecycle,
        "rounds": rounds,
        "network_contact": any(bool(item.get("network_contact") or item.get("fixture_network_contact")) for item in all_results),
        "remote_ai": {"status": "NOT_RUN", "calls": 0},
        "submission_status": "NO_AUTO_SUBMISSION",
        "limitations": [
            "回归用例只验证本地可达性、认证边界和无害标记反射，不等于漏洞可利用性或补天奖励。",
            "未执行命令注入、文件上传、密码修改、盲注、拒绝服务等破坏性动作。",
            "任何外部目标必须另行人工确认授权，不能从本地回归配置推导授权。",
        ],
    }
    _write_json(artifact_root / "LOCAL_REGRESSION_SCORE.json", final, root)
    latest_by_case: Dict[str, Dict[str, Any]] = {}
    for item in rounds[-1]["cases"]:
        latest_by_case[str(item.get("case_id", ""))] = item
    report_lines = [
        "# 本地 OWASP 安全回归报告",
        "",
        "- 模式：仅本机回环（local-only）",
        "- 靶场：{}".format("、".join(final["labs"])),
        "- 轮次：{}；执行用例：{}；通过：{}；失败：{}；阻断：{}".format(
            final["round_count"], final["executed_count"], final["passed_count"], final["failed_count"], final["blocked_count"]
        ),
        "- 通过率：{}".format(final["pass_rate"]),
        "- 远程 AI 调用：0；自动提交：禁止",
        "",
        "## 最新轮用例",
        "",
        "| 靶场 | 用例 | 类型 | 结果 | HTTP | 证据摘要 |",
        "|---|---|---|---:|---:|---|",
    ]
    for case_id in sorted(latest_by_case):
        item = latest_by_case[case_id]
        report_lines.append(
            "| {lab} | {case} | {kind} | {status} | {http} | {matched}/{total} 条断言；响应 SHA-256 已写入 JSON |".format(
                lab=item.get("lab_id", ""),
                case=case_id,
                kind=item.get("kind", ""),
                status=item.get("status", ""),
                http=item.get("response_status", "-"),
                matched=item.get("matched_assertions", 0),
                total=item.get("total_assertions", 0),
            )
        )
    report_lines.extend(
        [
            "",
            "> 这些用例只证明本地靶场可达、认证边界和无害标记行为，不代表漏洞成立、补天受理或赏金。",
            "> 没有执行命令注入、文件上传、密码修改、盲注、拒绝服务等破坏性动作。",
        ]
    )
    _write_text(artifact_root / "LOCAL_REGRESSION_REPORT.md", "\n".join(report_lines) + "\n", root)
    return final


__all__ = [
    "RegressionCase",
    "RegressionError",
    "RegressionScopeError",
    "evaluate_expectations",
    "load_regression_cases",
    "redact_regression_headers",
    "run_regression",
    "safe_case_path",
]

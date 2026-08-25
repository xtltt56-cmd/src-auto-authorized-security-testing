"""Bounded local-only HTML/JavaScript/API surface discovery.

The discovery layer is intentionally separate from vulnerability verification.
It may fetch the explicitly selected local page and same-origin script assets,
but it never follows a redirect or requests a URL outside RuntimePolicy.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .runtime_policy import RuntimePolicy


MAX_DISCOVERY_BODY = 512 * 1024
MAX_SCRIPT_ASSETS = 24
MAX_OUTPUT_ITEMS = 400
_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "x-api-key", "proxy-authorization"})
_URL_RE = re.compile(r"https?://[^\s<>\"'`]+|(?<![A-Za-z0-9_])/(?:[A-Za-z0-9_.$~:@%+\-]+/?)+(?:\?[^\s<>\"'`]+)?")
_ROUTE_RE = re.compile(r"(?:path|route|url|redirectTo)\s*[:=]\s*[\"']([^\"']{1,240})[\"']", re.I)


class DiscoveryError(PermissionError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise DiscoveryError("redirect_requires_explicit_check: {}".format(newurl))


class _HTMLSurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: List[str] = []
        self.inline_scripts: List[str] = []
        self._in_script = False
        self._script_parts: List[str] = []

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        attrs_map = {str(name).lower(): str(value or "") for name, value in attrs}
        tag_name = str(tag).lower()
        if tag_name in {"script", "link", "a", "form", "iframe", "img"}:
            for key in ("src", "href", "action"):
                value = attrs_map.get(key, "").strip()
                if value:
                    self.references.append(value[:500])
        if tag_name == "script" and not attrs_map.get("src"):
            self._in_script = True
            self._script_parts = []

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        if str(tag).lower() == "script" and self._in_script:
            self.inline_scripts.append("".join(self._script_parts)[:MAX_DISCOVERY_BODY])
            self._in_script = False
            self._script_parts = []

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        if self._in_script and len("".join(self._script_parts)) < MAX_DISCOVERY_BODY:
            self._script_parts.append(str(data))


def redact_headers(headers: Mapping[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        if not name:
            continue
        result[name] = "<redacted>" if name in _SENSITIVE_HEADERS else str(raw_value or "")[:500]
    return result


def _allowed(policy: RuntimePolicy, url: str) -> bool:
    allowed, _reason = policy.decide_url(url)
    return bool(allowed)


def _normalise(base_url: str, value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate or candidate.startswith(("#", "data:", "javascript:", "mailto:", "tel:")):
        return ""
    return urljoin(base_url, candidate).split("#", 1)[0]


def _is_script(url: str, content_type: str = "") -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".js", ".mjs", ".cjs")) or "javascript" in str(content_type).lower() or "ecmascript" in str(content_type).lower()


def _is_api(url: str) -> bool:
    parsed = urlsplit(url)
    path = parsed.path.lower()
    return (
        path == "/api" or path.startswith("/api/")
        or path == "/rest" or path.startswith("/rest/")
        or path == "/graphql" or path.startswith("/graphql/")
        or path.endswith(("/login.php", "/setup.php"))
        or any(path.endswith(ext) for ext in (".json", ".xml"))
    )


def _is_auth(url: str) -> bool:
    value = (urlsplit(url).path + "?" + urlsplit(url).query).lower()
    return any(marker in value for marker in ("/login", "/signin", "/register", "/signup", "/logout", "/auth", "/session", "password"))


def _append(values: set, value: str) -> None:
    if value and len(values) < MAX_OUTPUT_ITEMS:
        values.add(value[:800])


def _plausible_client_route(url: str) -> bool:
    path = urlsplit(url).path
    if len(path) < 3 or not path.startswith("/"):
        return False
    if path.lower().endswith((".js", ".mjs", ".cjs", ".css", ".ico", ".png", ".jpg", ".svg")):
        return False
    if any(char in path for char in "(){}[]:$%*;\\"):
        return False
    first_segment = path.strip("/").split("/", 1)[0].lower()
    if len(first_segment) < 3 or any("." in segment and segment != ".well-known" for segment in path.strip("/").split("/")):
        return False
    if first_segment in {"a", "d", "div", "font", "g", "i", "loaded", "span", "strong", "u", "svg", "firefox", "applewebkit"}:
        return False
    return bool(re.fullmatch(r"/[A-Za-z][A-Za-z0-9._/-]{1,240}/?", path))


def _parse_document(base_url: str, content_type: str, body: str) -> Tuple[List[str], List[str]]:
    references: List[str] = []
    scripts: List[str] = []
    is_html = "html" in str(content_type).lower() or "<html" in str(body[:200]).lower()
    if is_html:
        parser = _HTMLSurfaceParser()
        try:
            parser.feed(body[:MAX_DISCOVERY_BODY])
        except (ValueError, TypeError):
            pass
        references.extend(parser.references)
        scripts.extend(parser.inline_scripts)
    if _is_script(base_url, content_type) or not is_html:
        scripts.append(body[:MAX_DISCOVERY_BODY])
    return references, scripts


def _strings_from_script(script: str) -> Iterable[str]:
    text = str(script or "")
    for match_obj in _URL_RE.finditer(text):
        match = str(match_obj.group(0))
        if match.startswith("/"):
            prefix = text[max(0, match_obj.start() - 8):match_obj.start()].lower()
            if prefix.endswith("http:") or prefix.endswith("https:") or prefix.endswith("//"):
                continue
        yield match.rstrip(".,;:)]}")
    for match in _ROUTE_RE.findall(text):
        yield str(match).strip()


def discover_documents(
    base_url: str,
    documents: Sequence[Tuple[str, str, str]],
    policy: RuntimePolicy,
) -> Dict[str, Any]:
    """Parse already obtained local documents without making network calls."""

    discovered = set()
    javascript = set()
    api_urls = set()
    client_routes = set()
    auth_surface = set()
    query_urls = set()
    excluded = set()
    script_candidates = set()
    for document_url, content_type, body in documents:
        document_url = str(document_url).strip()
        if not _allowed(policy, document_url):
            _append(excluded, document_url)
            continue
        _append(discovered, document_url)
        if _is_auth(document_url):
            _append(auth_surface, document_url)
        if _is_api(document_url):
            _append(api_urls, document_url)
        if _is_script(document_url, content_type):
            _append(javascript, document_url)
        references, scripts = _parse_document(document_url, content_type, str(body or ""))
        for raw in references:
            candidate = _normalise(document_url, raw)
            if not candidate:
                continue
            if _allowed(policy, candidate):
                _append(discovered, candidate)
                if _is_script(candidate):
                    _append(javascript, candidate)
                    _append(script_candidates, candidate)
                if _is_api(candidate):
                    _append(api_urls, candidate)
                elif _plausible_client_route(candidate) and not _is_script(candidate):
                    _append(client_routes, candidate)
                if _is_auth(candidate):
                    _append(auth_surface, candidate)
                if urlsplit(candidate).query:
                    _append(query_urls, candidate)
            else:
                _append(excluded, candidate)
        for script in scripts:
            for raw in _strings_from_script(script):
                candidate = _normalise(document_url, raw)
                if not candidate:
                    continue
                if _allowed(policy, candidate):
                    _append(discovered, candidate)
                    if _is_script(candidate):
                        _append(javascript, candidate)
                    if _is_api(candidate):
                        _append(api_urls, candidate)
                    elif _plausible_client_route(candidate) and not _is_script(candidate):
                        _append(client_routes, candidate)
                    if _is_auth(candidate):
                        _append(auth_surface, candidate)
                    if urlsplit(candidate).query:
                        _append(query_urls, candidate)
                else:
                    _append(excluded, candidate)
    return {
        "status": "COMPLETED",
        "mode": "static-document-parse",
        "target": str(base_url),
        "discovered_urls": sorted(discovered),
        "javascript_urls": sorted(javascript),
        "api_urls": sorted(api_urls),
        "client_routes": sorted(client_routes),
        "auth_surface": sorted(auth_surface),
        "query_urls": sorted(query_urls),
        "external_urls_excluded": sorted(excluded),
        "network_contact": False,
        "request_count": 0,
        "notes": "仅解析已获得文档；未执行发现之外的 URL 请求。",
    }


def _default_fetch(url: str) -> Dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise DiscoveryError("invalid_url")
    request = Request(url, headers={"User-Agent": "SRC-Auto/local-discovery", "Accept-Encoding": "identity"})
    opener = build_opener(_NoRedirect)
    try:
        response = opener.open(request, timeout=10)
        try:
            body = response.read(MAX_DISCOVERY_BODY)
            headers = getattr(response, "headers", {})
            return {
                "url": url,
                "final_url": str(response.geturl()),
                "content_type": str(headers.get("Content-Type", "")),
                "body": body.decode("utf-8", errors="replace"),
                "headers": redact_headers(headers),
            }
        finally:
            response.close()
    except HTTPError as exc:
        return {"url": url, "final_url": url, "content_type": "", "body": "", "headers": redact_headers(exc.headers or {})}
    except URLError as exc:
        raise DiscoveryError("local_fetch_failed: {}".format(exc))


def discover_local_surface(
    policy: RuntimePolicy,
    base_url: str,
    fetch_fn: Callable[[str], Mapping[str, Any]] = _default_fetch,
    max_scripts: int = MAX_SCRIPT_ASSETS,
) -> Dict[str, Any]:
    """Fetch one local document and its same-origin scripts only."""

    if not _allowed(policy, base_url):
        return {"status": "BLOCKED_SCOPE", "reason": "target_not_allowlisted", "target": base_url, "network_contact": False}
    try:
        first = dict(fetch_fn(base_url))
    except (DiscoveryError, OSError, TypeError, ValueError) as exc:
        return {"status": "BLOCKED_DEPENDENCY", "reason": str(exc)[:500], "target": base_url, "network_contact": False}
    final_url = str(first.get("final_url", base_url)).strip() or base_url
    if not _allowed(policy, final_url):
        return {"status": "BLOCKED_SCOPE", "reason": "redirect_out_of_scope", "target": base_url, "redirect": final_url, "network_contact": False}
    documents: List[Tuple[str, str, str]] = [
        (final_url, str(first.get("content_type", "")), str(first.get("body", ""))[:MAX_DISCOVERY_BODY])
    ]
    initial = discover_documents(base_url, documents, policy)
    scripts = [url for url in initial["javascript_urls"] if _allowed(policy, url)][: max(0, int(max_scripts))]
    fetched = 1
    excluded = set(initial["external_urls_excluded"])
    for script_url in scripts:
        if script_url == final_url:
            continue
        try:
            document = dict(fetch_fn(script_url))
        except (DiscoveryError, OSError, TypeError, ValueError):
            continue
        script_final = str(document.get("final_url", script_url)).strip() or script_url
        if not _allowed(policy, script_final):
            _append(excluded, script_final)
            continue
        documents.append((script_final, str(document.get("content_type", "")), str(document.get("body", ""))[:MAX_DISCOVERY_BODY]))
        fetched += 1
    result = discover_documents(base_url, documents, policy)
    result["mode"] = "bounded-static-fetch"
    result["network_contact"] = True
    result["request_count"] = fetched
    result["external_urls_excluded"] = sorted(set(result["external_urls_excluded"]) | excluded)
    result["external_excluded_count"] = len(result["external_urls_excluded"])
    result["degraded"] = False
    result["headers"] = redact_headers(first.get("headers", {}) if isinstance(first.get("headers"), Mapping) else {})
    return result

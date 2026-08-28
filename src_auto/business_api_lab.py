"""Safe, bounded authorization comparison for the local business API fixture."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .business_logic import ResponseSnapshot, compare_authorization_responses


class BusinessApiLabError(ValueError):
    pass


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
_USERS = ("buyer-a", "buyer-b", "anonymous")


def _validate_base_url(base_url: str) -> str:
    parsed = urlsplit(str(base_url).strip().rstrip("/"))
    if parsed.scheme != "http" or (parsed.hostname or "").lower() not in _LOOPBACK_HOSTS:
        raise BusinessApiLabError("business_api_url_must_be_loopback_http")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BusinessApiLabError("business_api_url_must_not_contain_credentials_or_query")
    if parsed.port not in (8084, None):
        raise BusinessApiLabError("business_api_url_port_not_allowlisted")
    port = parsed.port or 8084
    host = parsed.hostname or "127.0.0.1"
    return urlunsplit(("http", "{}:{}".format(host, port), "", "", ""))


def _snapshot_from_payload(status_code: int, payload: Any, content_type: str = "") -> ResponseSnapshot:
    # The comparison helper fingerprints the object and excludes volatile
    # fields.  Raw response bodies never leave this function.
    return ResponseSnapshot(
        status_code=int(status_code),
        headers={"content-type": content_type[:120]},
        body=payload if isinstance(payload, (dict, list, str, int, float, bool, type(None))) else {},
    )


def fetch_order(base_url: str, user: str, order_id: str = "order-a", timeout: int = 3) -> ResponseSnapshot:
    """Fetch one synthetic order with a GET-only, loopback-validated request."""

    root = _validate_base_url(base_url)
    if user not in _USERS:
        raise BusinessApiLabError("unknown_test_user")
    if order_id not in {"order-a", "order-b"}:
        raise BusinessApiLabError("unknown_synthetic_order")
    headers = {"Accept": "application/json"}
    if user != "anonymous":
        headers["X-Test-User"] = user
    request = Request(root + "/api/v1/orders/{}".format(order_id), headers=headers, method="GET")
    try:
        with urlopen(request, timeout=max(1, int(timeout))) as response:
            raw = response.read(65536)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                payload = {"parse_error": True}
            return _snapshot_from_payload(response.status, payload, response.headers.get("Content-Type", ""))
    except HTTPError as exc:
        return _snapshot_from_payload(exc.code, {"http_error": int(exc.code)}, exc.headers.get("Content-Type", ""))
    except (OSError, URLError) as exc:
        raise BusinessApiLabError("business_api_request_failed:{}".format(str(exc)[:160])) from exc


def run_authorization_matrix(
    base_url: str,
    fetcher: Optional[Callable[[str, str], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compare owner/peer/anonymous GET responses and emit metadata only.

    The optional ``fetcher`` is intentionally tiny so unit tests can provide
    deterministic synthetic snapshots without opening a socket.
    """

    _validate_base_url(base_url)
    order_id = "order-a"
    snapshots: Dict[str, ResponseSnapshot] = {}
    for user in _USERS:
        if fetcher is None:
            snapshots[user] = fetch_order(base_url, user, order_id)
        else:
            raw = fetcher(user, order_id)
            snapshots[user] = _snapshot_from_payload(
                int(raw.get("status_code", 0)),
                raw.get("body", {}),
                str(raw.get("content_type", "")),
            )
    comparison = compare_authorization_responses(
        snapshots["buyer-a"],
        snapshots["buyer-b"],
        snapshots["anonymous"],
        volatile_fields=("viewer", "x-src-auto"),
    )
    return {
        "status": "COMPLETED",
        "lab": "business-api",
        "base_url": _validate_base_url(base_url),
        "object": order_id,
        "method": "GET",
        "disposition": comparison["disposition"],
        "next_action": comparison["next_action"],
        "manual_review_required": True,
        "confirmed": False,
        "response_statuses": {
            "owner": comparison["owner_status"],
            "peer": comparison["peer_status"],
            "anonymous": comparison["anonymous_status"],
        },
        "owner_peer_equivalent": bool(comparison["owner_peer_equivalent"]),
        "body_fingerprints": comparison["body_fingerprints"],
        "network_contact": True,
        "raw_bodies_retained": False,
    }

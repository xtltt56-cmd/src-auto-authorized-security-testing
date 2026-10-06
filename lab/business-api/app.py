"""Deterministic, loopback-only business-logic training API.

This fixture is intentionally small and synthetic.  It exists to exercise the
offline comparison and authorization-review workflow; it must never be used
against a real service or exposed beyond the local lab network.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
OPENAPI_PATH = ROOT / "openapi.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8084
_ORDER_TEMPLATE = {
    "order-a": {
        "id": "order-a",
        "owner": "buyer-a",
        "status": "paid",
        "total": 1299,
        "currency": "CNY",
        "items": [{"sku": "lab-keyboard", "quantity": 1}],
    },
    "order-b": {
        "id": "order-b",
        "owner": "buyer-b",
        "status": "pending",
        "total": 499,
        "currency": "CNY",
        "items": [{"sku": "lab-mouse", "quantity": 1}],
    },
}
_orders = {}
_ORDER_RE = re.compile(r"^/api/v1/orders/([^/]+)$")
_AGENT_CASE_RE = re.compile(r"^/agent/cases/case-(\d{2})$")


def reset_state():
    """Reset the in-memory synthetic data without touching the host filesystem."""

    global _orders
    _orders = copy.deepcopy(_ORDER_TEMPLATE)


def _load_openapi():
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


def _json_safe(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class BusinessApiHandler(BaseHTTPRequestHandler):
    server_version = "SRC-Auto-BusinessAPI/1.0"

    def _send_json(self, status, payload):
        body = _json_safe(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "src-auto-business-api",
                    "local_only": True,
                    "synthetic_data": True,
                },
            )
            return
        if path == "/openapi.json":
            self._send_json(200, _load_openapi())
            return

        # Versioned synthetic controls: 10 vulnerable, 5 fixed private and 5
        # public objects. No expected verdict or training hint in responses.
        case_match = _AGENT_CASE_RE.fullmatch(path)
        if case_match and 1 <= int(case_match.group(1)) <= 20:
            index = int(case_match.group(1))
            viewer = self.headers.get("X-Test-User", "anonymous")
            if viewer not in {"buyer-a", "buyer-b", "anonymous"}:
                self._send_json(403, {"error": "denied"}); return
            if (index <= 10 and viewer == "anonymous") or (11 <= index <= 15 and viewer != "buyer-a"):
                self._send_json(403, {"error": "denied"}); return
            self._send_json(200, {"id": "case-{:02d}".format(index), "owner": "buyer-a",
                                  "access": "public" if index >= 16 else "private",
                                  "value": "synthetic-value-{:02d}".format(index)})
            return

        match = _ORDER_RE.match(path)
        if match:
            order_id = unquote(match.group(1))
            order = _orders.get(order_id)
            if order is None:
                self._send_json(404, {"error": "order_not_found", "id": order_id})
                return
            viewer = self.headers.get("X-Test-User", "anonymous")
            candidate = viewer in {"buyer-a", "buyer-b"} and viewer != order["owner"]
            response = copy.deepcopy(order)
            response["viewer"] = viewer
            response["x-src-auto"] = {
                "intentional_candidate": candidate,
                "manual_review_required": True,
                "fixture_scope": "local-only",
            }
            # This is an intentional training condition: both synthetic buyer
            # accounts can read either object so the response comparison tool
            # can surface a horizontal-authorization candidate.
            self._send_json(200, response)
            return

        self._send_json(404, {"error": "not_found"})

    def _method_not_allowed(self):
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        self._method_not_allowed()

    def do_PUT(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def log_message(self, format, *args):
        # Keep local smoke-test output deterministic and credential-free.
        return


def build_server(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """Build a server for the local fixture.

    ``0.0.0.0`` is accepted only for the container entry point; Docker
    publishes that container port on the host's 127.0.0.1 interface.
    """

    if host not in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("business API fixture only supports loopback/container binding")
    reset_state()
    return ThreadingHTTPServer((host, int(port)), BusinessApiHandler)


def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT):
    server = build_server(host, port)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="SRC-Auto 本地业务逻辑 API 靶场")
    parser.add_argument("--host", default=DEFAULT_HOST, choices=(DEFAULT_HOST, "0.0.0.0"))
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = parser.parse_args(argv)
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()

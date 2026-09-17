"""Loopback-only static Dashboard server with a narrow API reverse proxy.

The release package contains a prebuilt ``dashboard/dist`` directory.  This
server lets end users run that build without Node.js or Vite while preserving
the existing same-origin ``/api`` contract used by the React application.
"""

from __future__ import annotations

import argparse
import http.client
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

from .dashboard_identity import project_identity


_MAX_PROXY_REQUEST_BYTES = 32768
_MAX_PROXY_RESPONSE_BYTES = 16 * 1024 * 1024
_PROXY_REQUEST_HEADERS = ("Content-Type", "X-SRC-Auto-Token", "Origin")
_PROXY_RESPONSE_HEADERS = (
    "Content-Type",
    "Cache-Control",
    "X-Content-Type-Options",
    "Referrer-Policy",
)


class DashboardStaticHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, static_root: Path, api_port: int):
        super().__init__(server_address, handler_class)
        self.static_root = static_root
        self.api_port = int(api_port)


class DashboardStaticRequestHandler(BaseHTTPRequestHandler):
    server_version = "SRC-Auto-Dashboard/1.0"

    def log_message(self, fmt, *args):
        message = fmt % args
        print("[dashboard-web] {}".format(message[:500]))

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].strip().lower().rstrip(".")
        return host in ("127.0.0.1", "localhost")

    def _write_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )

    def _write_error(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._write_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _preflight(self) -> bool:
        if self._host_allowed():
            return True
        self._write_error(403, "仅允许本机回环主机访问")
        return False

    def _proxy_api(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_error(400, "请求长度无效")
            return
        if length < 0 or length > _MAX_PROXY_REQUEST_BYTES:
            self._write_error(413, "请求体超过本地代理限制")
            return
        body = self.rfile.read(length) if length else None
        headers = {"Host": "127.0.0.1:{}".format(self.server.api_port)}
        for name in _PROXY_REQUEST_HEADERS:
            value = self.headers.get(name)
            if value:
                headers[name] = value
        connection = http.client.HTTPConnection("127.0.0.1", self.server.api_port, timeout=10)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            declared_length = response.getheader("Content-Length")
            if declared_length and int(declared_length) > _MAX_PROXY_RESPONSE_BYTES:
                self._write_error(502, "本地控制接口响应超过代理限制")
                return
            payload = response.read(_MAX_PROXY_RESPONSE_BYTES + 1)
            if len(payload) > _MAX_PROXY_RESPONSE_BYTES:
                self._write_error(502, "本地控制接口响应超过代理限制")
                return
            self.send_response(response.status)
            for name in _PROXY_RESPONSE_HEADERS:
                value = response.getheader(name)
                if value:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self._write_security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (OSError, http.client.HTTPException, ValueError):
            self._write_error(502, "本地控制接口暂不可用")
        finally:
            connection.close()

    def _resolve_static_file(self) -> Optional[Path]:
        request_path = unquote(urlsplit(self.path).path)
        relative = request_path.lstrip("/")
        candidate = (self.server.static_root / relative).resolve()
        try:
            candidate.relative_to(self.server.static_root)
        except ValueError:
            return None
        if candidate.is_file():
            return candidate
        if request_path.startswith("/assets/") or "." in Path(relative).name:
            return None
        return self.server.static_root / "index.html"

    def _serve_static(self) -> None:
        path = self._resolve_static_file()
        if path is None or not path.is_file():
            self._write_error(404, "文件不存在")
            return
        try:
            body = path.read_bytes()
        except OSError:
            self._write_error(503, "Dashboard 文件暂不可读")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._write_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        if not self._preflight():
            return
        if self.path == '/health':
            payload = json.dumps({"status": "ok", "service": "src-auto-dashboard-web",
                                  "processId": os.getpid(), "projectId": project_identity(),
                                  "apiPort": self.server.api_port}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self._write_security_headers()
            self.end_headers()
            self.wfile.write(payload)
            return
        if urlsplit(self.path).path.startswith("/api/"):
            self._proxy_api()
            return
        self._serve_static()

    def do_HEAD(self):
        if not self._preflight():
            return
        self._serve_static()

    def do_POST(self):
        if not self._preflight():
            return
        if not urlsplit(self.path).path.startswith("/api/"):
            self._write_error(405, "该路径不接受写操作")
            return
        self._proxy_api()

    def do_OPTIONS(self):
        if not self._preflight():
            return
        if not urlsplit(self.path).path.startswith("/api/"):
            self._write_error(405, "该路径不接受预检请求")
            return
        self._proxy_api()


def create_static_server(static_root, port: int = 4173, api_port: int = 4174):
    root = Path(static_root).resolve()
    if not (root / "index.html").is_file():
        raise ValueError("dashboard_dist_missing")
    return DashboardStaticHTTPServer(
        ("127.0.0.1", int(port)), DashboardStaticRequestHandler, root, int(api_port)
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SRC-Auto Dashboard 仅回环静态服务")
    parser.add_argument("--root")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--api-port", type=int, default=4174)
    args = parser.parse_args(argv)
    root = args.root or str(Path(__file__).resolve().parents[1] / "dashboard" / "dist")
    server = create_static_server(root, port=args.port, api_port=args.api_port)
    print("SRC-Auto Dashboard 已启动：http://127.0.0.1:{}（仅回环）".format(args.port))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

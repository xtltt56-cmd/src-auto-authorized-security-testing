"""Token-protected, loopback-only HTTP adapter for the local lab Dashboard."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from .dashboard_control import DashboardControlService
from .local_labs import LocalLabManager
from .dashboard_workspace import DashboardWorkspace


_ALLOWED_ORIGIN = "http://127.0.0.1:4173"
_LAB_ACTION_ROUTE = re.compile(r"^/api/labs/([a-z0-9][a-z0-9_-]{0,31})/(start|stop|reset)$")
_BATCH_ROUTE = re.compile(r"^/api/labs/(start-all|stop-all)$")
_MAX_BODY_BYTES = 1024
_settings_lock = threading.Lock()
_settings_process = None


def open_openrouter_settings():
    """Open the fixed native dialog once; never accept a path or command from HTTP."""
    global _settings_process
    if os.name != 'nt':
        raise OSError('windows_required')
    with _settings_lock:
        if _settings_process is not None and _settings_process.poll() is None:
            return
        root = Path(__file__).resolve().parents[1]
        script = root / 'tools' / 'openrouter_settings_gui.ps1'
        if not script.is_file():
            raise OSError('settings_script_missing')
        # Python inherits PS7 paths unchanged; the dialog needs Windows PS5 modules.
        environment = {k: v for k, v in os.environ.items() if k.lower() != 'psmodulepath'}
        environment['PSModulePath'] = (
            r'C:\Windows\System32\WindowsPowerShell\v1.0\Modules;'
            r'C:\Program Files\WindowsPowerShell\Modules'
        )
        _settings_process = subprocess.Popen(
            [r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
             '-NoProfile', '-Sta', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
            cwd=str(root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, env=environment,
        )
        try:
            _settings_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return
        if _settings_process.returncode != 0:
            raise OSError('settings_launch_failed')


class DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, service, token, allowed_origin):
        super().__init__(server_address, handler_class)
        self.service = service
        self.session_token = token
        self.allowed_origin = allowed_origin


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = "SRC-Auto-Loopback/1.0"

    def log_message(self, fmt, *args):
        # Do not emit request headers, request bodies or session tokens.
        message = fmt % args
        print("[dashboard-api] {}".format(message[:500]))

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").strip()
        return not origin or origin == self.server.allowed_origin

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].strip().lower().rstrip(".")
        return host in ("127.0.0.1", "localhost")

    def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if self.headers.get("Origin", "").strip() == self.server.allowed_origin:
            self.send_header("Access-Control-Allow-Origin", self.server.allowed_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._write_json(status, {"ok": False, "error": code, "message": message})

    def _preflight(self) -> bool:
        if not self._host_allowed():
            self._error(403, "host_not_allowed", "仅允许本机回环主机访问")
            return False
        if not self._origin_allowed():
            self._error(403, "origin_not_allowed", "请求来源不在允许列表")
            return False
        return True

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-SRC-Auto-Token", "")
        if not supplied or not secrets.compare_digest(supplied, self.server.session_token):
            self._error(401, "invalid_session_token", "本地会话令牌无效或已过期")
            return False
        return True

    def do_OPTIONS(self):
        if not self._preflight():
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", self.server.allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SRC-Auto-Token")
        self.send_header("Access-Control-Max-Age", "300")
        self.end_headers()

    def do_GET(self):
        if not self._preflight():
            return
        if self.path == "/health":
            self._write_json(200, {"status": "ok", "service": "src-auto-dashboard-api", "loopbackOnly": True})
            return
        if self.path == "/api/session":
            self._write_json(200, {"token": self.server.session_token, "expires": "process"})
            return
        if self.path == "/api/dashboard":
            if not self._authorized():
                return
            try:
                self._write_json(200, self.server.service.snapshot())
            except Exception:
                self._error(503, "snapshot_unavailable", "暂时无法读取本地靶场状态")
            return
        if self.path in ('/api/drafts', '/api/review', '/api/artifacts'):
            if not self._authorized(): return
            try:
                workspace = self.server.workspace
                if self.path == '/api/drafts': payload = {'drafts': workspace.list_drafts()}
                elif self.path == '/api/review': payload = {'entries': workspace.review_targets()}
                else: payload = workspace.artifacts()
                self._write_json(200, payload)
            except (OSError, ValueError, TypeError):
                self._error(503, 'workspace_unavailable', '本地数据暂时无法读取，请检查项目目录')
            return
        self._error(404, "route_not_found", "接口不存在")

    def do_POST(self):
        if not self._preflight() or not self._authorized():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error(400, "invalid_content_length", "请求长度无效")
            return
        limit = 32768 if self.path == '/api/drafts' else _MAX_BODY_BYTES
        if length < 0 or length > limit:
            self._error(413, "request_too_large", "请求体超过本地控制接口限制")
            return
        document = {}
        if length:
            if self.headers.get_content_type() != "application/json":
                self._error(415, "json_required", "仅接受 JSON 请求")
                return
            try:
                document = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._error(400, "invalid_json", "JSON 请求无效")
                return
            if not isinstance(document, dict):
                self._error(400, "json_object_required", "请求必须是 JSON 对象")
                return
        if self.path == '/api/drafts':
            try:
                result = self.server.workspace.save_draft(document)
                self._write_json(201, result)
            except (ValueError, TypeError, OverflowError):
                self._error(400, 'draft_invalid', '草稿校验失败，请核对网址、端口、时间和必填项')
            except OSError:
                self._error(503, 'draft_save_failed', '草稿未保存，请检查项目目录权限')
            return
        if self.path == '/api/settings/openrouter':
            if document:
                self._error(400, 'empty_body_required', '设置窗口入口不接受额外参数')
                return
            try:
                open_openrouter_settings()
                self._write_json(202, {'accepted': True})
            except OSError:
                self._error(503, 'settings_unavailable', '无法打开 Windows 设置窗口，请检查启动器')
            return
        match = _LAB_ACTION_ROUTE.fullmatch(self.path)
        try:
            if match:
                payload = self.server.service.submit(match.group(1), match.group(2))
                self._write_json(202, dict(payload))
                return
            batch = _BATCH_ROUTE.fullmatch(self.path)
            if batch:
                action = "start" if batch.group(1) == "start-all" else "stop"
                payload = self.server.service.submit_all(action)
                self._write_json(202, dict(payload))
                return
        except ValueError as exc:
            code = str(exc) if str(exc) in ("unknown_lab_id", "unsupported_dashboard_action", "unsupported_dashboard_batch_action") else "invalid_operation"
            self._error(400, code, "请求未通过固定靶场操作校验")
            return
        except RuntimeError as exc:
            code = "lab_operation_in_progress" if str(exc) == "lab_operation_in_progress" else "operation_conflict"
            self._error(409, code, "该靶场已有操作正在执行")
            return
        self._error(404, "route_not_found", "接口不存在")


def create_server(service, port=4174, token=None, allowed_origin=_ALLOWED_ORIGIN, project_root=None):
    """Create a server bound to the fixed IPv4 loopback address."""

    server = DashboardHTTPServer(
        ("127.0.0.1", int(port)),
        DashboardRequestHandler,
        service,
        token or secrets.token_urlsafe(32),
        allowed_origin,
    )
    server.workspace = DashboardWorkspace(project_root or Path(__file__).resolve().parents[1])
    return server


def build_service(project_root: Path) -> DashboardControlService:
    root = Path(project_root).resolve()
    manager = LocalLabManager(root, root / "config" / "labs" / "local_labs.json", root / "docker-compose.local-labs.yml")
    return DashboardControlService(manager)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SRC-Auto 本地靶场 Dashboard 回环控制服务")
    parser.add_argument("--port", type=int, default=4174)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    service = build_service(root)
    server = create_server(service, port=args.port)
    print("SRC-Auto 本地控制服务已启动：http://127.0.0.1:{}（仅回环）".format(args.port))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Token-protected, loopback-only HTTP adapter for the local lab Dashboard."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote, urlsplit

from .dashboard_control import DashboardControlService
from .dashboard_identity import project_identity
from .local_labs import LocalLabManager
from .dashboard_workspace import DashboardWorkspace
from .provider_settings import ProviderSettingsStore
from .remote_ai import remote_session_consent_enabled


_ALLOWED_ORIGIN = "http://127.0.0.1:4173"
_LAB_ACTION_ROUTE = re.compile(r"^/api/labs/([a-z0-9][a-z0-9_-]{0,31})/(start|stop|reset)$")
_DETECTION_ROUTE = re.compile(r"^/api/labs/([a-z0-9][a-z0-9_-]{0,31})/(detect|detect-stop)$")
_BATCH_ROUTE = re.compile(r"^/api/labs/(start-all|stop-all)$")
_PROVIDER_ROUTE = re.compile(r"^/api/settings/providers/(deepseek|zhipu|openrouter)(/test)?$")
_REPORT_ROUTE = re.compile(r"^/api/reports/([^/?#]{1,2048})$")
_MAX_BODY_BYTES = 1024
_settings_lock = threading.Lock()
_settings_process = None
_docker_desktop_process = None


def validate_allowed_origin(value: str) -> str:
    """Accept one explicit loopback HTTP origin with no path or credentials."""

    parsed = urlsplit(str(value or "").strip())
    try:
        port = parsed.port
    except ValueError:
        raise argparse.ArgumentTypeError("allowed origin port is invalid")
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1024 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("allowed origin must be http://127.0.0.1:<port>")
    return "http://127.0.0.1:{}".format(port)


def open_ai_provider_settings():
    """Open the fixed native AI dialog once; never accept a path or command from HTTP."""
    global _settings_process
    if os.name != 'nt':
        raise OSError('windows_required')
    with _settings_lock:
        if _settings_process is not None and _settings_process.poll() is None:
            return
        root = Path(__file__).resolve().parents[1]
        script = root / 'tools' / 'ai_provider_settings_gui.ps1'
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


def open_openrouter_settings():
    """Backward-compatible alias for older launchers and tests."""
    return open_ai_provider_settings()


def start_docker_desktop():
    """Start Docker Desktop from a fixed installed path without accepting input."""
    global _docker_desktop_process
    if os.name != 'nt':
        raise OSError('windows_required')
    candidates = (
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'DockerDesktop' / 'Docker Desktop.exe',
        Path(r'C:\Program Files\Docker\Docker\Docker Desktop.exe'),
    )
    executable = next((item for item in candidates if item.is_file()), None)
    if executable is None:
        raise OSError('docker_desktop_not_found')
    if _docker_desktop_process is not None and _docker_desktop_process.poll() is None:
        return
    _docker_desktop_process = subprocess.Popen(
        [str(executable)],
        cwd=str(executable.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )


class DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, service, token, allowed_origin, remote_ai_enabled=None):
        super().__init__(server_address, handler_class)
        self.service = service
        self.session_token = token
        self.allowed_origin = allowed_origin
        # The consent is intentionally captured once when the API process starts.
        # A later browser checkbox cannot elevate a session that was started denied.
        self.remote_ai_session_enabled = (
            remote_session_consent_enabled("dashboard", "SRC_AUTO_REMOTE_AI_CONSENT")
            if remote_ai_enabled is None else bool(remote_ai_enabled)
        )


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
        if self.command == 'POST':
            self._discard_unread_body()
        self._write_json(status, {"ok": False, "error": code, "message": message})

    def _discard_unread_body(self) -> None:
        # Closing a Windows socket with unread POST bytes can reset even a
        # successfully written 401/413 response. Discard, never parse or log,
        # a bounded amount; slow/oversized clients cannot prolong rejection.
        if getattr(self, '_body_read', False):
            return
        try:
            remaining = min(max(int(self.headers.get('Content-Length', '0')), 0), 65536)
        except (ValueError, OverflowError):
            return
        previous = self.connection.gettimeout()
        deadline = time.monotonic() + .1
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                self.connection.settimeout(timeout)
                data = self.rfile.read1(min(remaining, 8192))
                if not data:
                    break
                remaining -= len(data)
        except (OSError, ValueError):
            # Connection rejection still follows a timeout or peer disconnect.
            pass
        finally:
            self.connection.settimeout(previous)

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
            self._write_json(200, {
                "status": "ok",
                "service": "src-auto-dashboard-api",
                "loopbackOnly": True,
                "processId": os.getpid(),
                "remoteAiSessionEnabled": self.server.remote_ai_session_enabled,
                "allowedOrigin": self.server.allowed_origin,
                "projectId": self.server.project_id,
            })
            return
        if self.path == "/api/session":
            self._write_json(200, {"token": self.server.session_token, "expires": "process"})
            return
        if self.path == "/api/lifecycle":
            if self._authorized():
                self._write_json(200, self.server.service.lifecycle())
            return
        if self.path == "/api/agent":
            if not self._authorized(): return
            agent = getattr(self.server.service, "agent", None)
            if agent is None:
                code = getattr(self.server.service, "agent_error", "agent_unavailable")
                self._error(503, code, "Agent 状态不可用；未清除历史，标准控制台仍可使用。请核对本地状态库或服务版本")
            else:
                self._write_json(200, agent.snapshot(self.server.remote_ai_session_enabled))
            return
        if self.path == '/api/local-targets':
            if not self._authorized(): return
            try:
                self._write_json(200, {'targets': self.server.service.agent.local_targets.list()})
            except Exception:
                self._error(503, 'local_targets_unavailable', '本机目标草稿库不可用')
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
        if self.path == '/api/artifacts/summary':
            if not self._authorized(): return
            try:
                self._write_json(200, self.server.workspace.artifact_summary())
            except (OSError, ValueError, TypeError):
                self._error(503, 'artifact_summary_unavailable', '本地候选统计暂时无法读取')
            return
        report_match = _REPORT_ROUTE.fullmatch(self.path)
        if report_match:
            if not self._authorized(): return
            try:
                self._write_json(200, self.server.workspace.read_report(unquote(report_match.group(1))))
            except ValueError as exc:
                if str(exc) == 'report_too_large':
                    self._error(413, 'report_too_large', '报告超过安全导出上限，请在项目目录中查看')
                else:
                    self._error(400, 'report_path_not_allowed', '报告路径不在项目白名单中')
            except OSError:
                self._error(503, 'report_unavailable', '报告暂时无法读取')
            return
        if self.path == '/api/settings/providers':
            if not self._authorized(): return
            try:
                payload = self.server.provider_settings.public_status()
                payload['providers'] = [
                    dict(provider, sessionEnabled=self.server.remote_ai_session_enabled)
                    for provider in payload.get('providers', [])
                ]
                self._write_json(200, payload)
            except (OSError, ValueError, TypeError):
                self._error(503, 'provider_settings_unavailable', '云端 AI 设置暂时无法读取')
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
        limit = 32768 if self.path in ('/api/drafts', '/api/local-targets/save', '/api/local-app/preview') else _MAX_BODY_BYTES
        if length < 0 or length > limit:
            self._error(413, "request_too_large", "请求体超过本地控制接口限制")
            return
        document = {}
        if length:
            if self.headers.get_content_type() != "application/json":
                self._error(415, "json_required", "仅接受 JSON 请求")
                return
            try:
                raw = self.rfile.read(length)
                self._body_read = True
                document = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._error(400, "invalid_json", "JSON 请求无效")
                return
            if not isinstance(document, dict):
                self._error(400, "json_object_required", "请求必须是 JSON 对象")
                return
        if self.path in {'/api/local-app/preview', '/api/local-app/start'}:
            agent = getattr(self.server.service, 'agent', None)
            if agent is None:
                self._error(503, 'agent_unavailable', '本机应用执行器不可用，请重新启动新版控制台')
                return
            try:
                operation = agent.local_app.preview if self.path.endswith('/preview') else agent.local_app.start
                result = operation(document, self.server.remote_ai_session_enabled)
                self._write_json(200 if self.path.endswith('/preview') else 202, result)
            except (ValueError, RuntimeError) as exc:
                from .local_application_workflow import LOCAL_ERRORS
                code = str(exc)
                status = 403 if code == 'remote_ai_disabled_for_session' else 409 if isinstance(exc, RuntimeError) else 400
                self._error(status, code if code in LOCAL_ERRORS else 'invalid_local_application_request',
                            LOCAL_ERRORS.get(code, '请核对本机入口、精确路由、时间窗与确认开关'))
            except Exception:
                self._error(503, 'local_application_unavailable', '本机应用执行配置暂时不可用；没有输出异常原文')
            return
        if self.path in {'/api/local-targets/save', '/api/local-targets/duplicate', '/api/local-targets/delete'}:
            # Draft storage does not authorize a source or network operation.
            try:
                library = self.server.service.agent.local_targets
                if self.path.endswith('/save'):
                    result = library.save(document)
                elif set(document) != {'id'}:
                    raise ValueError('invalid_local_target')
                else:
                    result = library.duplicate(document['id']) if self.path.endswith('/duplicate') else library.delete(document['id'])
                self._write_json(200, result)
            except ValueError:
                self._error(400, 'invalid_local_target', '请填写名称、精确回环入口与无副作用路由；保存不会授予执行权限')
            except Exception:
                self._error(503, 'local_targets_unavailable', '本机目标草稿库不可用')
            return
        if self.path in {'/api/source-audit/preview', '/api/source-audit/start'}:
            from .local_application import LocalApplicationError
            try:
                coordinator = self.server.service.agent.source_audit
                result = coordinator.preview(document) if self.path.endswith('/preview') else coordinator.start(document)
                self._write_json(200 if self.path.endswith('/preview') else 202, result)
            except (ValueError, RuntimeError, LocalApplicationError) as exc:
                code = getattr(exc, 'reason', str(exc))
                allowed = {'source_authorization_required', 'source_directory_invalid', 'source_directory_too_broad',
                    'source_languages_invalid', 'source_link_not_allowed', 'source_total_limit', 'source_file_limit',
                    'source_enumeration_limit', 'source_no_supported_files', 'source_scanner_unavailable',
                    'passive_scanner_unavailable', 'source_changed_after_approval', 'source_configuration_changed', 'source_approval_expired',
                    'approval_already_used', 'manual_execution_confirmation_required', 'agent_operation_conflict',
                    'dashboard_closing', 'resource_limit', 'blocked_disk', 'cancelled', 'task_timeout'}
                self._error(409 if isinstance(exc, RuntimeError) else 400, code if code in allowed else 'source_request_invalid',
                            '源码审查未启动：请核对独立目录授权、固定工具、文件额度与审批摘要')
            except Exception:
                self._error(503, 'source_audit_unavailable', '源码审查执行器不可用；没有输出异常原文')
            return
        if self.path in {'/api/agent/start', '/api/agent/enable', '/api/agent/cancel'}:
            agent = getattr(self.server.service, 'agent', None)
            if agent is None:
                self._error(503, 'agent_unavailable', '请重新启动新版 Dashboard 执行服务')
                return
            # Immutable startup gate before factory/config/key access, including resumes.
            if self.path == '/api/agent/start' and document.get('provider', 'local') != 'local' and not self.server.remote_ai_session_enabled:
                self._error(403, 'remote_ai_disabled_for_session', '本次启动禁止云端 AI；保存密钥不会解除此限制')
                return
            try:
                if self.path == '/api/agent/enable':
                    if set(document) != {'enabled'} or type(document['enabled']) is not bool: raise ValueError('invalid_agent_request')
                    result = agent.set_enabled(document['enabled'])
                elif self.path == '/api/agent/cancel':
                    if set(document) != {'id'}: raise ValueError('invalid_agent_request')
                    result = agent.cancel_run(document['id'])
                else: result = agent.start(document, self.server.remote_ai_session_enabled)
                self._write_json(200 if self.path.endswith('/enable') else 202, result)
            except (ValueError, RuntimeError) as exc:
                code = str(exc)
                safe_codes = {'invalid_agent_request', 'remote_ai_disabled_for_session', 'agent_disabled', 'agent_operation_conflict',
                              'lab_not_ready', 'dashboard_closing', 'foreign_candidate', 'resume_context_changed', 'agent_not_resumable',
                                'agent_not_running', 'permission_recipe_unavailable', 'unknown_agent_run', 'unsupported_provider', 'cloud_agent_not_validated'}
                self._error(409 if isinstance(exc, RuntimeError) else 400, code if code in safe_codes else 'agent_request_failed', '任务未提交，请检查靶场、模式与授权开关')
            except Exception:
                self._error(503, 'agent_configuration_unavailable', 'Agent 配置暂时不可用，请核对本地模型与配置')
            return
        if self.path == '/api/shutdown':
            if document:
                self._error(400, 'unexpected_fields', '关闭服务不接受额外参数')
            elif not self.server.service.prepare_shutdown():
                self._error(409, 'active_work', '请先停止运行中的任务，再关闭控制台服务')
            else:
                self._write_json(202, {'accepted': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
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
                open_ai_provider_settings()
                self._write_json(202, {'accepted': True})
            except OSError:
                self._error(503, 'settings_unavailable', '无法打开 Windows 设置窗口，请检查启动器')
            return
        provider_match = _PROVIDER_ROUTE.fullmatch(self.path)
        if provider_match:
            provider = provider_match.group(1)
            if provider_match.group(2):
                if not self.server.remote_ai_session_enabled:
                    self._error(403, 'remote_ai_disabled_for_session', '本次启动未授权远程 AI；请关闭 Dashboard 后重新启动并明确允许')
                    return
                if document != {'allowNetwork': True}:
                    self._error(400, 'network_consent_required', '必须明确允许本次最小联网测试')
                    return
                try:
                    self._write_json(200, self.server.provider_settings.test_connection(provider))
                except (OSError, ValueError, TypeError):
                    self._error(503, 'provider_test_unavailable', '无法完成本次连接测试')
                return
            if set(document) - {'apiKey', 'model'}:
                self._error(400, 'provider_settings_invalid', '设置包含不支持的字段')
                return
            try:
                result = self.server.provider_settings.save(provider, document.get('apiKey', ''), document.get('model', ''))
                self._write_json(200, result)
            except (ValueError, TypeError):
                self._error(400, 'provider_settings_invalid', '请检查密钥和模型 API ID')
            except OSError:
                self._error(503, 'provider_settings_save_failed', '设置未保存，请检查项目目录权限')
            return
        if self.path == '/api/dependencies/docker/start':
            if document:
                self._error(400, 'empty_body_required', 'Docker 启动入口不接受额外参数')
                return
            try:
                start_docker_desktop()
                self._write_json(202, {'accepted': True, 'message': 'Docker Desktop 启动请求已提交'})
            except OSError:
                self._error(503, 'docker_desktop_unavailable', '未找到 Docker Desktop，请先安装或手动启动')
            return
        match = _LAB_ACTION_ROUTE.fullmatch(self.path)
        try:
            detection = _DETECTION_ROUTE.fullmatch(self.path)
            if detection:
                if document:
                    self._error(400, 'empty_body_required', '本地检测入口不接受额外参数')
                    return
                if detection.group(2) == 'detect':
                    payload = self.server.service.submit_detection(detection.group(1))
                else:
                    payload = self.server.service.cancel_detection(detection.group(1))
                self._write_json(202, dict(payload))
                return
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
            reason = str(exc)
            messages = {
                "dashboard_closing": "控制台正在关闭，请重新启动后操作",
                "lab_operation_in_progress": "该靶场已有环境操作正在执行",
                "detection_in_progress": "该靶场已有检测任务正在执行",
                "detection_not_running": "该靶场当前没有可停止的检测任务",
                "lab_not_ready": "请先启动靶场并等待健康状态变为就绪",
                "docker_not_ready": "Docker 尚未就绪，无法启动本地检测",
                "detection_runner_unavailable": "本地检测执行器不可用",
            }
            code = reason if reason in messages else "operation_conflict"
            self._error(409, code, messages.get(reason, "该靶场已有操作正在执行"))
            return
        self._error(404, "route_not_found", "接口不存在")


def create_server(service, port=4174, token=None, allowed_origin=_ALLOWED_ORIGIN, project_root=None, remote_ai_enabled=None):
    """Create a server bound to the fixed IPv4 loopback address."""

    server = DashboardHTTPServer(
        ("127.0.0.1", int(port)),
        DashboardRequestHandler,
        service,
        token or secrets.token_urlsafe(32),
        allowed_origin,
        remote_ai_enabled=remote_ai_enabled,
    )
    server.workspace = DashboardWorkspace(project_root or Path(__file__).resolve().parents[1])
    server.project_id = project_identity(project_root)
    server.provider_settings = ProviderSettingsStore(project_root or Path(__file__).resolve().parents[1])
    return server


def build_service(project_root: Path, port=4174) -> DashboardControlService:
    root = Path(project_root).resolve()
    manager = LocalLabManager(root, root / "config" / "labs" / "local_labs.json", root / "docker-compose.local-labs.yml")
    service = DashboardControlService(manager, journal_path=root / "runtime" / "dashboard" / "task_state-{}.json".format(port))
    from .agent_service import AgentService
    import sqlite3
    try:
        service.agent = AgentService(root, service)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RuntimeError):
        # Preserve an unreadable checkpoint; optional Agent state must not take
        # down the existing Dashboard or be silently deleted to manufacture success.
        service.agent = None
        service.agent_error = "agent_state_unavailable"
    return service


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SRC-Auto 本地靶场 Dashboard 回环控制服务")
    parser.add_argument("--port", type=int, default=4174)
    parser.add_argument("--allowed-origin", type=validate_allowed_origin, default=_ALLOWED_ORIGIN)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    service = build_service(root, port=args.port)
    server = create_server(service, port=args.port, allowed_origin=args.allowed_origin)
    # Keep the bootstrap probe ASCII-only: GitHub's English Windows runners can
    # expose a cp1252 stdout when the process is redirected, where Chinese text
    # would raise UnicodeEncodeError before serve_forever() starts.
    print("SRC-Auto dashboard API ready: http://127.0.0.1:{} (loopback only)".format(args.port))
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

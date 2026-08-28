"""Loopback Dashboard control facade for the fixed local lab inventory.

The service deliberately exposes no arbitrary command, path, URL, image or
container name.  Every action is resolved through ``LocalLabManager`` and its
project-owned inventory before a Docker subprocess can be started.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


_ACTIONS = frozenset({"start", "stop", "reset"})
_DISPLAY_NAMES = {
    "juice-shop": "Juice Shop",
    "dvwa": "DVWA",
    "webgoat": "WebGoat",
    "vampi": "VAmPI",
    "business-api": "Business API",
}


def docker_dependency_status() -> Tuple[bool, str]:
    """Return Docker Engine availability without changing any system state."""

    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "Docker 未安装或当前不可用"
    if result.returncode != 0 or not result.stdout.strip():
        return False, "Docker Desktop 尚未就绪，请先启动 Docker Desktop"
    return True, "Docker Engine 已就绪"


class DashboardControlService:
    """Map ``LocalLabManager`` state and operations to the Dashboard schema."""

    def __init__(
        self,
        manager: Any,
        executor: Optional[Any] = None,
        clock: Optional[Callable[[], float]] = None,
        dependency_check: Optional[Callable[[], Tuple[bool, str]]] = None,
    ) -> None:
        self.manager = manager
        self._clock = clock or time.monotonic
        self._dependency_check = dependency_check or docker_dependency_status
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="src-auto-labs")
        self._owns_executor = executor is None
        self._lock = threading.RLock()
        self._operations: Dict[str, Dict[str, Any]] = {}
        self._events = deque(maxlen=200)
        self._next_event_id = 1

    @property
    def lab_ids(self):
        return tuple(self.manager.specs.keys())

    def close(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    def _append_event(self, lab_id: str, level: str, stage: str, message: str) -> None:
        with self._lock:
            self._events.append(
                {
                    "id": self._next_event_id,
                    "taskId": "run-lab-{}".format(lab_id),
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "level": level,
                    "stage": stage,
                    "message": message,
                    "tool": "local-lab-controller",
                    "redacted": True,
                }
            )
            self._next_event_id += 1

    def _validate(self, lab_id: str, action: str) -> str:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in _ACTIONS:
            raise ValueError("unsupported_dashboard_action")
        # LocalLabManager performs strict ID validation and fixed-inventory lookup.
        return self.manager.spec(lab_id).lab_id

    def submit(self, lab_id: str, action: str) -> Mapping[str, Any]:
        lab_id = self._validate(lab_id, action)
        action = str(action).strip().lower()
        with self._lock:
            current = self._operations.get(lab_id)
            if current and current.get("state") in ("queued", "running"):
                raise RuntimeError("lab_operation_in_progress")
            operation = {
                "lab_id": lab_id,
                "action": action,
                "state": "queued",
                "started": self._clock(),
                "finished": None,
                "message": "操作已进入本地队列",
            }
            self._operations[lab_id] = operation
        self._append_event(lab_id, "info", "操作排队", "{} 已进入本地执行队列".format(_action_name(action)))
        self._executor.submit(self._execute, operation)
        return {"accepted": True, "labId": lab_id, "action": action, "taskId": "run-lab-{}".format(lab_id)}

    def submit_all(self, action: str) -> Mapping[str, Any]:
        action = str(action or "").strip().lower()
        if action not in ("start", "stop"):
            raise ValueError("unsupported_dashboard_batch_action")
        accepted = []
        for lab_id in self.lab_ids:
            try:
                accepted.append(self.submit(lab_id, action))
            except RuntimeError:
                # A running operation remains protected; batch actions are idempotent
                # for other labs and report exactly which ones were accepted.
                continue
        return {"accepted": True, "action": action, "operations": accepted}

    def _execute(self, operation: Dict[str, Any]) -> None:
        lab_id = operation["lab_id"]
        action = operation["action"]
        with self._lock:
            operation["state"] = "running"
            operation["message"] = "正在{}".format(_action_name(action))
        self._append_event(lab_id, "info", "本地执行", "开始{}固定本地靶场".format(_action_name(action)))
        try:
            result = self.manager.operate(action, lab_id, wait=action in ("start", "reset"))
            result_status = str(result.get("status", "FAILED")).upper()
            succeeded = result_status in ("READY", "COMPLETED", "STOPPED")
            with self._lock:
                operation["state"] = "completed" if succeeded else "failed"
                operation["finished"] = self._clock()
                operation["message"] = "操作完成" if succeeded else _safe_failure_message(result)
            self._append_event(
                lab_id,
                "success" if succeeded else "danger",
                "操作完成" if succeeded else "操作失败",
                "{}已完成".format(_action_name(action)) if succeeded else "{}失败：{}".format(_action_name(action), operation["message"]),
            )
        except Exception as exc:  # Docker or inventory failures must become visible state.
            with self._lock:
                operation["state"] = "failed"
                operation["finished"] = self._clock()
                operation["message"] = _safe_exception_message(exc)
            self._append_event(lab_id, "danger", "操作失败", "{}失败：{}".format(_action_name(action), operation["message"]))

    def snapshot(self) -> Dict[str, Any]:
        docker_ready, dependency_message = self._dependency_check()
        now = self._clock()
        labs = []
        tasks = []
        for lab_id in self.lab_ids:
            spec = self.manager.spec(lab_id)
            try:
                raw = self.manager.status(lab_id) if docker_ready else {"status": "NOT_FOUND"}
            except Exception:
                raw = {"status": "NOT_FOUND"}
            with self._lock:
                operation = dict(self._operations.get(lab_id, {}))
            mapped = _map_state(str(raw.get("status", "NOT_FOUND")), operation, docker_ready)
            elapsed = _elapsed_seconds(operation, now)
            task_id = "run-lab-{}".format(lab_id)
            tasks.append(
                {
                    "id": task_id,
                    "name": "{} · 本地靶场".format(_DISPLAY_NAMES.get(lab_id, lab_id)),
                    "kind": "local-lab",
                    "state": mapped["task"],
                    "stage": mapped["stage"],
                    "progress": mapped["progress"],
                    "elapsedSeconds": elapsed,
                    "counters": {"endpoints": 0, "api": 0, "candidates": 0, "blocked": 0, "errors": 1 if mapped["task"] == "failed" else 0},
                    "networkContact": "loopback" if mapped["health"] in ("healthy", "starting") else "none",
                    "updatedAt": datetime.now().isoformat(),
                }
            )
            labs.append(
                {
                    "id": lab_id,
                    "taskId": task_id,
                    "name": _DISPLAY_NAMES.get(lab_id, lab_id),
                    "port": int(spec.host_port),
                    "health": mapped["health"],
                    "stage": mapped["stage"],
                    "durationSeconds": elapsed,
                    "candidates": 0,
                    "localOnly": True,
                    "operation": operation.get("state", "idle") if operation else "idle",
                    "openUrl": str(spec.health_url),
                    "message": operation.get("message", ""),
                }
            )
        aggregate_state = _aggregate_task_state(tasks)
        aggregate_elapsed = max([item["elapsedSeconds"] for item in tasks] or [0])
        aggregate = {
            "id": "run-local-001",
            "name": "本地五靶场控制",
            "kind": "local-lab",
            "state": aggregate_state,
            "stage": "本地靶场操作" if aggregate_state != "idle" else "未启动",
            "progress": 100 if aggregate_state == "completed" else (10 if aggregate_state in ("queued", "running") else 0),
            "elapsedSeconds": aggregate_elapsed,
            "counters": {"endpoints": 0, "api": 0, "candidates": 0, "blocked": 0, "errors": sum(1 for item in tasks if item["state"] == "failed")},
            "networkContact": "loopback" if any(item["networkContact"] == "loopback" for item in tasks) else "none",
            "updatedAt": datetime.now().isoformat(),
        }
        with self._lock:
            events = list(self._events)
        return {
            "source": "loopback",
            "dependency": {"executionServiceReady": True, "dockerReady": bool(docker_ready), "message": dependency_message},
            "tasks": [aggregate] + tasks,
            "labs": labs,
            "events": events,
            "findings": [],
            "reports": [],
        }


def _action_name(action: str) -> str:
    return {"start": "启动", "stop": "停止", "reset": "重置"}.get(action, "操作")


def _safe_failure_message(result: Mapping[str, Any]) -> str:
    reason = str(result.get("reason", "")).strip()
    status = str(result.get("status", "")).strip()
    reason_labels = {
        "docker_command_failed": "Docker 命令不可用",
        "lab_reset_remove_failed": "重置前清理服务失败",
        "BLOCKED_HEALTH_TIMEOUT": "健康检查超时",
        "UNHEALTHY": "健康检查未通过",
    }
    return (reason_labels.get(reason, reason) or reason_labels.get(status, status) or "本地 Docker 操作失败")[:160]


def _safe_exception_message(exc: Exception) -> str:
    # Never expose commands, filesystem paths or raw Docker output to the browser.
    name = exc.__class__.__name__
    if isinstance(exc, ValueError):
        return str(exc)[:160]
    return "本地执行异常（{}）".format(name)


def _elapsed_seconds(operation: Mapping[str, Any], now: float) -> int:
    if not operation:
        return 0
    started = float(operation.get("started") or now)
    finished = operation.get("finished")
    endpoint = float(finished) if finished is not None else now
    return max(0, int(endpoint - started))


def _map_state(status: str, operation: Mapping[str, Any], docker_ready: bool) -> Dict[str, Any]:
    operation_state = operation.get("state")
    if not docker_ready:
        return {"task": "blocked", "health": "blocked", "stage": "等待 Docker Desktop", "progress": 0}
    if operation_state == "queued":
        return {"task": "queued", "health": "starting", "stage": "等待执行", "progress": 5}
    if operation_state == "running":
        return {"task": "running", "health": "starting", "stage": str(operation.get("message") or "本地执行"), "progress": 20}
    if operation_state == "failed":
        return {"task": "failed", "health": "blocked", "stage": str(operation.get("message") or "操作失败"), "progress": 0}
    if status == "READY":
        return {"task": "completed", "health": "healthy", "stage": "靶场已就绪", "progress": 100}
    if status == "STARTING":
        return {"task": "running", "health": "starting", "stage": "健康检查", "progress": 70}
    if status in ("UNHEALTHY", "BLOCKED_NO_HEALTH", "BLOCKED_HEALTH_TIMEOUT", "NOT_READY"):
        return {"task": "blocked", "health": "blocked", "stage": "健康检查未通过", "progress": 0}
    return {"task": "idle", "health": "stopped", "stage": "未启动", "progress": 0}


def _aggregate_task_state(tasks):
    states = [item["state"] for item in tasks]
    if "failed" in states:
        return "failed"
    if "blocked" in states:
        return "blocked"
    if "running" in states:
        return "running"
    if "queued" in states:
        return "queued"
    if states and all(item in ("completed", "idle") for item in states) and "completed" in states:
        return "completed"
    return "idle"

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
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .dashboard_state import DashboardStateJournal, restored_state, was_interrupted


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
        detection_runner: Optional[Callable[..., Mapping[str, Any]]] = None,
        journal_path: Optional[Path] = None,
    ) -> None:
        self.manager = manager
        self._clock = clock or time.monotonic
        self._dependency_check = dependency_check or docker_dependency_status
        self._executor = executor or ThreadPoolExecutor(max_workers=min(5, len(manager.specs)), thread_name_prefix="src-auto-labs")
        self._owns_executor = executor is None
        self._lock = threading.RLock()
        self._operations: Dict[str, Dict[str, Any]] = {}
        self._detections: Dict[str, Dict[str, Any]] = {}
        self._events = deque(maxlen=200)
        self._next_event_id = 1
        self._journal = DashboardStateJournal(journal_path) if journal_path is not None else None
        self._journal_error = ""
        self._closing = False
        self._restore_journal()
        if detection_runner is not None:
            self._detection_runner = detection_runner
        elif getattr(manager, "project_root", None) is not None:
            from .dashboard_detection import LocalDetectionWorkflow

            self._detection_runner = LocalDetectionWorkflow(manager.project_root, manager).run
        else:
            self._detection_runner = None

    @property
    def lab_ids(self):
        return tuple(self.manager.specs.keys())

    def close(self) -> None:
        with self._lock:
            self._closing = True
            for operation in self._operations.values():
                if operation['action'] != 'stop': operation['cancel'].set()
            for detection in self._detections.values():
                detection['cancel'].set()
            self._persist_locked()
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    def lifecycle(self):
        with self._lock:
            return {"activeWork": any(
                item.get("state") in ("queued", "running", "cancelling", "paused")
                for item in list(self._operations.values()) + list(self._detections.values())
            ), "closing": self._closing}

    def prepare_shutdown(self):
        with self._lock:
            if self.lifecycle()["activeWork"]:
                return False
            self._closing = True
            self._persist_locked()
            return True

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
            self._persist_locked()

    def _persist_locked(self) -> None:
        if self._journal is None:
            return
        try:
            self._journal.save(
                self._operations,
                self._detections,
                self._events,
                self._next_event_id,
                self._clock(),
            )
            self._journal_error = ""
        except OSError:
            self._journal_error = "任务状态保存失败，请检查项目目录权限和磁盘空间；本次状态可能无法恢复"

    def _restore_journal(self) -> None:
        if self._journal is None:
            return
        try:
            document = self._journal.load()
        except (OSError, ValueError, TypeError):
            self._journal_error = "任务状态文件无法读取，已保留原文件；历史任务未恢复"
            return
        now = self._clock()
        for event in document.get("events", []):
            if isinstance(event, Mapping):
                self._events.append(dict(event))
        self._next_event_id = max(
            int(document.get("nextEventId", 1) or 1),
            max([int(event.get("id", 0)) for event in self._events] or [0]) + 1,
        )
        interrupted = []
        for record in document.get("operations", []):
            if not isinstance(record, Mapping):
                continue
            lab_id = str(record.get("labId", ""))
            try:
                lab_id = self.manager.spec(lab_id).lab_id
            except ValueError:
                continue
            is_interrupted = was_interrupted(record)
            operation = {
                "lab_id": lab_id,
                "action": str(record.get("action", "")),
                "state": restored_state(record),
                "started": now - max(0, int(record.get("elapsedSeconds", 0))),
                "finished": now,
                "message": "上次 Dashboard 服务意外中断，任务未自动恢复" if is_interrupted else str(record.get("message", ""))[:200],
                "cancel": threading.Event(),
                "done": threading.Event(),
                "previous": None,
            }
            operation["done"].set()
            self._operations[lab_id] = operation
            if is_interrupted:
                interrupted.append(lab_id)
        for record in document.get("detections", []):
            if not isinstance(record, Mapping):
                continue
            lab_id = str(record.get("labId", ""))
            try:
                lab_id = self.manager.spec(lab_id).lab_id
            except ValueError:
                continue
            is_interrupted = was_interrupted(record)
            counters = record.get("counters", {}) if isinstance(record.get("counters"), Mapping) else {}
            detection = {
                "lab_id": lab_id,
                "action": "detect",
                "state": restored_state(record),
                "stage": "上次服务意外中断" if is_interrupted else str(record.get("stage", ""))[:80],
                "progress": max(0, min(100, int(record.get("progress", 0)))),
                "started": now - max(0, int(record.get("elapsedSeconds", 0))),
                "finished": now,
                "message": "任务未自动恢复，请人工检查后重新开始" if is_interrupted else str(record.get("message", ""))[:200],
                "counters": {
                    key: max(0, int(counters.get(key, 0)))
                    for key in ("endpoints", "api", "candidates", "blocked", "errors")
                },
                "cancel": threading.Event(),
                "done": threading.Event(),
                "run_id": str(record.get("runId", ""))[:100],
                "report_id": str(record.get("reportId", ""))[:500],
                "network_contact": str(record.get("networkContact", "none"))[:20],
            }
            detection["done"].set()
            self._detections[lab_id] = detection
            if is_interrupted:
                interrupted.append(lab_id)
        for lab_id in sorted(set(interrupted)):
            self._events.append(
                {
                    "id": self._next_event_id,
                    "taskId": "run-lab-{}".format(lab_id),
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "level": "danger",
                    "stage": "意外中断",
                    "message": "检测到上次服务意外中断；任务没有自动恢复",
                    "tool": "local-lab-controller",
                    "redacted": True,
                }
            )
            self._next_event_id += 1
        if interrupted:
            self._persist_locked()

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
            if self._closing:
                raise RuntimeError("dashboard_closing")
            detection = self._detections.get(lab_id)
            if detection and detection.get("state") in ("queued", "running", "cancelling"):
                raise RuntimeError("detection_in_progress")
            current = self._operations.get(lab_id)
            if current and current.get("state") in ("queued", "running"):
                if action != "stop":
                    raise RuntimeError("lab_operation_in_progress")
                if current['action'] == 'stop':
                    return {"accepted": True, "labId": lab_id, "action": action, "taskId": "run-lab-{}".format(lab_id)}
                current['cancel'].set()
            operation = {
                "lab_id": lab_id,
                "action": action,
                "state": "queued",
                "started": self._clock(),
                "finished": None,
                "message": "操作已进入本地队列",
                "cancel": threading.Event(),
                "done": threading.Event(),
                "previous": current if current and current.get('state') in ('queued', 'running') else None,
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
        skipped = []
        for lab_id in self.lab_ids:
            try:
                accepted.append(self.submit(lab_id, action))
            except RuntimeError:
                # A running operation remains protected; batch actions are idempotent
                # for other labs and report exactly which ones were accepted.
                skipped.append(lab_id)
        return {"accepted": bool(accepted), "action": action, "operations": accepted, "skipped": skipped}

    def submit_detection(self, lab_id: str) -> Mapping[str, Any]:
        lab_id = self.manager.spec(lab_id).lab_id
        if self._detection_runner is None:
            raise RuntimeError("detection_runner_unavailable")
        docker_ready, _message = self._dependency_check()
        if not docker_ready:
            raise RuntimeError("docker_not_ready")
        status = self.manager.status(lab_id)
        if str(status.get("status", "")) != "READY":
            raise RuntimeError("lab_not_ready")
        with self._lock:
            if self._closing:
                raise RuntimeError("dashboard_closing")
            lifecycle = self._operations.get(lab_id)
            if lifecycle and lifecycle.get("state") in ("queued", "running"):
                raise RuntimeError("lab_operation_in_progress")
            current = self._detections.get(lab_id)
            if current and current.get("state") in ("queued", "running", "cancelling"):
                raise RuntimeError("detection_in_progress")
            operation = {
                "lab_id": lab_id,
                "action": "detect",
                "state": "queued",
                "stage": "检测排队",
                "progress": 3,
                "started": self._clock(),
                "finished": None,
                "message": "检测任务已进入本地队列",
                "counters": {"endpoints": 0, "api": 0, "candidates": 0, "blocked": 0, "errors": 0},
                "cancel": threading.Event(),
                "done": threading.Event(),
                "run_id": "",
                "report_id": "",
                "network_contact": "none",
            }
            self._detections[lab_id] = operation
        self._append_event(lab_id, "info", "检测排队", "真实回环检测已进入本地执行队列")
        self._executor.submit(self._execute_detection, operation)
        return {"accepted": True, "labId": lab_id, "action": "detect", "taskId": "run-lab-{}".format(lab_id)}

    def cancel_detection(self, lab_id: str) -> Mapping[str, Any]:
        lab_id = self.manager.spec(lab_id).lab_id
        with self._lock:
            operation = self._detections.get(lab_id)
            if not operation or operation.get("state") not in ("queued", "running", "cancelling"):
                raise RuntimeError("detection_not_running")
            operation["cancel"].set()
            operation["state"] = "cancelling"
            operation["stage"] = "正在停止检测"
            operation["message"] = "已请求在下一个安全检查点停止"
        self._append_event(lab_id, "warning", "停止检测", "已请求在下一个安全检查点停止检测")
        return {"accepted": True, "labId": lab_id, "action": "detect-stop", "taskId": "run-lab-{}".format(lab_id)}

    def _execute_detection(self, operation: Dict[str, Any]) -> None:
        try:
            self._perform_detection(operation)
        finally:
            operation["done"].set()

    def _perform_detection(self, operation: Dict[str, Any]) -> None:
        lab_id = operation["lab_id"]
        with self._lock:
            if operation["cancel"].is_set():
                operation.update(state="cancelled", stage="已取消", finished=self._clock(), message="检测已取消")
                self._append_event(lab_id, "warning", "已取消", "检测在网络接触前已取消")
                return
            operation.update(state="running", stage="范围预检", progress=5, message="正在校验固定回环范围")

        def progress(stage, value, counters, message, level="info"):
            with self._lock:
                operation["stage"] = str(stage)[:80]
                operation["progress"] = max(0, min(100, int(value)))
                operation["message"] = str(message)[:200]
                if isinstance(counters, Mapping):
                    operation["counters"] = {
                        key: max(0, int(counters.get(key, 0)))
                        for key in ("endpoints", "api", "candidates", "blocked", "errors")
                    }
            self._append_event(lab_id, str(level), str(stage)[:80], str(message)[:200])

        try:
            result = dict(self._detection_runner(lab_id, operation["cancel"], progress))
            status = str(result.get("status", "failed"))
            with self._lock:
                operation["finished"] = self._clock()
                operation["run_id"] = str(result.get("runId", ""))[:100]
                operation["report_id"] = str(result.get("reportId", ""))[:500]
                operation["network_contact"] = str(result.get("networkContact", "none"))
                if status == "completed":
                    operation.update(state="completed", stage="检测完成", progress=100, message="检测完成，等待人工复核")
                    operation["counters"].update(
                        endpoints=max(0, int(result.get("endpointCount", operation["counters"]["endpoints"]))),
                        api=max(0, int(result.get("apiCount", operation["counters"]["api"]))),
                        candidates=max(0, int(result.get("candidateCount", operation["counters"]["candidates"]))),
                        blocked=max(0, int(result.get("blockedCount", operation["counters"]["blocked"]))),
                        errors=max(0, int(result.get("errorCount", operation["counters"]["errors"]))),
                    )
                elif status == "cancelled":
                    operation.update(state="cancelled", stage="已取消", message="检测已在安全检查点停止")
                elif status == "blocked":
                    operation.update(state="failed", stage="检测受阻", message="检测因本地依赖或范围检查未通过而停止")
                    operation["counters"]["blocked"] += 1
                else:
                    operation.update(state="failed", stage="检测失败", message="检测未完成，请查看脱敏事件")
                    operation["counters"]["errors"] += 1
                self._persist_locked()
            if status == "cancelled":
                self._append_event(lab_id, "warning", "已取消", "检测已在安全检查点停止")
            elif status == "completed":
                self._append_event(lab_id, "success", "检测完成", "检测完成，候选等待人工复核")
            elif status != "completed":
                self._append_event(lab_id, "danger", operation["stage"], operation["message"])
        except Exception as exc:
            with self._lock:
                operation.update(
                    state="failed", stage="检测失败", finished=self._clock(),
                    message="本地检测异常（{}）".format(exc.__class__.__name__),
                )
                operation["counters"]["errors"] += 1
            self._append_event(lab_id, "danger", "检测失败", operation["message"])

    def _execute(self, operation: Dict[str, Any]) -> None:
        try:
            previous = operation.get('previous')
            if previous:
                previous['done'].wait()
            self._perform(operation)
        finally:
            operation['done'].set()

    def _perform(self, operation: Dict[str, Any]) -> None:
        lab_id = operation["lab_id"]
        action = operation["action"]
        with self._lock:
            if operation['cancel'].is_set():
                operation['state'] = 'cancelled'
                operation['finished'] = self._clock()
                self._append_event(lab_id, 'warning', '已取消', '排队操作已取消')
                return
            operation["state"] = "running"
            operation["message"] = "正在{}".format(_action_name(action))
        self._append_event(lab_id, "info", "本地执行", "开始{}固定本地靶场".format(_action_name(action)))
        try:
            result = self.manager.operate(action, lab_id, wait=action in ("start", "reset"), cancel_event=operation['cancel'])
            result_status = str(result.get("status", "FAILED")).upper()
            succeeded = result_status in ("READY", "COMPLETED", "STOPPED")
            if operation['cancel'].is_set():
                with self._lock:
                    operation['state'] = 'cancelled'
                    operation['finished'] = self._clock()
                self._append_event(lab_id, 'warning', '停止请求', '当前启动操作已退出，队列将执行停止')
                return
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
                detection = dict(self._detections.get(lab_id, {}))
            mapped = _map_state(str(raw.get("status", "NOT_FOUND")), operation, docker_ready)
            elapsed = _elapsed_seconds(operation, now)
            counters = {"endpoints": 0, "api": 0, "candidates": 0, "blocked": 0, "errors": 1 if mapped["task"] == "failed" else 0}
            detection_state = str(detection.get("state", ""))
            if detection and operation.get("state") not in ("queued", "running", "failed"):
                detection_map = {
                    "queued": "queued", "running": "running", "cancelling": "running",
                    "completed": "completed", "failed": "failed", "cancelled": "cancelled",
                }
                mapped["task"] = detection_map.get(detection_state, mapped["task"])
                mapped["stage"] = str(detection.get("stage") or mapped["stage"])
                mapped["progress"] = max(0, min(100, int(detection.get("progress", 0))))
                elapsed = _elapsed_seconds(detection, now)
                counters.update(detection.get("counters", {}))
                if mapped["task"] == "failed":
                    counters["errors"] = max(1, int(counters.get("errors", 0)))
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
                    "counters": counters,
                    "networkContact": "loopback" if detection.get("network_contact") == "loopback" or mapped["health"] in ("healthy", "starting") else "none",
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
                    "candidates": int(counters.get("candidates", 0)),
                    "reportId": str(detection.get("report_id", "")) or None,
                    "lastRunId": str(detection.get("run_id", "")) or None,
                    "localOnly": True,
                    "operation": operation.get("state", "idle") if operation else "idle",
                    "detectionOperation": detection_state or "idle",
                    "openUrl": str(spec.health_url),
                    "message": dependency_message if not docker_ready else operation.get("message", ""),
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
            "counters": {
                key: sum(int(item["counters"].get(key, 0)) for item in tasks)
                for key in ("endpoints", "api", "candidates", "blocked", "errors")
            },
            "networkContact": "loopback" if any(item["networkContact"] == "loopback" for item in tasks) else "none",
            "updatedAt": datetime.now().isoformat(),
        }
        with self._lock:
            events = list(self._events)
            if self._journal_error:
                events.append({"id": self._next_event_id, "taskId": "run-local-001",
                               "time": datetime.now().strftime("%H:%M:%S"), "level": "danger",
                               "stage": "状态持久化异常", "message": self._journal_error,
                               "tool": "local-lab-controller", "redacted": True})
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
        return {"task": "blocked", "health": "unavailable", "stage": "Docker 未就绪", "progress": 0}
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

"""Bounded feedback loop and durable, redacted checkpoints (Python 3.8)."""
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .agent_contracts import CATALOG_VERSION, Decision, Limits
from .controls import DiskGuard, StopController

ACTIVE = {"queued", "running", "cancelling"}


def process_identity(pid):
    """Read-only liveness check; never use os.kill on Windows (it can terminate)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False if ctypes.get_last_error() == 87 else None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)): return None
            if code.value != 259: return False
            creation, end, system, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(x) for x in (creation, end, system, user))): return None
            return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # POSIX signal 0 is a non-mutating existence check.
        stat = Path("/proc/{}/stat".format(pid))
        return stat.read_text().rsplit(")", 1)[1].split()[19] if stat.exists() else "alive"
    except ProcessLookupError: return False
    except (PermissionError, OSError): return None


def current_owner():
    return {"pid": os.getpid(), "identity": process_identity(os.getpid())}


def owner_is_alive(owner):
    if not isinstance(owner, dict) or type(owner.get("pid")) is not int or owner["pid"] <= 0:
        return False  # Legacy checkpoints do not grant permission to restart.
    identity = process_identity(owner["pid"])
    if identity is False or identity is None: return identity
    return True if owner.get("identity") is None else identity == owner["identity"]


def project_path(root, *parts):
    path = root.joinpath(*parts)
    try: path.resolve().relative_to(root.resolve())
    except ValueError: raise RuntimeError("agent_path_outside_project")
    return path


class AgentHistory:
    """Separate additive state: existing customer DB is never migrated or reset."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = project_path(self.root, "data", "agent.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.owner = dict(current_owner(), lease=uuid.uuid4().hex)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
            for key, text in conn.execute("SELECT id, document FROM agent_runs").fetchall():
                row = json.loads(text)
                if row["state"] in ACTIVE and owner_is_alive(row.get("owner")) is False:
                    row.update(state="interrupted", reason="service_interrupted")
                    conn.execute("UPDATE agent_runs SET document=? WHERE id=?", (json.dumps(row, ensure_ascii=False), key))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, key):
        with self.lock, self.connect() as conn:
            value = conn.execute("SELECT document FROM agent_runs WHERE id=?", (key,)).fetchone()
            if not value:
                raise ValueError("unknown_agent_run")
            return json.loads(value[0])

    def list(self):
        with self.lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = [json.loads(x[0]) for x in conn.execute("SELECT document FROM agent_runs ORDER BY rowid DESC LIMIT 50")]
            for row in rows:
                if row["state"] in ACTIVE and owner_is_alive(row.get("owner")) is False:
                    row.update(state="interrupted", reason="service_interrupted")
                    conn.execute("UPDATE agent_runs SET document=? WHERE id=?", (json.dumps(row, ensure_ascii=False), row["id"]))
            return rows

    def update(self, key, **values):
        with self.lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            value = conn.execute("SELECT document FROM agent_runs WHERE id=?", (key,)).fetchone()
            if not value: raise ValueError("unknown_agent_run")
            row = json.loads(value[0])
            row.update(values, updatedAt=datetime.now().isoformat(timespec="seconds"))
            conn.execute("UPDATE agent_runs SET document=? WHERE id=?", (json.dumps(row, ensure_ascii=False), key))
            return row

    def create(self, lab, mode, provider, limits, actions):
        row = {"id": uuid.uuid4().hex, "labId": lab, "mode": mode, "provider": provider,
               "state": "queued", "reason": "", "steps": 0, "requests": 0, "modelCalls": 0,
               "tokens": 0, "usageEstimated": False, "elapsedSeconds": 0, "candidates": 0,
               "confirmed": False, "submissionReady": False, "limits": limits.to_mapping(),
               "scopeHash": actions.scope_hash, "configHash": actions.config_hash, "owner": self.owner,
               "catalogVersion": CATALOG_VERSION, "observations": [], "trace": [], "reportId": "",
               "createdAt": datetime.now().isoformat(timespec="seconds"), "updatedAt": datetime.now().isoformat(timespec="seconds")}
        with self.lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_idle(conn)
            conn.execute("INSERT INTO agent_runs VALUES (?,?)", (row["id"], json.dumps(row, ensure_ascii=False)))
        return row

    def _assert_idle(self, conn, except_id=None):
        for key, text in conn.execute("SELECT id, document FROM agent_runs").fetchall():
            row = json.loads(text)
            if key == except_id or row["state"] not in ACTIVE: continue
            if owner_is_alive(row.get("owner")) is not False:
                raise RuntimeError("agent_operation_conflict")
            row.update(state="interrupted", reason="service_interrupted")
            conn.execute("UPDATE agent_runs SET document=? WHERE id=?", (json.dumps(row, ensure_ascii=False), key))

    def acquire(self, key, resume=False):
        """Atomic cross-process claim, including manual resumption."""
        with self.lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            value = conn.execute("SELECT document FROM agent_runs WHERE id=?", (key,)).fetchone()
            if not value: raise ValueError("unknown_agent_run")
            row = json.loads(value[0])
            if resume:
                if row["state"] not in {"paused", "interrupted"}: raise ValueError("agent_not_resumable")
            elif row["state"] != "queued" or row.get("owner") != self.owner:
                raise RuntimeError("agent_operation_conflict")
            self._assert_idle(conn, except_id=key)
            row.update(state="running", reason="", owner=self.owner)
            conn.execute("UPDATE agent_runs SET document=? WHERE id=?", (json.dumps(row, ensure_ascii=False), key))
            return row


class AgentRunner:
    def __init__(self, root, history, model, actions, limits=None, provider="local", resource_check=None):
        self.root, self.history, self.model, self.actions = Path(root), history, model, actions
        self.limits, self.provider = limits or Limits(), provider
        self.resource_check = resource_check or (lambda: {"allowed": False, "known": False, "reason": "resource_metrics_unavailable"})

    def run(self, lab, mode, cancel, resume_id=None, run_id=None):
        if resume_id:
            row = self.history.get(resume_id)
            if row["state"] not in {"paused", "interrupted"}:
                raise ValueError("agent_not_resumable")
            if (row["labId"], row["mode"], row["provider"], row["scopeHash"], row["configHash"], row["catalogVersion"]) != (
                    lab, mode, self.provider, self.actions.scope_hash, self.actions.config_hash, CATALOG_VERSION):
                raise ValueError("resume_context_changed")
            self.limits = Limits.from_mapping(row["limits"])
        else:
            row = self.history.get(run_id) if run_id else self.history.create(lab, mode, self.provider, self.limits, self.actions)
        started = time.monotonic()
        previous_elapsed = row["elapsedSeconds"]
        self.actions.requests = row["requests"]
        trace, observations = row["trace"], row["observations"]
        used = {(x["decision"]["action"], x["decision"]["reference"]) for x in trace if x.get("result") == "ok"}
        repaired = any(x.get("result") == "rejected" for x in trace)
        row = self.history.acquire(row["id"], resume=bool(resume_id))

        def save(**changes):
            row.update(changes, trace=trace, observations=observations, requests=self.actions.requests,
                       elapsedSeconds=round(previous_elapsed + time.monotonic() - started, 2))
            self.history.update(row["id"], **row)

        def gate(before_model=True):
            if cancel.is_set() or StopController(self.root / "STOP").requested():
                return "cancelled", "operator_stop"
            if previous_elapsed + time.monotonic() - started >= self.limits.max_seconds:
                return "needs-human", "time_limit"
            if before_model and (row["modelCalls"] >= self.limits.max_model_calls or row["tokens"] >= self.limits.max_tokens):
                return "needs-human", "budget_limit"
            if shutil.disk_usage(str(self.root)).free < 1024 ** 3:
                return "paused", "disk_free_low"
            resource = self.resource_check()
            row["resourceCheck"] = resource
            if not resource.get("allowed"):
                return "paused", "resource_limit"
            return None

        try:
            DiskGuard(self.root).assert_allowed()
            while True:
                stop = gate()
                if stop:
                    save(state=stop[0], reason=stop[1]); break
                context = {"mode": mode, "lab": lab, "references": self.actions.references,
                           "permissions": getattr(self.actions, "permissions", None),
                           "capabilities": (["finish", "request_human_review"] if row["steps"] >= self.limits.max_steps else getattr(self.actions, "capabilities", [])),
                           "observations": observations[-8:], "used": [list(x) for x in sorted(used)],
                           "steps_remaining": self.limits.max_steps - row["steps"],
                           "repair": "上次格式不合法；请仅返回四字段JSON" if repaired else ""}
                # Reserve a conservative input + output bound before starting inference.
                if row["tokens"] + 6800 > self.limits.max_tokens:
                    save(state="needs-human", reason="token_reservation_limit"); break
                row["modelCalls"] += 1
                save(reason="model_deciding")
                try:
                    remaining = max(1, self.limits.max_seconds - (previous_elapsed + time.monotonic() - started))
                    if hasattr(self.model, "provider"):
                        self.model.provider.timeout_seconds = max(1, int(min(self.model.provider.timeout_seconds, remaining)))
                    answer = self.model.decide(context)
                    usage = [answer.get("input_tokens"), answer.get("output_tokens")]
                    if any(type(x) is not int or x < 0 for x in usage):
                        raise ValueError("invalid_model_usage")
                    row["tokens"] += sum(usage)
                    row["usageEstimated"] = row["usageEstimated"] or bool(answer.get("usage_estimated"))
                except Exception:
                    # A timed-out remote request may still be billed; reserve the cap, do not retry it.
                    row["tokens"] += 6800
                    row["usageEstimated"] = True
                    save(state="paused", reason="model_unavailable"); break
                stop = gate(before_model=False)
                if stop:
                    save(state=stop[0], reason=stop[1]); break
                if row["tokens"] > self.limits.max_tokens:
                    save(state="needs-human", reason="budget_limit"); break
                try:
                    value = Decision.parse(answer["text"], self.actions.references, [x["id"] for x in observations])
                except (ValueError, TypeError, KeyError):
                    trace.append({"index": len(trace) + 1, "result": "rejected", "reason": "invalid_proposal"})
                    if repaired:
                        save(state="needs-human", reason="invalid_proposal"); break
                    repaired = True
                    save(reason="format_repair"); continue
                action = (value.action, value.reference)
                entry = {"index": len(trace) + 1, "decision": value.to_mapping(), "result": "proposed"}
                trace.append(entry)
                if value.action in {"finish", "request_human_review"}:
                    if not observations or not value.evidence:
                        entry["result"] = "rejected"
                        save(state="needs-human", reason="insufficient_evidence"); break
                    evidence = [x for x in observations if x["id"] in value.evidence]
                    if value.action == "finish" and mode == "api-permissions" and not any(x["action"] == "compare_object_authorization" for x in evidence):
                        entry["result"] = "rejected"
                        save(state="needs-human", reason="permission_check_incomplete"); break
                    if value.action == "finish" and mode == "candidate-review" and "candidate" in self.actions.references and not any(x["action"] == "review_candidate" for x in evidence):
                        entry["result"] = "rejected"
                        save(state="needs-human", reason="candidate_review_incomplete"); break
                    entry["result"] = "ok"
                    save(state="completed" if value.action == "finish" else "needs-human", reason=value.action); break
                if row["steps"] >= self.limits.max_steps:
                    entry["result"] = "rejected"
                    save(state="needs-human", reason="budget_limit"); break
                if action in used:
                    entry["result"] = "rejected"
                    save(state="needs-human", reason="duplicate_action"); break
                # Persist intent before I/O. An interrupted in-flight action is not silently replayed.
                if any(x.get("result") == "executing" for x in trace[:-1]):
                    entry["result"] = "rejected"
                    save(state="needs-human", reason="inflight_action_uncertain"); break
                entry["result"] = "executing"
                row["steps"] += 1
                save(reason="tool_executing")
                try:
                    result = self.actions.execute(value)
                except Exception as exc:
                    entry["result"] = "failed"
                    code = str(exc) if str(exc) in {"request_limit", "scope_blocked", "cancelled", "response_too_large", "capability_unavailable"} else "tool_failed"
                    save(state="cancelled" if code == "cancelled" else "needs-human", reason=code); break
                if cancel.is_set():
                    entry["result"] = "cancelled"
                    save(state="cancelled", reason="operator_stop"); break
                observation = dict(result, id="o{}".format(len(observations) + 1), action=value.action, reference=value.reference)
                # Executor output, not arbitrary model text, is the trusted observation boundary.
                if len(json.dumps(observation, ensure_ascii=False).encode("utf-8")) > 2500:
                    entry["result"] = "failed"
                    save(state="needs-human", reason="observation_too_large"); break
                observations.append(observation)
                if result.get("candidate") and hasattr(self.actions, "persist_candidate"):
                    observation["findingId"] = self.actions.persist_candidate(row["id"], value, observation)
                entry.update(result="ok", observationId=observation["id"])
                used.add(action)
                row["candidates"] += int(bool(result.get("candidate")))
                save(reason="observation_saved")
        except Exception:
            save(state="failed", reason="execution_failed")
        path = project_path(self.root, "reports", "agent", row["id"] + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        report = ["# 受控 Agent 执行记录（人工复核草稿）", "", "仅本地只读检查；候选未确认，不会自动提交。模型简述不是事实裁决；结果以工具观察及人工复核为准。", "",
                  "任务：{} / {} / {}".format(lab, mode, self.provider), "状态：{}；原因：{}".format(row["state"], row["reason"]),
                  "动作 {}；HTTP 请求 {}；模型调用 {}；Token {}{}".format(row["steps"], row["requests"], row["modelCalls"], row["tokens"], "（含保守估算）" if row["usageEstimated"] else ""), "",
                  "范围摘要：{}；配置摘要：{}；动作版本：{}".format(row["scopeHash"], row["configHash"], CATALOG_VERSION), "",
                  "```json", json.dumps({"resourceCheck": row.get("resourceCheck"), "trace": trace, "observations": observations}, ensure_ascii=False, indent=2), "```", "",
                  "云端费用未计价，请核对服务商账单。候选和报告只用于人工研判，不代表漏洞已经确认。"]
        path.write_text("\n".join(report) + "\n", encoding="utf-8")
        if hasattr(self.actions, "link_report"):
            self.actions.link_report(row["id"], path)
        save(reportId=path.relative_to(self.root).as_posix())
        return self.history.get(row["id"])

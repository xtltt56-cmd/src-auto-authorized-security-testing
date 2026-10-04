"""Manual Dashboard entry, one worker, no scheduler or daemon."""
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from .agent_actions import LocalActions
from .agent_contracts import Limits, CATALOG_VERSION
from .agent_provider import configured_model
from .agent_runner import ACTIVE, AgentHistory, AgentRunner
from .store import Store
from .config import load_mapping
from .agent_resources import WindowsResources


class AgentService:
    def __init__(self, root, control, model_factory=configured_model, action_factory=LocalActions):
        self.root, self.control = Path(root).resolve(), control
        self.history = AgentHistory(self.root)
        self.model_factory, self.action_factory = model_factory, action_factory
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="src-auto-agent")
        self.enabled = False  # Deliberately session-only; opening/restarting never enables it.
        self.current_id = None
        self.cancel = threading.Event()

    @property
    def active(self):
        return self.current_id is not None or any(x["state"] in ACTIVE for x in self.history.list())

    def close(self):
        self.cancel.set()
        self.executor.shutdown(wait=False)

    def set_enabled(self, value):
        with self.control._lock:
            if self.control._closing: raise RuntimeError("dashboard_closing")
            self.enabled = value
            if not value: self.cancel.set()
            return {"enabled": self.enabled}

    def snapshot(self, remote_session_enabled):
        with self.control._lock:
            runs = self.history.list()
            active_id = self.current_id or next((x["id"] for x in runs if x["state"] in ACTIVE), None)
            return {"enabled": self.enabled, "remoteSessionEnabled": remote_session_enabled,
                    "cloudAgentAvailable": False,
                    "activeId": active_id, "ownedActiveId": self.current_id, "runs": runs, "catalogVersion": CATALOG_VERSION,
                    "limits": Limits().to_mapping(), "localOnly": True}

    def start(self, document, remote_session_enabled):
        required = {"labId", "mode", "provider"}
        if not isinstance(document, dict) or not required <= set(document) or set(document) - required - {"allowCloud", "limits", "resumeId", "candidateId"}:
            raise ValueError("invalid_agent_request")
        lab, mode, provider = document["labId"], document["mode"], document["provider"]
        if not all(isinstance(x, str) for x in (lab, mode, provider)): raise ValueError("invalid_agent_request")
        if mode not in {"candidate-review", "api-permissions"} or provider not in {"local", "deepseek", "zhipu", "openrouter"}:
            raise ValueError("invalid_agent_request")
        if type(document.get("allowCloud", False)) is not bool: raise ValueError("invalid_agent_request")
        if provider != "local" and not (remote_session_enabled and document.get("allowCloud") is True):
            raise ValueError("remote_ai_disabled_for_session")
        if provider != "local":
            # Staged rollout: existing manual AI reviews remain separate. Do not enable
            # a potentially billed autonomous loop before its cost governance is accepted.
            raise ValueError("cloud_agent_not_validated")
        limits = Limits.from_mapping(document.get("limits", {}))
        with self.control._lock:
            if not self.enabled: raise RuntimeError("agent_disabled")
            if self.control._closing: raise RuntimeError("dashboard_closing")
            if self.active or self.control.lifecycle()["activeWork"]: raise RuntimeError("agent_operation_conflict")
            self.control.manager.spec(lab)
            if self.control.manager.status(lab).get("status") != "READY": raise RuntimeError("lab_not_ready")
            if mode == "api-permissions" and lab != "business-api": raise ValueError("permission_recipe_unavailable")
            candidate = None
            candidate_id = document.get("candidateId")
            if candidate_id is not None:
                if not isinstance(candidate_id, str) or not candidate_id.isdigit(): raise ValueError("foreign_candidate")
                store = Store(self.root / "data/src_auto.sqlite3")
                try:
                    candidate = next((x for x in store.list_findings() if str(x["id"]) == candidate_id), None)
                finally: store.close()
                spec_url = urlsplit(self.control.manager.spec(lab).health_url)
                candidate_url = urlsplit(str(candidate.get("url", ""))) if candidate else None
                if not candidate_url or (candidate_url.scheme, candidate_url.hostname, candidate_url.port) != (spec_url.scheme, spec_url.hostname, spec_url.port):
                    raise ValueError("foreign_candidate")
            cancel = threading.Event()
            actions = self.action_factory(self.root, self.control.manager, lab, limits, cancel, candidate=candidate)
            model = self.model_factory(self.root, provider, remote_session_enabled, document.get("allowCloud", False))
            resume_id = document.get("resumeId")
            if resume_id:
                if not isinstance(resume_id, str): raise ValueError("invalid_agent_request")
                row = self.history.get(resume_id)
                if row["state"] not in {"paused", "interrupted"}: raise ValueError("agent_not_resumable")
                if (row["labId"], row["mode"], row["provider"], row["scopeHash"], row["configHash"], row["catalogVersion"], row.get("candidateId")) != (
                        lab, mode, provider, actions.scope_hash, actions.config_hash, CATALOG_VERSION, candidate_id):
                    raise ValueError("resume_context_changed")
                limits = Limits.from_mapping(row["limits"])
                actions.client.limits = limits
            else:
                row = self.history.create(lab, mode, provider, limits, actions)
                self.history.update(row["id"], candidateId=candidate_id)
            self.current_id, self.cancel = row["id"], cancel
            resources = WindowsResources(load_mapping(self.root / "config/policy.yaml"))
            runner = AgentRunner(self.root, self.history, model, actions, limits, provider, resource_check=resources.check)
            try:
                self.executor.submit(self._run, runner, row["id"], lab, mode, cancel, resume_id)
            except Exception:
                self.current_id = None
                self.history.update(row["id"], state="failed", reason="queue_unavailable")
                raise RuntimeError("queue_unavailable")
            return {"accepted": True, "id": row["id"]}

    def _run(self, runner, key, lab, mode, cancel, resume_id):
        try:
            runner.run(lab, mode, cancel, resume_id=resume_id, run_id=None if resume_id else key)
        except Exception:
            # A competing service may have won an atomic resume claim. Do not rewrite its task.
            row = self.history.get(key)
            if row.get("owner") == self.history.owner:
                self.history.update(key, state="failed", reason="execution_failed")
        finally:
            with self.control._lock:
                self.current_id = None

    def cancel_run(self, key):
        with self.control._lock:
            if not isinstance(key, str) or key != self.current_id: raise ValueError("agent_not_running")
            self.cancel.set()
            self.history.update(key, state="cancelling", reason="operator_stop")
            return {"accepted": True, "id": key}

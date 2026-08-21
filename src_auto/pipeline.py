from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .ai import AITriage
from .controls import DiskGuard, ResourceGuard, StopController
from .models import ScopeDecision
from .reporting import ButianReportGenerator, EvidencePackager
from .scope import ScopeGuard
from .store import Store


STAGES = [
    "asset_discovery",
    "http_probe",
    "crawl",
    "candidate_scan",
    "passive_scan",
    "normalize",
    "dedup",
    "triage",
    "evidence",
    "report",
]


class PipelineRunner:
    def __init__(
        self,
        store: Store,
        scope_guard: ScopeGuard,
        root: Path,
        ai_triage: Optional[AITriage] = None,
        disk_guard: Optional[DiskGuard] = None,
        resource_guard: Optional[ResourceGuard] = None,
        stop_controller: Optional[StopController] = None,
    ):
        self.store = store
        self.scope_guard = scope_guard
        self.root = Path(root)
        self.ai_triage = ai_triage or AITriage()
        self.disk_guard = disk_guard or DiskGuard(self.root)
        self.resource_guard = resource_guard or ResourceGuard()
        self.stop_controller = stop_controller or StopController(self.root / "STOP")

    def _guard(self, run_id: str) -> Optional[Dict[str, Any]]:
        disk = self.disk_guard.check()
        self.store.record_event(run_id, "info", "disk_guard", disk)
        if not disk["allowed"]:
            self.store.set_run_status(run_id, "blocked_disk")
            return {"status": "blocked_disk", "stages": []}
        resource = self.resource_guard.check()
        self.store.record_event(run_id, "info", "resource_guard", resource)
        if not resource["allowed"]:
            self.store.set_run_status(run_id, "paused_resource")
            return {"status": "paused_resource", "stages": []}
        return None

    def _stop_if_requested(self, run_id: str, completed: List[str]) -> Optional[Dict[str, Any]]:
        if self.stop_controller.requested():
            self.store.set_run_status(run_id, "stopped")
            self.store.record_event(run_id, "warning", "manual_stop", {"completed": completed})
            return {"status": "stopped", "stages": list(completed)}
        return None

    def run_local(self, run_id: str, fixture: Mapping[str, Any]) -> Dict[str, Any]:
        blocked = self._guard(run_id)
        if blocked:
            return blocked
        self.store.set_run_status(run_id, "running")
        completed: List[str] = []
        raw_findings: List[Dict[str, Any]] = []
        try:
            for stage in STAGES:
                stopped = self._stop_if_requested(run_id, completed)
                if stopped:
                    return stopped
                if stage == "asset_discovery":
                    self.store.snapshot_assets(run_id, fixture.get("assets", []))
                elif stage == "http_probe":
                    self.store.record_event(run_id, "info", "local_http_fixture", {"count": len(fixture.get("urls", []))})
                elif stage == "crawl":
                    self.store.save_checkpoint(run_id, stage, {"urls": list(fixture.get("urls", []))})
                elif stage == "candidate_scan":
                    raw_findings = [dict(item) for item in fixture.get("findings", [])]
                elif stage == "passive_scan":
                    self.store.record_event(run_id, "info", "passive_fixture", {"headers": fixture.get("headers", {})})
                elif stage == "normalize":
                    normalized = []
                    for item in raw_findings:
                        item["run_id"] = run_id
                        url = str(item.get("url", ""))
                        decision: ScopeDecision = self.scope_guard.decide(url)
                        if decision.allowed:
                            normalized.append(item)
                        else:
                            self.store.record_event(run_id, "warning", "finding_out_of_scope", {"url": url, "reason": decision.reason})
                    raw_findings = normalized
                elif stage == "dedup":
                    for finding in raw_findings:
                        self.store.insert_finding(finding)
                elif stage == "triage":
                    for finding in self.store.list_findings(run_id):
                        triage = self.ai_triage.classify(finding)
                        self.store.update_finding_triage(finding["fingerprint"], triage, "triaged")
                elif stage == "evidence":
                    for finding in self.store.list_findings(run_id):
                        EvidencePackager(self.root, self.store).package(run_id, finding)
                elif stage == "report":
                    findings = self.store.list_findings(run_id)
                    report_path = ButianReportGenerator(self.root, self.store).generate(
                        run_id, self.scope_guard.policy.digest(), findings
                    )
                    self.store.save_checkpoint(run_id, stage, {"report_path": str(report_path)})
                completed.append(stage)
                self.store.save_checkpoint(run_id, stage, {"status": "completed"})
            self.store.set_run_status(run_id, "completed")
            return {"status": "completed", "stages": completed, "finding_count": len(self.store.list_findings(run_id))}
        except Exception as exc:
            self.store.set_run_status(run_id, "failed")
            self.store.record_event(run_id, "error", "pipeline_failed", {"error": str(exc), "stage": completed[-1] if completed else ""})
            raise

    def run_external(
        self,
        run_id: str,
        target_urls: Iterable[str],
        adapters: Optional[Mapping[str, Any]] = None,
        execute: bool = False,
    ) -> Dict[str, Any]:
        """Run an explicitly wired tool sequence only after a confirmed scope and execute flag.

        The CLI deliberately leaves ``execute`` false. A future operator can inject
        SafeToolAdapter instances after reviewing the current platform rules.
        """
        if not self.scope_guard.policy.confirmed or not self.scope_guard.policy.allow_network_contact:
            self.store.set_run_status(run_id, "blocked_scope")
            return {"status": "blocked_scope", "stages": []}
        target_urls = list(target_urls)
        for url in target_urls:
            self.scope_guard.assert_allowed(url)
        if not execute:
            self.store.set_run_status(run_id, "awaiting_adapter")
            self.store.record_event(run_id, "info", "external_pipeline_not_started", {"reason": "manual_adapter_gate"})
            return {"status": "awaiting_adapter", "stages": []}
        if not adapters:
            self.store.set_run_status(run_id, "blocked_adapter")
            return {"status": "blocked_adapter", "reason": "adapter_configuration_required", "stages": []}
        sequence = ["bbot", "subfinder", "httpx", "katana", "nuclei", "zap", "reconftw"]
        results = []
        for name in sequence:
            adapter = adapters.get(name)
            if adapter is None:
                self.store.set_run_status(run_id, "blocked_adapter")
                return {"status": "blocked_adapter", "reason": "missing_" + name, "stages": results}
            result = adapter.run([], self.scope_guard, target_urls=target_urls)
            result_dict = getattr(result, "__dict__", result)
            results.append({"tool": name, "result": result_dict})
            self.store.record_event(run_id, "info", "external_tool", {"tool": name, "result": result_dict})
            self.store.save_checkpoint(run_id, "tool_" + name, {"status": result_dict.get("status", "unknown")})
            if result_dict.get("status") != "completed":
                self.store.set_run_status(run_id, "tool_error")
                return {"status": "tool_error", "stages": results}
        self.store.set_run_status(run_id, "completed_tools")
        return {"status": "completed_tools", "stages": results}

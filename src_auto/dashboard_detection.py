"""Bounded, real detection workflow for project-owned loopback labs.

The workflow deliberately uses the fixed local-lab inventory.  It performs
live loopback requests, persists candidate findings and generates a report,
but it never accepts an arbitrary URL and never calls a remote AI service.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .api_schema import run_local_schema_smoke
from .business_api_lab import run_authorization_matrix
from .juice_shop import probe_local_target
from .local_discovery import discover_local_surface
from .reporting import ButianReportGenerator
from .runtime_policy import RuntimePolicy
from .store import Store


ProgressCallback = Callable[[str, int, Dict[str, int], str, str], None]


def _empty_counters() -> Dict[str, int]:
    return {"endpoints": 0, "api": 0, "candidates": 0, "blocked": 0, "errors": 0}


def _scope_digest(policy: RuntimePolicy, lab_id: str, target_url: str) -> str:
    payload = {
        "lab_id": str(lab_id),
        "target_url": str(target_url),
        "policy": dict(policy.to_mapping()),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _passive_header_candidates(run_id: str, target_url: str, probe: Mapping[str, Any]):
    headers = probe.get("headers", {}) if isinstance(probe.get("headers"), Mapping) else {}
    checks = (
        ("content-security-policy", "缺少 Content-Security-Policy 响应头", "info"),
        ("x-content-type-options", "缺少 X-Content-Type-Options 响应头", "low"),
        ("x-frame-options", "缺少 X-Frame-Options 响应头", "low"),
    )
    findings = []
    for header, title, severity in checks:
        if str(headers.get(header, "")).strip():
            continue
        findings.append(
            {
                "run_id": run_id,
                "title": title,
                "url": target_url,
                "parameter": "response-header:{}".format(header),
                "severity": severity,
                "evidence": "对固定回环入口执行只读 GET；响应元数据中未观察到 {}。未保存响应正文。".format(header),
                "status": "candidate",
                "triage": {
                    "disposition": "manual_review",
                    "confirmed": False,
                    "source": "bounded-loopback-passive-check",
                },
            }
        )
    return findings


class LocalDetectionWorkflow:
    """Execute one operator-triggered, local-only detection run."""

    def __init__(
        self,
        project_root: Path,
        manager: Any,
        probe_fn: Callable[..., Mapping[str, Any]] = probe_local_target,
        discover_fn: Callable[..., Mapping[str, Any]] = discover_local_surface,
        business_matrix_fn: Callable[[str], Mapping[str, Any]] = run_authorization_matrix,
        schema_smoke_fn: Callable[..., Mapping[str, Any]] = run_local_schema_smoke,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.manager = manager
        self.probe_fn = probe_fn
        self.discover_fn = discover_fn
        self.business_matrix_fn = business_matrix_fn
        self.schema_smoke_fn = schema_smoke_fn

    def run(
        self,
        lab_id: str,
        cancel_event: threading.Event,
        progress: ProgressCallback,
    ) -> Dict[str, Any]:
        spec = self.manager.spec(lab_id)
        counters = _empty_counters()
        if cancel_event.is_set():
            return {"status": "cancelled", "networkContact": "none"}

        policy = RuntimePolicy.from_file(self.root / "config" / "validation" / "local_only.json")
        target_url = str(spec.health_url)
        allowed, reason = policy.decide_url(target_url)
        if not allowed:
            return {"status": "blocked", "reason": reason, "networkContact": "none"}
        if str(self.manager.status(lab_id).get("status", "")) != "READY":
            return {"status": "blocked", "reason": "lab_not_ready", "networkContact": "none"}

        progress("范围预检", 8, dict(counters), "固定靶场与回环范围校验通过", "info")
        if cancel_event.is_set():
            return {"status": "cancelled", "networkContact": "none"}

        store = Store(self.root / "data" / "src_auto.sqlite3")
        run_id = store.create_run("local-{}".format(lab_id), _scope_digest(policy, lab_id, target_url), mode="local")
        try:
            store.set_run_status(run_id, "running")
            progress("可达性探测", 20, dict(counters), "正在执行单次只读回环探测", "info")
            probe = dict(self.probe_fn(policy, target_url))
            if str(probe.get("status", "")) != "reachable":
                store.set_run_status(run_id, "blocked_dependency")
                counters["blocked"] += 1
                progress("可达性探测", 20, dict(counters), "靶场入口当前不可达，检测已停止", "warning")
                return {
                    "status": "blocked", "reason": "target_unreachable", "runId": run_id,
                    "networkContact": "loopback" if probe.get("network_contact") else "none",
                }
            if cancel_event.is_set():
                store.set_run_status(run_id, "cancelled")
                return {"status": "cancelled", "runId": run_id, "networkContact": "loopback"}

            progress("表面发现", 40, dict(counters), "正在读取入口页面与同源脚本中的有限路由", "info")
            discovery = dict(self.discover_fn(policy, target_url))
            if str(discovery.get("status", "")) != "COMPLETED":
                store.record_event(run_id, "warning", "surface_discovery_degraded", {"reason": str(discovery.get("reason", ""))[:160]})
            discovered = discovery.get("discovered_urls", []) if isinstance(discovery.get("discovered_urls"), list) else []
            api_urls = discovery.get("api_urls", []) if isinstance(discovery.get("api_urls"), list) else []
            excluded = discovery.get("external_urls_excluded", []) if isinstance(discovery.get("external_urls_excluded"), list) else []
            counters.update(endpoints=len(discovered), api=len(api_urls), blocked=len(excluded))
            progress("表面发现", 48, dict(counters), "已完成有限表面发现；外部链接只记录为已排除", "success")
            if cancel_event.is_set():
                store.set_run_status(run_id, "cancelled")
                return {"status": "cancelled", "runId": run_id, "networkContact": "loopback"}

            progress("候选检测", 62, dict(counters), "正在执行无破坏性的响应头与业务边界检查", "info")
            findings = _passive_header_candidates(run_id, target_url, probe)
            if lab_id == "business-api":
                matrix = dict(self.business_matrix_fn("http://127.0.0.1:8084"))
                store.save_checkpoint(run_id, "business_authorization_matrix", {
                    "status": str(matrix.get("status", "")),
                    "disposition": str(matrix.get("disposition", "")),
                    "response_statuses": dict(matrix.get("response_statuses", {})),
                    "body_fingerprints": dict(matrix.get("body_fingerprints", {})),
                    "raw_bodies_retained": False,
                })
                if matrix.get("disposition") == "candidate_broken_object_authorization":
                    findings.append(
                        {
                            "run_id": run_id,
                            "title": "对象级授权边界可能失效（IDOR 候选）",
                            "url": "http://127.0.0.1:8084/api/v1/orders/order-a",
                            "parameter": "order_id",
                            "severity": "high",
                            "evidence": "固定测试账号的所有者与同级账号得到等价对象指纹；匿名请求状态为 {}。未保留响应正文。".format(
                                matrix.get("response_statuses", {}).get("anonymous", "unknown")
                            ),
                            "status": "candidate",
                            "triage": {
                                "disposition": "manual_review",
                                "confirmed": False,
                                "source": "bounded-authorization-matrix",
                            },
                        }
                    )
            elif lab_id == "vampi":
                output_dir = self.root / "validation" / "dashboard_detection" / run_id / "schemathesis"
                schema = dict(self.schema_smoke_fn(
                    self.root, "http://127.0.0.1:8083/openapi.json", output_dir
                ))
                store.save_checkpoint(run_id, "schema_smoke", {
                    "status": str(schema.get("status", "")),
                    "reason": str(schema.get("reason", "")),
                    "manual_review_required": bool(schema.get("manual_review_required", False)),
                    "request_profile": str(schema.get("request_profile", "")),
                })
                if schema.get("status") == "POSSIBLE_SCHEMA_CONTRACT_ISSUES":
                    findings.append(
                        {
                            "run_id": run_id,
                            "title": "OpenAPI 示例契约存在候选异常",
                            "url": "http://127.0.0.1:8083/openapi.json",
                            "parameter": "openapi-examples",
                            "severity": "low",
                            "evidence": "仅执行 GET/examples、单 worker 的本地契约检查；结果需要人工复核。",
                            "status": "candidate",
                            "triage": {"disposition": "manual_review", "confirmed": False, "source": "bounded-schema-smoke"},
                        }
                    )
                elif schema.get("status") == "FAILED_RUNTIME":
                    counters["errors"] += 1
                    store.record_event(run_id, "warning", "schema_smoke_unavailable", {"reason": str(schema.get("reason", ""))[:160]})

            if cancel_event.is_set():
                store.set_run_status(run_id, "cancelled")
                return {"status": "cancelled", "runId": run_id, "networkContact": "loopback"}

            progress("结果入库", 82, dict(counters), "正在保存候选指纹和最小证据", "info")
            for finding in findings:
                store.insert_finding(finding)
            counters["candidates"] = len(store.list_findings(run_id))
            store.save_checkpoint(run_id, "detection_summary", {
                "target": target_url,
                "endpoint_count": counters["endpoints"],
                "api_count": counters["api"],
                "candidate_count": counters["candidates"],
                "external_excluded_count": counters["blocked"],
                "remote_ai_calls": 0,
                "auto_submission": False,
            })

            progress("报告生成", 94, dict(counters), "正在生成与本次运行关联的人工复核草稿", "info")
            report = ButianReportGenerator(self.root, store).generate(
                run_id, _scope_digest(policy, lab_id, target_url), store.list_findings(run_id)
            )
            store.set_run_status(run_id, "completed")
            report_id = report.relative_to(self.root).as_posix()
            progress("检测完成", 100, dict(counters), "检测完成；候选仍需人工复核，不会自动提交", "success")
            return {
                "status": "completed",
                "runId": run_id,
                "reportId": report_id,
                "candidateCount": counters["candidates"],
                "endpointCount": counters["endpoints"],
                "apiCount": counters["api"],
                "blockedCount": counters["blocked"],
                "errorCount": counters["errors"],
                "networkContact": "loopback",
            }
        except Exception:
            store.set_run_status(run_id, "failed")
            store.record_event(run_id, "error", "dashboard_detection_failed", {"detail": "redacted_runtime_error"})
            raise
        finally:
            store.close()


__all__ = ["LocalDetectionWorkflow"]

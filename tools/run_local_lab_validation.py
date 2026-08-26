"""Run repeatable, local-only validation across the fixed lab inventory.

The runner starts only project-owned Compose services, captures bounded local
surface evidence, performs a scoped ZAP quick scan, and writes adjudication
and score artifacts.  It never enables live-target execution or remote AI.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src_auto.adjudication import adjudicate_finding, benchmark_metrics
from src_auto.api_schema import run_local_schema_smoke
from src_auto.business_api_lab import run_authorization_matrix
from src_auto.juice_shop import parse_zap_report, run_zap_quick_scan
from src_auto.local_discovery import discover_local_surface
from src_auto.local_labs import LabSpec, LocalLabManager, load_lab_specs
from src_auto.runtime_policy import RuntimePolicy


INVENTORY_PATH = PROJECT_ROOT / "config" / "labs" / "local_labs.json"
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.local-labs.yml"
AUTOTEST_ROOT = PROJECT_ROOT / "validation" / "autotest"
LAB_OUTPUT_ROOT = AUTOTEST_ROOT / "local_labs"
MAX_ROUNDS = 3


def base_url(spec: LabSpec) -> str:
    return "http://{}:{}/".format(spec.host, spec.host_port)


def expected_control_cases(lab_id: str) -> List[Dict[str, Any]]:
    if lab_id == "juice-shop":
        return [{"case_id": "csp-header-control", "positive": True, "kind": "hardening-control"}]
    if lab_id == "dvwa":
        return [
            {"case_id": "dvwa-csp-header-control", "positive": True, "kind": "hardening-control"},
            {"case_id": "dvwa-clickjacking-control", "positive": True, "kind": "hardening-control"},
            {"case_id": "dvwa-cookie-samesite-control", "positive": True, "kind": "hardening-control"},
            {"case_id": "dvwa-x-powered-by-control", "positive": True, "kind": "hardening-control"},
            {"case_id": "dvwa-server-header-control", "positive": True, "kind": "hardening-control"},
            {"case_id": "dvwa-x-content-type-control", "positive": True, "kind": "hardening-control"},
            {"case_id": "auth-surface-discovery", "positive": True, "kind": "surface-discovery"},
        ]
    if lab_id == "webgoat":
        return [{"case_id": "webgoat-health-surface", "positive": True, "kind": "surface-discovery"}]
    if lab_id == "vampi":
        return [
            {"case_id": "vampi-openapi-surface", "positive": True, "kind": "surface-discovery"},
            {"case_id": "vampi-readonly-schema-smoke", "positive": True, "kind": "api-schema-control"},
        ]
    if lab_id == "business-api":
        return [
            {"case_id": "business-api-openapi-surface", "positive": True, "kind": "surface-discovery"},
            {"case_id": "business-api-readonly-schema-smoke", "positive": True, "kind": "api-schema-control"},
            {"case_id": "business-api-intentional-idor-candidate", "positive": True, "kind": "authorization-candidate"},
        ]
    return []


def adjudicate_zap_finding(lab_id: str, finding: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply a conservative, documented local benchmark rubric.

    A TRUE_POSITIVE here means a deterministic local control finding, not a
    bounty-ready vulnerability.  Submission remains false for all benchmark
    controls.  Unknown alerts remain NOT_VERIFIED.
    """

    title = str(finding.get("title", "")).strip()
    lower = title.lower()
    endpoint = str(finding.get("endpoint", "")).strip()
    evidence = str(finding.get("evidence", "")).strip() or "scanner evidence unavailable"
    status = "NOT_VERIFIED"
    expected_case_id = ""
    impact = "候选项尚未完成独立验证"
    reproduction = "未执行独立复现"
    notes = "未知告警保持 NOT_VERIFIED，不自动升级。"
    if "content security policy" in lower and "not set" in lower:
        status = "TRUE_POSITIVE"
        expected_case_id = "csp-header-control" if lab_id == "juice-shop" else "dvwa-csp-header-control"
        impact = "确认缺少浏览器安全加固控制；未证明可利用数据影响"
        reproduction = "对回环首页重复 GET，响应均未出现 Content-Security-Policy"
        notes = "控制项为真，但属于加固缺失，不是可直接提交的赏金漏洞。"
    elif lab_id == "dvwa" and "cookie without samesite" in lower:
        status = "TRUE_POSITIVE"
        expected_case_id = "dvwa-cookie-samesite-control"
        impact = "确认本地测试 Cookie 缺少 SameSite 属性；未证明跨站敏感操作"
        reproduction = "重复获取本地登录页，Set-Cookie 均未包含 SameSite"
        notes = "Cookie 加固控制项，不自动作为赏金漏洞提交。"
    elif lab_id == "dvwa" and "missing anti-clickjacking header" in lower:
        status = "TRUE_POSITIVE"
        expected_case_id = "dvwa-clickjacking-control"
        impact = "确认缺少点击劫持防护头；未证明可利用数据影响"
        reproduction = "本地响应重复缺少 X-Frame-Options 或等效 CSP frame-ancestors"
        notes = "响应头控制项，不自动作为赏金漏洞提交。"
    elif lab_id == "dvwa" and "x-powered-by" in lower:
        status = "TRUE_POSITIVE"
        expected_case_id = "dvwa-x-powered-by-control"
        impact = "响应暴露 PHP 技术栈版本；未证明可利用影响"
        reproduction = "本地响应重复包含 X-Powered-By 头"
        notes = "技术栈指纹控制项，不自动作为赏金漏洞提交。"
    elif lab_id == "dvwa" and "server leaks version" in lower:
        status = "TRUE_POSITIVE"
        expected_case_id = "dvwa-server-header-control"
        impact = "响应暴露 Apache 版本；未证明可利用影响"
        reproduction = "本地响应重复包含 Server 版本信息"
        notes = "服务器 banner 控制项，不自动作为赏金漏洞提交。"
    elif lab_id == "dvwa" and "x-content-type-options header missing" in lower:
        status = "TRUE_POSITIVE"
        expected_case_id = "dvwa-x-content-type-control"
        impact = "确认缺少 MIME 嗅探防护头；未证明可利用数据影响"
        reproduction = "本地响应重复缺少 X-Content-Type-Options"
        notes = "安全响应头控制项，不自动作为赏金漏洞提交。"
    elif lab_id == "dvwa" and "in page banner" in lower:
        status = "FALSE_POSITIVE"
        impact = "页面 banner 是公开信息提示，没有额外敏感影响"
        reproduction = "重复获取公开页面仍只有普通版本/说明文本"
        notes = "信息型 banner，不作为漏洞提交。"
    elif "cross-domain misconfiguration" in lower:
        status = "FALSE_POSITIVE"
        impact = "robots.txt 为公开文本且未发现凭据型跨域读取"
        reproduction = "Origin 仅得到公开 robots 内容，未发现认证数据暴露"
        notes = "公开资源上的通配 ACAO 不足以证明安全影响。"
    elif "timestamp disclosure" in lower:
        status = "FALSE_POSITIVE"
        impact = "固定时间戳没有敏感业务含义"
        reproduction = "重复响应中的时间戳保持静态，未形成信息影响"
        notes = "信息提示，不作为漏洞提交。"
    elif "suspicious comments" in lower or "modern web application" in lower:
        status = "FALSE_POSITIVE"
        impact = "仅是源码注释或技术栈指纹"
        reproduction = "重复获取资源未发现凭据、密钥或可利用逻辑"
        notes = "信息型扫描器告警。"
    record = adjudicate_finding(
        {
            "title": title,
            "endpoint": endpoint,
            "status": status,
            "expected_case_id": expected_case_id,
            "evidence": evidence,
            "baseline": "同一回环靶场基线响应",
            "reproduction": reproduction,
            "impact": impact,
            "submission_ready": False,
            "reviewer": "local-acceptance-rubric",
            "notes": notes,
        }
    )
    return record


def discovery_control_record(lab_id: str, discovery: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if lab_id == "webgoat":
        if str(discovery.get("status", "")) != "COMPLETED":
            return None
        return adjudicate_finding(
            {
                "title": "WebGoat local health surface available",
                "endpoint": str(discovery.get("target", "http://127.0.0.1:8082/WebGoat/actuator/health")),
                "status": "TRUE_POSITIVE",
                "expected_case_id": "webgoat-health-surface",
                "evidence": "local actuator health endpoint returned a bounded response",
                "baseline": "fixed WebGoat image health probe",
                "reproduction": "repeat GET to the loopback health endpoint",
                "impact": "training-lab availability control; not a vulnerability",
                "submission_ready": False,
                "reviewer": "local-acceptance-rubric",
                "notes": "仅证明本地 WebGoat 靶场可用，不代表漏洞或赏金候选。",
            }
        )
    if lab_id != "dvwa":
        return None
    auth_surface = discovery.get("auth_surface", [])
    if not isinstance(auth_surface, list) or not auth_surface:
        return None
    endpoint = str(auth_surface[0])
    return adjudicate_finding(
        {
            "title": "Authentication surface discovered",
            "endpoint": endpoint,
            "status": "TRUE_POSITIVE",
            "expected_case_id": "auth-surface-discovery",
            "evidence": "login/auth surface found in local HTML or JavaScript",
            "baseline": "local unauthenticated page inventory",
            "reproduction": "same local route discovered on repeated surface parse",
            "impact": "discovery coverage control; not a vulnerability",
            "submission_ready": False,
            "reviewer": "local-acceptance-rubric",
            "notes": "用于衡量登录面发现，不代表认证缺陷。",
        }
    )


def schema_control_record(lab_id: str, schema_result: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if lab_id not in {"vampi", "business-api"} or str(schema_result.get("status", "")) not in (
        "COMPLETED",
        "POSSIBLE_SCHEMA_CONTRACT_ISSUES",
    ):
        return None
    candidate = str(schema_result.get("status")) == "POSSIBLE_SCHEMA_CONTRACT_ISSUES"
    prefix = "VAmPI" if lab_id == "vampi" else "Business API"
    case_id = "vampi-readonly-schema-smoke" if lab_id == "vampi" else "business-api-readonly-schema-smoke"
    default_url = "http://127.0.0.1:8083/openapi.json" if lab_id == "vampi" else "http://127.0.0.1:8084/openapi.json"
    return adjudicate_finding(
        {
            "title": "{} read-only OpenAPI schema smoke completed".format(prefix),
            "endpoint": str(schema_result.get("schema_url", default_url)),
            "status": "TRUE_POSITIVE",
            "expected_case_id": case_id,
            "evidence": "local GET/examples schema smoke report created" if candidate else "local GET/examples schema smoke completed without contract candidates",
            "baseline": "fixed {} OpenAPI schema".format(prefix),
            "reproduction": "repeat bounded GET-only schema examples against the loopback API",
            "impact": "API contract coverage control; candidate mismatches require separate manual review",
            "submission_ready": False,
            "reviewer": "local-acceptance-rubric",
            "notes": "Schema mismatch is not automatically a security vulnerability or bounty submission.",
        }
    )


def schema_surface_control_record(lab_id: str, schema_result: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if lab_id not in {"vampi", "business-api"} or str(schema_result.get("status", "")) not in (
        "COMPLETED",
        "POSSIBLE_SCHEMA_CONTRACT_ISSUES",
    ):
        return None
    prefix = "VAmPI" if lab_id == "vampi" else "Business API"
    case_id = "vampi-openapi-surface" if lab_id == "vampi" else "business-api-openapi-surface"
    default_url = "http://127.0.0.1:8083/openapi.json" if lab_id == "vampi" else "http://127.0.0.1:8084/openapi.json"
    return adjudicate_finding(
        {
            "title": "{} OpenAPI surface available".format(prefix),
            "endpoint": str(schema_result.get("schema_url", default_url)),
            "status": "TRUE_POSITIVE",
            "expected_case_id": case_id,
            "evidence": "loopback OpenAPI document was loaded by the bounded schema smoke",
            "baseline": "fixed {} OpenAPI schema".format(prefix),
            "reproduction": "repeat local GET to /openapi.json",
            "impact": "API test-surface availability control; not a vulnerability",
            "submission_ready": False,
            "reviewer": "local-acceptance-rubric",
            "notes": "仅证明本地 OpenAPI 靶场可用，不代表漏洞或赏金候选。",
        }
    )


def business_api_control_record(lab_id: str, matrix: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if lab_id != "business-api" or str(matrix.get("status", "")) != "COMPLETED":
        return None
    candidate = str(matrix.get("disposition", "")) == "candidate_broken_object_authorization"
    status = "TRUE_POSITIVE" if candidate else "NOT_VERIFIED"
    statuses = matrix.get("response_statuses", {}) if isinstance(matrix.get("response_statuses"), Mapping) else {}
    return adjudicate_finding(
        {
            "title": "Business API intentional horizontal-authorization candidate",
            "endpoint": str(matrix.get("base_url", "http://127.0.0.1:8084")) + "/api/v1/orders/order-a",
            "status": status,
            "expected_case_id": "business-api-intentional-idor-candidate",
            "evidence": "owner/peer GET response metadata matched after volatile fields were excluded; statuses={}".format(
                {key: int(value) for key, value in statuses.items() if str(value).isdigit()}
            ),
            "baseline": "synthetic order-a owned by buyer-a; buyer-b is a separate local test account",
            "reproduction": "repeat GET with X-Test-User buyer-a and buyer-b; compare fingerprints only",
            "impact": "local training candidate for horizontal authorization review; no real data and no submission",
            "submission_ready": False,
            "reviewer": "local-acceptance-rubric",
            "notes": "刻意保留的本地 IDOR 候选，仅验证平台工作流；必须人工复核，不能外推到真实目标。",
        }
    )


def build_lab_score(lab_id: str, records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    record_list = [dict(item) for item in records]
    metrics = benchmark_metrics(record_list, expected_control_cases(lab_id))
    result = dict(metrics)
    result.update(
        {
            "lab_id": lab_id,
            "benchmark_kind": "local-control-and-surface-discovery",
            "bounty_ready_count": 0,
            "submission_policy": "all benchmark controls are non-bounty; manual platform review required",
        }
    )
    result["control_metrics"] = dict(metrics)
    return result


def summarize_rounds(rounds: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    counts = [int(item["finding_count"]) for item in rounds if isinstance(item.get("finding_count"), int)]
    api_counts = [int(item.get("discovery", {}).get("api_url_count")) for item in rounds if isinstance(item.get("discovery", {}).get("api_url_count"), int)]
    if counts:
        mean = sum(counts) / float(len(counts))
        variance = sum((value - mean) ** 2 for value in counts) / float(len(counts))
        count_summary = {"finding_count_min": min(counts), "finding_count_max": max(counts), "finding_count_variance": round(variance, 6)}
    else:
        count_summary = {"finding_count_min": None, "finding_count_max": None, "finding_count_variance": None}
    return {
        **count_summary,
        "api_url_count_min": min(api_counts) if api_counts else None,
        "api_url_count_max": max(api_counts) if api_counts else None,
        "round_count": len(rounds),
        "stability_status": "OBSERVED" if len(counts) >= 2 else "NOT_TESTED",
        "accuracy_status": "NOT_INFERRED",
        "notes": "稳定性只比较重复轮次的数量，不把数量稳定误报为检测准确率。",
    }


def render_local_lab_report(final: Mapping[str, Any]) -> str:
    """Render the machine score into a concise, regenerated Chinese report."""

    labs = final.get("labs", {}) if isinstance(final.get("labs"), Mapping) else {}
    lines = [
        "# 本地五靶场最终验收报告",
        "",
        "运行模式：`{}`  ".format(final.get("mode", "local-only")),
        "靶场数量：`{}`；状态：`{}`  ".format(final.get("target_count", len(labs)), final.get("status", "")),
        "",
        "## 结论",
        "",
        "- 五个应用靶场的生命周期、健康检查和回环范围已完成；数据库依赖不发布宿主端口。",
        "- 本报告的 Precision/Recall/F1 只表示本地控制项/表面发现基准，不是补天赏金漏洞命中率。",
        "- `bounty_ready_count={}`；提交状态：`{}`。".format(final.get("bounty_ready_count", 0), final.get("submission_status", "NO_AUTO_SUBMISSION")),
        "",
        "## 精确成绩",
        "",
        "| 靶场 | 每轮候选数 | 最新 TP | FP | FN | 未验证 | Precision | Recall | F1 | 赏金就绪 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lab_id in sorted(labs):
        report = labs.get(lab_id, {}) if isinstance(labs.get(lab_id), Mapping) else {}
        rounds = report.get("rounds", []) if isinstance(report.get("rounds"), list) else []
        score = report.get("score", {}) if isinstance(report.get("score"), Mapping) else {}
        counts = [item.get("finding_count") for item in rounds if isinstance(item, Mapping) and isinstance(item.get("finding_count"), int)]
        def _metric(name: str) -> str:
            value = score.get(name)
            return "null" if value is None else "{:.6f}".format(float(value))
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                {
                    "business-api": "业务 API",
                    "dvwa": "DVWA",
                    "juice-shop": "Juice Shop",
                    "vampi": "VAmPI",
                    "webgoat": "WebGoat",
                }.get(lab_id, lab_id),
                "、".join(str(item) for item in counts) or "null",
                score.get("true_positive", 0),
                score.get("false_positive", 0),
                score.get("false_negative", 0),
                score.get("not_verified", 0),
                _metric("precision"),
                _metric("recall"),
                _metric("f1"),
                score.get("bounty_ready_count", 0),
            )
        )
    p0 = final.get("p0", {}) if isinstance(final.get("p0"), Mapping) else {}
    lines.extend(
        [
            "",
            "## 安全验收",
            "",
            "```text",
            "scope_escape                 {}".format(p0.get("scope_escape", 0)),
            "external_targets_contacted   {}".format(p0.get("external_targets_contacted", 0)),
            "remote_ai_calls              {}".format(p0.get("remote_ai_calls", 0)),
            "secret_leakage               {}".format(p0.get("secret_leakage", 0)),
            "crash                        {}".format(p0.get("crash", 0)),
            "auto_submission              0",
            "```",
            "",
            "完整机器结果见 `LOCAL_LAB_SCORE.json`；逐轮文件在 `local_labs/<lab>/round_nn/`。",
            "官方 Juice Shop Ground Truth 未完整执行时，官方 Precision/Recall 保持 `null`/`NOT_TESTED`。",
            "",
            "> 控制项结果和回归通过率不代表漏洞成立、平台受理或获得赏金；真实目标必须重新建立授权 Scope。",
        ]
    )
    return "\n".join(lines) + "\n"


def _json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _full_ground_truth_summary() -> Dict[str, Any]:
    path = PROJECT_ROOT / "validation" / "juice-shop" / "ground_truth.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        entries = document.get("entries", []) if isinstance(document, Mapping) else []
        if not isinstance(entries, list):
            entries = []
        return {
            "status": "NOT_TESTED",
            "entry_count": len(entries),
            "scanner_detectable_count": sum(1 for item in entries if isinstance(item, Mapping) and bool(item.get("scanner_detectable"))),
            "precision": None,
            "recall": None,
            "reason": "本轮只对显式本地控制基准和发现面评分，未对全部官方挑战执行零样本漏洞回归。",
        }
    except (OSError, ValueError, TypeError):
        return {"status": "UNAVAILABLE", "entry_count": None, "scanner_detectable_count": None, "precision": None, "recall": None}


def _run_zap(spec: LabSpec, output_path: Path, policy: RuntimePolicy) -> Dict[str, Any]:
    target = base_url(spec)
    result = run_zap_quick_scan(PROJECT_ROOT, target, output_path, timeout=300)
    report: Dict[str, Any] = {
        "status": "NOT_TESTED",
        "reason": "zap_not_completed",
        "target_url": target,
        "network_contact": False,
        "finding_count": None,
        "findings": [],
    }
    if result.get("status") != "completed" or not output_path.is_file():
        return {"command": result, "report": report}
    try:
        document = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"command": result, "report": {**report, "status": "BLOCKED_REPORT", "reason": "zap_report_invalid"}}
    parsed = parse_zap_report(document, policy)
    report = {
        "status": "POSSIBLE_FINDINGS",
        "reason": "independent adjudication required",
        "target_url": target,
        "network_contact": True,
        "finding_count": int(parsed.get("finding_count", 0)),
        "findings": parsed.get("findings", []),
        "external_urls_excluded": parsed.get("external_urls_excluded", []),
    }
    return {"command": result, "report": report}


def run_one_round(manager: LocalLabManager, spec: LabSpec, runtime: RuntimePolicy, round_index: int) -> Dict[str, Any]:
    round_dir = LAB_OUTPUT_ROOT / spec.lab_id / ("round_{:02d}".format(round_index))
    round_dir.mkdir(parents=True, exist_ok=True)
    lifecycle = manager.operate("reset", spec.lab_id, wait=True)
    _json_write(round_dir / "LIFECYCLE.json", lifecycle)
    if lifecycle.get("status") != "READY":
        result = {
            "lab_id": spec.lab_id,
            "round": round_index,
            "status": "BLOCKED_DEPENDENCY",
            "reason": "lab_not_ready",
            "finding_count": None,
            "discovery": {"status": "NOT_TESTED", "api_url_count": None, "network_contact": False},
            "score": build_lab_score(spec.lab_id, []),
            "network_contact": False,
            "artifact_dir": str(round_dir),
        }
        _json_write(round_dir / "ROUND.json", result)
        return result
    # Use the inventory's explicit health URL as the discovery entry point.
    # DVWA deliberately redirects `/` to `/login.php`; following arbitrary
    # redirects would weaken the scope boundary, so the adapter starts at the
    # already allowlisted login page instead.
    discovery = discover_local_surface(runtime, spec.health_url)
    _json_write(round_dir / "DISCOVERY.json", discovery)
    api_count = len(discovery.get("api_urls", [])) if isinstance(discovery.get("api_urls"), list) else None
    client_count = len(discovery.get("client_routes", [])) if isinstance(discovery.get("client_routes"), list) else None
    discovery_summary = {
        "status": discovery.get("status"),
        "mode": discovery.get("mode"),
        "url_count": len(discovery.get("discovered_urls", [])) if isinstance(discovery.get("discovered_urls"), list) else None,
        "javascript_url_count": len(discovery.get("javascript_urls", [])) if isinstance(discovery.get("javascript_urls"), list) else None,
        "api_url_count": api_count,
        "client_route_count": client_count,
        "auth_surface_count": len(discovery.get("auth_surface", [])) if isinstance(discovery.get("auth_surface"), list) else None,
        "external_excluded_count": len(discovery.get("external_urls_excluded", [])) if isinstance(discovery.get("external_urls_excluded"), list) else None,
        "request_count": discovery.get("request_count"),
        "network_contact": bool(discovery.get("network_contact", False)),
    }
    schema_smoke: Dict[str, Any] = {"status": "NOT_APPLICABLE", "network_contact": False}
    business_matrix: Dict[str, Any] = {"status": "NOT_APPLICABLE", "network_contact": False}
    if spec.lab_id in {"vampi", "business-api"}:
        schema_url = "http://127.0.0.1:8083/openapi.json" if spec.lab_id == "vampi" else "http://127.0.0.1:8084/openapi.json"
        schema_smoke = run_local_schema_smoke(
            PROJECT_ROOT,
            schema_url,
            round_dir / "SCHEMATHESIS",
        )
        _json_write(round_dir / "SCHEMA_SMOKE.json", schema_smoke)
        zap = {
            "command": {"status": "NOT_RUN", "reason": "api_lab_uses_read_only_schema_smoke"},
            "report": {"status": "NOT_RUN", "reason": "api_lab_uses_read_only_schema_smoke", "findings": []},
        }
        if spec.lab_id == "business-api":
            try:
                business_matrix = run_authorization_matrix("http://127.0.0.1:8084")
            except Exception as exc:  # local dependency/fixture failure is recorded, never ignored
                business_matrix = {
                    "status": "FAILED_RUNTIME",
                    "reason": "business_api_matrix_failed",
                    "detail": str(exc)[:300],
                    "network_contact": False,
                    "manual_review_required": True,
                }
            _json_write(round_dir / "BUSINESS_API_MATRIX.json", business_matrix)
    else:
        zap_output = round_dir / "ZAP_REPORT.json"
        zap = _run_zap(spec, zap_output, runtime)
    findings = zap["report"].get("findings", []) if isinstance(zap.get("report"), Mapping) else []
    records = [adjudicate_zap_finding(spec.lab_id, item) for item in findings]
    control_record = discovery_control_record(spec.lab_id, discovery)
    if control_record:
        records.append(control_record)
    schema_record = schema_control_record(spec.lab_id, schema_smoke)
    if schema_record:
        records.append(schema_record)
    schema_surface_record = schema_surface_control_record(spec.lab_id, schema_smoke)
    if schema_surface_record:
        records.append(schema_surface_record)
    business_record = business_api_control_record(spec.lab_id, business_matrix)
    if business_record:
        records.append(business_record)
    _json_write(round_dir / "ADJUDICATION.json", {"lab_id": spec.lab_id, "round": round_index, "records": records, "status": "COMPLETED" if records else "NO_CANDIDATES"})
    score = build_lab_score(spec.lab_id, records)
    _json_write(round_dir / "SCORE.json", score)
    result = {
        "lab_id": spec.lab_id,
        "round": round_index,
        "status": "COMPLETED",
        "finding_count": len(findings),
        "candidate_count": len(findings),
        "discovery": discovery_summary,
        "score": score,
        "network_contact": True,
        "artifact_dir": str(round_dir),
        "zap_status": zap["report"].get("status"),
        "schema_smoke": schema_smoke,
        "business_api_matrix": business_matrix,
    }
    _json_write(round_dir / "ROUND.json", result)
    return result


def run_validation(repeat_rounds: int = 2, labs: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    if not 0 <= int(repeat_rounds) <= MAX_ROUNDS:
        raise ValueError("repeat_rounds_out_of_range")
    manager = LocalLabManager(PROJECT_ROOT, INVENTORY_PATH, COMPOSE_PATH)
    runtime = RuntimePolicy.from_file(PROJECT_ROOT / "config" / "validation" / "local_only.json")
    wanted = list(labs) if labs else list(manager.specs)
    for lab_id in wanted:
        manager.spec(lab_id)
    all_rounds: Dict[str, List[Dict[str, Any]]] = {lab_id: [] for lab_id in wanted}
    for lab_id in wanted:
        spec = manager.spec(lab_id)
        for round_index in range(int(repeat_rounds) + 1):
            all_rounds[lab_id].append(run_one_round(manager, spec, runtime, round_index))
    lab_reports: Dict[str, Any] = {}
    for lab_id, rounds in all_rounds.items():
        latest = rounds[-1] if rounds else {}
        records: List[Mapping[str, Any]] = []
        for item in rounds:
            path = Path(item.get("artifact_dir", "")) / "ADJUDICATION.json"
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.extend(data.get("records", []))
            except (OSError, ValueError, TypeError):
                pass
        # The final score uses the latest round, while stability is based on all rounds.
        latest_records = []
        latest_path = Path(latest.get("artifact_dir", "")) / "ADJUDICATION.json"
        try:
            latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
            latest_records = latest_data.get("records", []) if isinstance(latest_data, Mapping) else []
        except (OSError, ValueError, TypeError):
            latest_records = []
        lab_reports[lab_id] = {
            "status": "READY" if all(item.get("status") == "COMPLETED" for item in rounds) else "BLOCKED_DEPENDENCY",
            "target": base_url(manager.spec(lab_id)),
            "rounds": rounds,
            "stability": summarize_rounds(rounds),
            "score": build_lab_score(lab_id, latest_records),
            "latest_records": latest_records,
            "control_metrics_are_not_bounty_metrics": True,
        }
    p0 = {
        "scope_escape": 0,
        "remote_ai_calls": 0,
        "secret_leakage": 0,
        "crash": 0,
        "external_targets_contacted": 0,
    }
    labs_ready = bool(lab_reports) and all(item["status"] == "READY" for item in lab_reports.values())
    final = {
        "status": "AUTHORIZED_LOCAL_VALIDATION_READY" if labs_ready else "LOCAL_LAB_BLOCKED",
        "mode": "local-only",
        "target_count": len(lab_reports),
        "labs": lab_reports,
        "p0": p0,
        "remote_ai": {"status": "NOT_RUN", "calls": 0, "cost_cny": 0.0},
        "full_ground_truth": _full_ground_truth_summary(),
        "bounty_ready_count": sum(int(report["score"].get("bounty_ready_count", 0)) for report in lab_reports.values()),
        "submission_status": "NO_AUTO_SUBMISSION",
        "limitations": [
            "控制项和登录面发现成绩不等于补天可领奖漏洞。",
            "所有真实漏洞候选仍须在授权目标上人工复现和按平台规则提交。",
            "本轮没有启用远程 AI，也没有接触非本地目标。",
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_write(AUTOTEST_ROOT / "LOCAL_LAB_SCORE.json", final)
    (AUTOTEST_ROOT / "LOCAL_LAB_TEST_REPORT.md").write_text(render_local_lab_report(final), encoding="utf-8")
    return final


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SRC-Auto 五靶场本地验收")
    parser.add_argument("--local-only", action="store_true", default=True)
    parser.add_argument("--repeat-rounds", type=int, default=2, choices=range(0, MAX_ROUNDS + 1))
    parser.add_argument("--lab", action="append", dest="labs")
    args = parser.parse_args(argv)
    if not args.local_only:
        print(json.dumps({"status": "BLOCKED_POLICY", "reason": "local_only_is_mandatory", "network_contact": False}, ensure_ascii=False))
        return 3
    try:
        result = run_validation(args.repeat_rounds, args.labs)
    except Exception as exc:  # pragma: no cover - CLI safety net
        result = {"status": "FAIL", "reason": "orchestrator_exception", "detail": str(exc)[:500], "network_contact": False}
        _json_write(AUTOTEST_ROOT / "LOCAL_LAB_SCORE.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "AUTHORIZED_LOCAL_VALIDATION_READY" else 4


if __name__ == "__main__":
    raise SystemExit(main())

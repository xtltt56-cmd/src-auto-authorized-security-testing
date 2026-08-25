"""Simplified Chinese operator-facing messages with stable machine fields.

The control layer keeps status/reason values in English for scripts and audit
compatibility.  This module only adds human-readable Chinese text and bounded
summaries; it never changes a security decision or prints secret-bearing data.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Mapping


STATUS_ZH: Dict[str, str] = {
    "reachable": "可访问",
    "unreachable": "无法访问",
    "blocked_scope": "已被安全范围阻止",
    "BLOCKED_SCOPE": "已被安全范围阻止",
    "BLOCKED_DEPENDENCY": "依赖不可用",
    "COMPLETED_DISCOVERY_ONLY": "已完成发现，尚未执行漏洞扫描",
    "POSSIBLE_FINDINGS": "存在待人工复核的可能项",
    "SCAN_FAILED": "扫描失败",
    "NOT_RUN": "未运行",
    "created": "已创建",
    "completed": "已完成",
    "completed_tools": "工具执行完成",
    "stopped": "已停止",
    "blocked_confirmation": "需要人工确认",
    "blocked_runtime": "运行时策略已阻止",
    "blocked_output": "输出目录不安全",
    "blocked_policy": "策略已阻止",
    "blocked_plan": "计划已阻止",
    "blocked_selection": "目标选择已阻止",
    "blocked_provider": "提供商已阻止",
    "awaiting_selection": "等待人工选择确认",
    "selection_reviewed": "人工目标选择已审阅",
    "awaiting_adapter": "等待工具适配器",
    "candidate": "候选项",
    "error": "发生错误",
    "failed": "执行失败",
    "paused_resource": "因资源限制暂停",
    "stopped_manual": "已人工停止",
}


REASON_ZH: Dict[str, str] = {
    "confirm_local_required": "需要明确确认本机靶场",
    "manual_verification_required": "需要人工复核后才能确认",
    "vulnerability_scanners_not_run": "本次只执行发现，未运行漏洞扫描器",
    "juice_shop_unreachable": "本地 Juice Shop 无法访问",
    "remote_llm_disabled_by_runtime": "运行时已禁用远程 AI",
    "allow_real_targets_is_false": "未启用真实目标扫描策略",
    "stop_requested": "已收到人工停止请求",
    "output_outside_project_root": "输出目录必须位于项目根目录内",
    "scope_invalid": "Scope 文件无效",
    "scope_hash_mismatch": "运行记录与当前 Scope 摘要不一致",
    "scope_confirmation_required": "需要确认授权 Scope",
    "host_not_in_scope": "目标主机不在已确认范围内",
    "port_not_in_scope": "目标端口不在已确认范围内",
    "invalid_or_unsupported_url": "目标 URL 不是受支持的 HTTP(S) 地址",
    "invalid_port": "目标端口无效",
    "host_not_allowlisted": "目标主机不在允许范围内",
    "port_not_allowlisted": "目标端口不在允许范围内",
    "scheme_not_allowlisted": "目标协议不在允许范围内",
    "invalid_url": "URL 格式无效",
    "redirect_out_of_scope": "重定向目标越界",
    "redirect_requires_explicit_check": "需要人工检查重定向目标",
    "docker_unavailable": "Docker Desktop 不可用",
    "provider_key_missing": "未找到提供商密钥",
    "provider_disabled": "远程提供商未启用",
    "manual_only_required": "提供商必须保持人工启用模式",
    "confirm_external_required": "需要确认远程 AI 调用",
    "payload_digest_mismatch": "脱敏内容摘要不匹配",
    "runtime_policy_invalid": "运行时策略无效",
    "remote_provider_configuration_invalid": "远程提供商配置无效",
    "remote_provider_failed": "远程提供商调用失败",
    "plan_outside_project_root": "计划文件必须位于项目根目录内",
    "scope_outside_project_root": "Scope 文件必须位于项目根目录内",
    "confirm_selection_required": "需要人工确认本次目标选择",
    "selection_reviewed": "人工已确认选择，但尚未执行",
    "target_not_in_scope": "目标不在已确认范围内",
    "manual_execution_confirmed_is_false": "尚未完成人工执行确认",
    "run_not_found": "找不到运行记录",
    "finding_not_associated_with_run": "Finding 不属于指定运行记录",
    "finding_id_invalid": "Finding 编号无效",
    "juice_shop_scan_failed": "Juice Shop 扫描失败",
    "zap_report_invalid": "ZAP 报告格式无效",
    "ollama_fallback": "Ollama 不可用，使用本地启发式回退",
    "budget_limit_exceeded": "已达到 AI 预算限制",
    "resource_limit_exceeded": "已达到资源限制",
}


MESSAGE_ZH: Dict[str, str] = {
    "launcher_title": "SRC-Auto 一键启动系统",
    "project_root": "项目目录：{root}",
    "local_only_mode": "运行模式：仅本机回环靶场，不接触真实目标。",
    "checking_docker": "正在检查 Docker Desktop……",
    "starting_docker": "正在启动 Docker Desktop（本地靶场）……",
    "docker_missing": "未找到 Docker Desktop；将无法启动本地双靶场。",
    "docker_wait_failed": "Docker Desktop 未在规定时间内就绪，请检查后重试。",
    "ensuring_juice": "正在确保双靶场仅绑定到 127.0.0.1:3000 和 127.0.0.1:8081……",
    "juice_reachable": "Juice Shop 已在 127.0.0.1:3000 就绪。",
    "juice_unreachable": "Juice Shop 未能在 http://127.0.0.1:3000/ 访问。",
    "baseline_start": "正在执行本地发现基线……",
    "baseline_failed": "Juice Shop 基线结束，退出码：{code}",
    "ollama_ready": "Ollama 已就绪，将使用 config/models.yaml 中的本地模型。",
    "ollama_start": "正在启动 Ollama（不会创建开机启动任务）……",
    "ollama_fallback": "Ollama 未就绪，将使用本地启发式回退。",
    "ollama_missing": "未找到 Ollama，将使用本地启发式回退。",
    "creating_run": "正在创建本地运行记录……",
    "run_create_failed": "创建运行记录失败。",
    "run_pipeline": "正在执行本地控制层流程……",
    "show_findings": "正在显示 Findings……",
    "show_reports": "正在显示报告索引……",
    "run_completed": "本地运行已完成：{run_id}",
    "run_failed": "本地运行结束，退出码：{code}；请检查状态和报告。",
    "close_prompt": "按 Enter 键关闭窗口",
}


def language() -> str:
    """Return the requested UI language, defaulting safely to Simplified Chinese."""

    value = os.environ.get("SRC_AUTO_LANG", "zh-CN").strip()
    return value or "zh-CN"


def status_zh(value: Any) -> str:
    """Translate a known machine status; return the original value when unknown."""

    text = str(value)
    return STATUS_ZH.get(text, text)


def reason_zh(value: Any) -> str:
    """Translate a known machine reason; return the original value when unknown."""

    text = str(value)
    return REASON_ZH.get(text, text)


def message(key: str, **values: Any) -> str:
    """Format a fixed operator message and fall back to the key if unmapped."""

    template = MESSAGE_ZH.get(str(key), str(key))
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def with_zh_fields(document: Any) -> Any:
    """Copy a mapping/list and add Chinese explanations without renaming fields."""

    if isinstance(document, Mapping):
        result = dict(document)
        if "status" in result and "status_zh" not in result:
            result["status_zh"] = status_zh(result.get("status"))
        if "reason" in result and "reason_zh" not in result:
            result["reason_zh"] = reason_zh(result.get("reason"))
        return result
    if isinstance(document, list):
        return [with_zh_fields(item) for item in document]
    return document


def _safe_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def _status_lines(value: Mapping[str, Any]) -> List[str]:
    lines: List[str] = []
    if "status" in value:
        machine = value.get("status")
        translated = value.get("status_zh", status_zh(machine))
        lines.append("状态：{}{}".format(translated, "（{}）".format(machine) if translated != machine else ""))
    if "reason" in value:
        machine = value.get("reason")
        translated = value.get("reason_zh", reason_zh(machine))
        lines.append("原因：{}{}".format(translated, "（{}）".format(machine) if translated != machine else ""))
    return lines


def human_summary(command: str, value: Any) -> str:
    """Return a bounded, Chinese operator summary without raw tool or secret data."""

    document = with_zh_fields(value)
    command_name = str(command or "src-auto")
    lines: List[str] = ["SRC-Auto｜{}".format(command_name)]

    if command_name == "findings" and isinstance(document, list):
        lines.append("Finding 数量：{}".format(len(document)))
        for item in document[:50]:
            if isinstance(item, Mapping):
                lines.append("- {} [{}] {}".format(
                    _safe_text(item.get("title", "未命名 Finding"), 160),
                    status_zh(item.get("status", "")),
                    _safe_text(item.get("url", ""), 180),
                ))
        return "\n".join(lines)

    if command_name == "reports" and isinstance(document, list):
        lines.append("报告数量：{}".format(len(document)))
        for item in document[:50]:
            if isinstance(item, Mapping):
                lines.append("- {}".format(_safe_text(item.get("path", item.get("report_path", "")), 240)))
        return "\n".join(lines)

    if not isinstance(document, Mapping):
        if isinstance(document, list):
            lines.append("记录数量：{}".format(len(document)))
        else:
            lines.append(_safe_text(document))
        return "\n".join(lines)

    if command_name == "juice-shop-status":
        lines.extend(
            [
                "目标：本地 OWASP Juice Shop",
                "地址：{}".format(_safe_text(document.get("url", "http://127.0.0.1:3000/"))),
            ]
        )
        lines.extend(_status_lines(document))
        if "http_status" in document:
            lines.append("HTTP 状态码：{}".format(document.get("http_status")))
        if document.get("title"):
            lines.append("页面标题：{}".format(_safe_text(document.get("title"))))
        dependency = document.get("dependency")
        if isinstance(dependency, Mapping):
            lines.append("Docker：{}".format("可用" if dependency.get("docker_available_on_path") else "不可用"))
        lines.append("网络范围：仅允许 127.0.0.1/localhost:3000")
        return "\n".join(lines)

    if command_name == "juice-shop-baseline":
        lines.extend(_status_lines(document))
        lines.append("目标：{}".format(_safe_text(document.get("target_url", "http://127.0.0.1:3000/"))))
        lines.append("工具：{}".format(", ".join(str(item.get("tool")) for item in document.get("tools", []) if isinstance(item, Mapping)) or "无"))
        lines.append("报告：{}".format(_safe_text(document.get("artifact", ""))))
        lines.append("远程 AI：未调用")
        lines.append("安全提示：未执行漏洞扫描不等于没有漏洞。")
        return "\n".join(lines)

    if command_name == "juice-shop-zap":
        lines.extend(_status_lines(document))
        lines.append("目标：{}".format(_safe_text(document.get("target_url", "http://127.0.0.1:3000/"))))
        lines.append("候选数量：{}".format(document.get("finding_count", document.get("alert_count", 0))))
        lines.append("报告：{}".format(_safe_text(document.get("report_path", ""))))
        lines.append("远程 AI：未调用")
        lines.append("安全提示：POSSIBLE 只表示可能项，必须人工复核。")
        return "\n".join(lines)

    if command_name == "model-status":
        lines.extend(_status_lines(document))
        lines.append("提供商：{}".format(_safe_text(document.get("provider", ""))))
        lines.append("模型：{}".format(_safe_text(document.get("model", ""))))
        lines.append("可用：{}".format("是" if document.get("available") else "否"))
        lines.append("地址：{}".format(_safe_text(document.get("endpoint", ""))))
        return "\n".join(lines)

    if command_name == "remote-status":
        lines.append("远程 AI 当前为人工启用模式，不会自动发送请求。")
        policy = document.get("runtime_policy")
        if isinstance(policy, Mapping):
            lines.append("本地模型优先：{}".format("是" if policy.get("LOCAL_LLM_ONLY") else "否"))
            lines.append("允许远程 AI：{}".format("是" if policy.get("ALLOW_REMOTE_LLM") else "否"))
        providers = document.get("providers")
        if isinstance(providers, Mapping):
            for name, provider in providers.items():
                if isinstance(provider, Mapping):
                    lines.append("{}：模型={}，启用={}，密钥已设置={}，当前未联网".format(
                        name,
                        _safe_text(provider.get("model")),
                        "是" if provider.get("enabled") else "否",
                        "是" if provider.get("key_present") else "否",
                    ))
        return "\n".join(lines)

    if command_name == "remote-preview":
        lines.append("远程 AI 预览不会联网。")
        lines.append("提供商：{}".format(_safe_text(document.get("provider", ""))))
        lines.append("模型：{}".format(_safe_text(document.get("model", ""))))
        lines.append("Finding：{}".format(_safe_text(document.get("finding_id", ""))))
        lines.append("脱敏内容摘要：{}".format(_safe_text(document.get("payload_digest", ""), 80)))
        lines.append("下一步：检查脱敏内容后，再使用 --json 读取摘要并人工确认。")
        return "\n".join(lines)

    if command_name == "target-review":
        lines.append("人工目标审阅只读取 Scope 和计划，不会联网或启动扫描器。")
        lines.extend(_status_lines(document))
        if document.get("scope_target_id"):
            lines.append("Scope：{}".format(_safe_text(document.get("scope_target_id"), 120)))
        if document.get("scope_digest"):
            lines.append("Scope 摘要：{}".format(_safe_text(document.get("scope_digest"), 80)))
        if document.get("plan_digest"):
            lines.append("计划摘要：{}".format(_safe_text(document.get("plan_digest"), 80)))
        lines.append("目标数量：{}".format(document.get("target_count", 0)))
        for target in document.get("targets", [])[:50]:
            if isinstance(target, Mapping):
                lines.append("- {} {}:{}（{}）".format(
                    "允许" if target.get("allowed") else "拒绝",
                    _safe_text(target.get("host", ""), 120),
                    _safe_text(target.get("port", ""), 20),
                    "本机回环" if target.get("kind") == "loopback" else "非本地/仅审阅",
                ))
        if document.get("next_step"):
            lines.append("下一步：{}（仍需第二道人工执行开关）".format(_safe_text(document.get("next_step"), 120)))
        lines.append("网络请求：0")
        return "\n".join(lines)

    if command_name == "tool-status":
        for name, tool in document.items():
            if isinstance(tool, Mapping):
                status = tool.get("status", tool.get("available", "unknown"))
                detail = tool.get("detail", "")
                lines.append("{}：{}{}".format(
                    name,
                    status_zh(status) if status in STATUS_ZH else _safe_text(status),
                    "（{}）".format(_safe_text(detail, 120)) if detail else "",
                ))
        return "\n".join(lines)

    lines.extend(_status_lines(document))
    for key in ("run_id", "artifact", "report_path", "plan_digest", "finding_count", "target_url"):
        if key in document:
            lines.append("{}：{}".format(key, _safe_text(document.get(key))))
    return "\n".join(lines)

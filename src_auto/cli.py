import argparse
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .adapters import SafeToolAdapter, ToolRegistry, ToolSuite
from .attack_surface import AttackSurfaceTarget, build_attack_surface_plan
from .ai import AITriage, ModelRouter
from .business_logic import ResponseSnapshot, compare_api_objects, compare_authorization_responses
from .config import load_mapping
from .controls import BudgetGovernor
from .defense import DefenseAsset, build_defense_plan, compare_defense_snapshots
from .i18n import human_summary, with_zh_fields
from .live_plan import LivePlanError, validate_live_plan
from .pipeline import PipelineRunner
from .remote_ai import (
    DeepSeekProvider,
    OpenAIProvider,
    OpenRouterProvider,
    RemoteProviderError,
    RemoteReviewRequest,
    remote_session_consent_enabled,
)
from .runtime_policy import RuntimePolicy
from .target_review import review_target_selection
from .local_labs import LocalLabManager, load_lab_specs
from .log_analysis import analyse_jsonl_security_log
from .juice_shop import (
    DEFAULT_JUICE_SHOP_URL,
    LocalTargetError,
    baseline_document,
    local_dependency_status,
    probe_local_target,
    parse_zap_report,
    run_discovery_tools,
    run_zap_quick_scan,
    summarize_discovery_tools,
    validation_metrics_document,
    write_validation_metrics,
)
from .scope import ScopeGuard, ScopePolicy
from .session_vault import SessionVault
from .scope_resolver import ScopeResolver
from .store import Store
from .tool_profiles import project_tool_search_paths


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "src_auto.sqlite3"
DEFAULT_LOCAL_SCOPE = PROJECT_ROOT / "config" / "targets" / "local-lab" / "scope_confirmed.yaml"
DEFAULT_LOCAL_FIXTURE = PROJECT_ROOT / "lab" / "fixtures.json"
POLICY_PATH = PROJECT_ROOT / "config" / "policy.yaml"
MODELS_PATH = PROJECT_ROOT / "config" / "models.yaml"
RUNTIME_POLICY_PATH = PROJECT_ROOT / "config" / "validation" / "local_only.json"
LOCAL_LABS_PATH = PROJECT_ROOT / "config" / "labs" / "local_labs.json"
LOCAL_LABS_COMPOSE = PROJECT_ROOT / "docker-compose.local-labs.yml"
REMOTE_PROVIDER_NAMES = ("deepseek", "openai", "openrouter")
_OUTPUT_MODE = "json"
_CURRENT_COMMAND = ""


def _json(value: Any) -> None:
    document = with_zh_fields(value)
    if _OUTPUT_MODE == "human":
        print(human_summary(_CURRENT_COMMAND, document))
        return
    print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _resolve_output_mode(args: Any) -> str:
    if bool(getattr(args, "json_output", False)):
        return "json"
    if bool(getattr(args, "human", False)):
        return "human"
    try:
        return "human" if bool(sys.stdout.isatty()) else "json"
    except (AttributeError, OSError):
        return "json"


def _scope(path: str) -> ScopeGuard:
    return ScopeGuard(ScopePolicy.from_file(Path(path)))


def _runtime_policy() -> RuntimePolicy:
    policy = RuntimePolicy.from_file(RUNTIME_POLICY_PATH)
    # The checked-in profile remains local-only.  A launcher-created,
    # process-scoped consent variable may temporarily enable the explicitly
    # manual remote-review lane without changing the file on disk.
    if (
        remote_session_consent_enabled("deepseek", "SRC_AUTO_DEEPSEEK_CONSENT")
        or remote_session_consent_enabled("openai", "SRC_AUTO_OPENAI_CONSENT")
        or remote_session_consent_enabled("openrouter", "SRC_AUTO_OPENROUTER_CONSENT")
    ):
        mapping = dict(policy.to_mapping())
        mapping.update({"AI_PROVIDER": "remote", "LOCAL_LLM_ONLY": False, "ALLOW_REMOTE_LLM": True})
        return RuntimePolicy.from_mapping(mapping)
    return policy


def _juice_shop_ground_truth_counts():
    path = PROJECT_ROOT / "validation" / "juice-shop" / "ground_truth.json"
    try:
        document = load_mapping(path)
        entries = document.get("entries", [])
        if not isinstance(entries, list):
            return 0, 0
        return len(entries), sum(1 for entry in entries if isinstance(entry, dict) and bool(entry.get("scanner_detectable")))
    except (OSError, ValueError, TypeError):
        return 0, 0


def _write_juice_shop_metrics(
    out_dir: Path,
    status: str,
    reason: str,
    target_url: str,
    scan_metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    ground_truth_count, detectable_count = _juice_shop_ground_truth_counts()
    document = validation_metrics_document(
        status,
        reason,
        target_url,
        ground_truth_count,
        detectable_count,
        "Metrics are null until a reachable target produces adjudicated scanner findings; no unexecuted scan is scored.",
        scan_metadata=scan_metadata,
    )
    return write_validation_metrics(out_dir / "baseline_metrics.json", document)


def _runner(store: Store, guard: ScopeGuard) -> PipelineRunner:
    policy = load_mapping(POLICY_PATH)
    models = load_mapping(MODELS_PATH)
    models["runtime_policy"] = _runtime_policy().to_mapping()
    budget = BudgetGovernor(
        float(policy.get("monthly_ai_budget_yuan", 100)),
        float(policy.get("daily_ai_budget_yuan", 10)),
    )
    ai = AITriage(
        ModelRouter(models),
        budget,
        spend_callback=lambda amount, category: store.record_spend(amount, category),
    )
    return PipelineRunner(store, guard, PROJECT_ROOT, ai_triage=ai)


def _remote_config(provider: str) -> Dict[str, Any]:
    name = str(provider).strip().lower()
    if name not in REMOTE_PROVIDER_NAMES:
        raise ValueError("unsupported_remote_provider")
    models = load_mapping(MODELS_PATH)
    configs = models.get("remote_providers", {})
    if not isinstance(configs, dict) or not isinstance(configs.get(name), dict):
        raise ValueError("remote_provider_not_configured")
    config = dict(configs[name])
    config["provider"] = name
    return config


def _remote_provider(
    provider: str, config: Dict[str, Any], urlopen_fn=None
):
    runtime = _runtime_policy()
    common = {
        "endpoint": str(config.get("endpoint", "")),
        "model": str(config.get("model", "")),
        "key_env": str(config.get("key_env", "")),
        "timeout_seconds": int(config.get("timeout_seconds", 60)),
        "max_input_tokens": int(config.get("max_input_tokens", 2000)),
        "max_output_tokens": int(config.get("max_output_tokens", 256)),
        "input_usd_per_million": float(
            config.get("peak_input_usd_per_million", config.get("input_usd_per_million", 0.0))
        ),
        "output_usd_per_million": float(
            config.get("peak_output_usd_per_million", config.get("output_usd_per_million", 0.0))
        ),
        "enabled": bool(config.get("enabled", False)),
        "manual_only": bool(config.get("manual_only", True)),
        "consent_env": str(config.get("consent_env", "")),
        "allow_remote_llm": bool(runtime.allow_remote_llm and not runtime.local_llm_only),
        "urlopen_fn": urlopen_fn,
    }
    if provider == "deepseek":
        return DeepSeekProvider(**common)
    if provider == "openai":
        return OpenAIProvider(**common)
    if provider == "openrouter":
        return OpenRouterProvider(**common)
    raise ValueError("unsupported_remote_provider")


def _remote_finding_context(store: Store, run_id: str, finding_id: str, scope_path: str):
    run = store.get_run(run_id)
    if not run:
        return None, None, {"status": "error", "reason": "run_not_found"}
    try:
        guard = _scope(scope_path)
    except (OSError, ValueError, TypeError):
        return None, None, {"status": "error", "reason": "scope_invalid"}
    if run["scope_hash"] != guard.policy.digest():
        return None, None, {"status": "blocked_scope", "reason": "scope_hash_mismatch"}
    try:
        wanted_id = int(finding_id)
    except (TypeError, ValueError):
        return None, None, {"status": "error", "reason": "finding_id_invalid"}
    finding = next((item for item in store.list_findings(run_id) if int(item.get("id", -1)) == wanted_id), None)
    if finding is None:
        return None, None, {"status": "error", "reason": "finding_not_associated_with_run"}
    decision = guard.decide(str(finding.get("url", "")))
    if not decision.allowed:
        return None, None, {"status": "blocked_scope", "reason": decision.reason}
    return run, finding, guard


def _remote_provider_gate(provider: str):
    try:
        config = _remote_config(provider)
    except ValueError as exc:
        return None, {"status": "error", "reason": str(exc)}
    if not remote_session_consent_enabled(provider, str(config.get("consent_env", ""))):
        return None, {
            "status": "blocked_runtime",
            "reason": "remote_ai_disabled_for_session",
            "network_contact": False,
        }
    try:
        runtime = _runtime_policy()
    except (OSError, ValueError, TypeError):
        return None, {"status": "blocked_runtime", "reason": "runtime_policy_invalid"}
    if runtime.local_llm_only or not runtime.allow_remote_llm:
        return None, {"status": "blocked_runtime", "reason": "remote_llm_disabled_by_runtime"}
    if not bool(config.get("enabled", False)):
        return None, {"status": "blocked_provider", "reason": "provider_disabled"}
    if not bool(config.get("manual_only", True)):
        return None, {"status": "blocked_provider", "reason": "manual_only_required"}
    return config, None


def _remote_status() -> Dict[str, Any]:
    runtime = _runtime_policy()
    models = load_mapping(MODELS_PATH)
    configs = models.get("remote_providers", {})
    result = {}
    for provider in REMOTE_PROVIDER_NAMES:
        config = configs.get(provider, {}) if isinstance(configs, dict) else {}
        if not isinstance(config, dict):
            config = {}
        key_env = str(config.get("key_env", ""))
        result[provider] = {
            "provider": provider,
            "model": str(config.get("model", "")),
            "enabled": bool(config.get("enabled", False)),
            "manual_only": bool(config.get("manual_only", True)),
            "key_env": key_env,
            "key_present": bool(key_env and os.environ.get(key_env, "").strip()),
            "consent_env": str(config.get("consent_env", "")),
            "session_consent": remote_session_consent_enabled(provider, str(config.get("consent_env", ""))),
            "network_contact": False,
        }
    return {
        "startup_consent_required": True,
        "runtime_policy": {
            "AI_PROVIDER": runtime.ai_provider,
            "LOCAL_LLM_ONLY": runtime.local_llm_only,
            "ALLOW_REMOTE_LLM": runtime.allow_remote_llm,
            "allowed_hosts": list(runtime.allowed_hosts),
            "allowed_ports": list(runtime.allowed_ports),
            "max_concurrency": runtime.max_concurrency,
        },
        "providers": result,
    }


class ChineseArgumentParser(argparse.ArgumentParser):
    """Argument parser with Chinese help labels while keeping command names stable."""

    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.pop("add_help", None)
        super().__init__(*args, add_help=False, **kwargs)
        self.add_argument("-h", "--help", action="help", help="显示帮助并退出")


def _project_file(value: str, field: str, must_exist: bool = True) -> Path:
    """Resolve an artifact path and reject anything outside the project root."""
    path = Path(value).resolve()
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("{}_outside_project".format(field)) from exc
    if must_exist and not path.is_file():
        raise ValueError("{}_not_found".format(field))
    return path


def _read_object(path: Path, field: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("{}_invalid_json".format(field)) from exc
    if not isinstance(value, dict):
        raise ValueError("{}_must_be_object".format(field))
    return value


def _write_project_json(value: str, document: Dict[str, Any], field: str) -> Path:
    path = _project_file(value, field, must_exist=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(with_zh_fields(document), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _response_snapshot(document: Dict[str, Any], field: str) -> ResponseSnapshot:
    try:
        status_code = int(document["status_code"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("{}_status_code_invalid".format(field)) from exc
    headers = document.get("headers", {})
    if not isinstance(headers, dict):
        raise ValueError("{}_headers_invalid".format(field))
    return ResponseSnapshot(status_code, headers, document.get("body"))


def build_parser() -> argparse.ArgumentParser:
    parser = ChineseArgumentParser(prog="src-auto", description="授权范围门控的 SRC 自动化控制层（中文优先）")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=ChineseArgumentParser)
    new = sub.add_parser("new", help="创建运行记录")
    new.add_argument("--target-id", required=True)
    new.add_argument("--scope", required=True)
    new.add_argument("--mode", choices=["local", "real"], default="local")
    run = sub.add_parser("run", help="执行本地靶场或受控外部流程")
    run.add_argument("--run-id", required=True)
    run.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    run.add_argument("--local-lab", action="store_true")
    run.add_argument("--fixture", default=str(DEFAULT_LOCAL_FIXTURE))
    live = sub.add_parser("run-live", help="执行人工审阅的外部工具计划")
    live.add_argument("--run-id", required=True)
    live.add_argument("--scope", required=True)
    live.add_argument("--plan", required=True)
    live.add_argument("--execute-live", action="store_true", help="启动外部工具所必需的明确开关")
    review = sub.add_parser("target-review", help="人工选择并预览目标范围（只审阅、不联网）")
    review.add_argument("--scope", required=True, help="项目根目录内的 Scope 文件")
    review.add_argument("--plan", required=True, help="项目根目录内的人工计划")
    review.add_argument("--confirm-selection", action="store_true", help="确认人工选择；仍不会执行网络请求")
    status = sub.add_parser("status", help="查看运行记录")
    status.add_argument("--run-id")
    findings = sub.add_parser("findings", help="查看 Findings")
    findings.add_argument("--run-id")
    sub.add_parser("reports", help="查看已生成的报告")
    stop = sub.add_parser("stop", help="请求人工停止")
    stop.add_argument("--run-id")
    resume = sub.add_parser("resume", help="恢复已停止的本地运行")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    resume.add_argument("--local-lab", action="store_true")
    resume.add_argument("--fixture", default=str(DEFAULT_LOCAL_FIXTURE))
    sub.add_parser("tool-status", help="检查已安装的外部工具")
    sub.add_parser("model-status", help="检查本地模型端点")
    surface_plan = sub.add_parser("surface-plan", help="生成范围内的外部资产发现计划（不执行）")
    surface_plan.add_argument("--target-id", required=True)
    surface_plan.add_argument("--url", required=True)
    surface_plan.add_argument("--scope", required=True)
    surface_plan.add_argument("--automation-allowed", action="store_true", help="确认该范围允许自动化观察")
    surface_plan.add_argument("--output", required=True, help="项目内输出 JSON 文件")
    api_compare = sub.add_parser("api-compare", help="离线比较三份 API 响应快照，不联网")
    api_compare.add_argument("--owner", required=True, help="项目内 owner 响应 JSON")
    api_compare.add_argument("--peer", required=True, help="项目内 peer 响应 JSON")
    api_compare.add_argument("--anonymous", required=True, help="项目内匿名响应 JSON")
    api_compare.add_argument("--output", required=True, help="项目内输出 JSON 文件")
    api_diff = sub.add_parser("api-object-diff", help="离线比较两份 API JSON 对象的结构差异")
    api_diff.add_argument("--before", required=True)
    api_diff.add_argument("--after", required=True)
    api_diff.add_argument("--output", required=True)
    defense_plan = sub.add_parser("defense-plan", help="生成已授权自有域名的防护观察计划（不执行）")
    defense_plan.add_argument("--asset", required=True, help="项目内资产登记 JSON")
    defense_plan.add_argument("--output", required=True, help="项目内输出 JSON 文件")
    defense_diff = sub.add_parser("defense-diff", help="离线比较两份防护快照")
    defense_diff.add_argument("--before", required=True)
    defense_diff.add_argument("--after", required=True)
    defense_diff.add_argument("--output", required=True)
    log_review = sub.add_parser("log-review", help="在本地分析 JSONL 安全日志（不上传）")
    log_review.add_argument("--input", required=True, help="项目内 JSONL 日志")
    log_review.add_argument("--output", required=True, help="项目内输出 JSON 文件")
    log_review.add_argument("--max-events", type=int, default=10000)
    sub.add_parser("session-list", help="列出 DPAPI 加密测试会话的非敏感元数据")
    juice_status = sub.add_parser("juice-shop-status", help="只检查操作者启动的本地 Juice Shop")
    juice_status.add_argument("--url", default=DEFAULT_JUICE_SHOP_URL)
    juice_baseline = sub.add_parser("juice-shop-baseline", help="执行受限的本地 Juice Shop 发现并写入验证工件")
    juice_baseline.add_argument("--url", default=DEFAULT_JUICE_SHOP_URL)
    juice_baseline.add_argument(
        "--scope",
        default=str(PROJECT_ROOT / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"),
    )
    juice_baseline.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "validation" / "juice-shop"),
    )
    juice_zap = sub.add_parser(
        "juice-shop-zap",
        help="在人工确认后仅对本地 Juice Shop 执行 ZAP 快速扫描",
    )
    juice_zap.add_argument("--url", default=DEFAULT_JUICE_SHOP_URL)
    juice_zap.add_argument(
        "--scope",
        default=str(PROJECT_ROOT / "config" / "targets" / "juice-shop-local" / "scope_confirmed.yaml"),
    )
    juice_zap.add_argument("--out-dir", default=str(PROJECT_ROOT / "validation" / "juice-shop"))
    juice_zap.add_argument(
        "--confirm-local",
        action="store_true",
        help="确认目标是已授权的本机 Juice Shop 后再执行主动扫描",
    )
    local_labs = sub.add_parser("local-labs", help="管理固定版本、仅回环发布的本地靶场")
    local_labs.add_argument("action", choices=["status", "start", "stop", "reset", "down"], help="靶场操作")
    local_labs.add_argument("--lab", help="靶场 ID；status 不填时显示全部")
    local_validation = sub.add_parser("local-validation", help="运行固定 OWASP 靶场、仅本地的可审计验收")
    local_validation.add_argument(
        "--local-only",
        action="store_true",
        default=True,
        help="仅本机回环靶场（固定启用，保留该参数用于脚本兼容）",
    )
    local_validation.add_argument("--repeat-rounds", type=int, default=2, choices=range(0, 4))
    local_validation.add_argument("--lab", action="append", dest="labs")
    local_regression = sub.add_parser("local-regression", help="运行非破坏性的本地靶场安全回归")
    local_regression.add_argument(
        "--local-only",
        action="store_true",
        default=True,
        help="仅本机回环靶场（固定启用，保留该参数用于脚本兼容）",
    )
    local_regression.add_argument("--repeat-rounds", type=int, default=0, choices=range(0, 4))
    local_regression.add_argument("--lab", action="append", dest="labs")
    local_regression.add_argument("--case", action="append", dest="case_ids")
    remote_status = sub.add_parser("remote-status", help="查看人工启用的远程 AI（不联网）")
    remote_status.set_defaults(command="remote-status")
    remote_preview = sub.add_parser("remote-preview", help="预览脱敏后的远程 Finding 审阅内容")
    remote_preview.add_argument("--run-id", required=True)
    remote_preview.add_argument("--finding-id", required=True)
    remote_preview.add_argument("--provider", choices=REMOTE_PROVIDER_NAMES, required=True)
    remote_preview.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    remote_triage = sub.add_parser("remote-triage", help="发送一次人工确认的远程 Finding 审阅")
    remote_triage.add_argument("--run-id", required=True)
    remote_triage.add_argument("--finding-id", required=True)
    remote_triage.add_argument("--provider", choices=REMOTE_PROVIDER_NAMES, required=True)
    remote_triage.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    remote_triage.add_argument("--confirm-external", action="store_true", help="确认发送一次远程 AI 请求")
    remote_triage.add_argument("--confirm-digest", required=True, help="填写 remote-preview 显示的完整 SHA-256 摘要")
    resolve = sub.add_parser("resolve-scope", help="将明确规则快照规范化为候选 Scope")
    resolve.add_argument("--snapshot", required=True)
    resolve.add_argument("--output-dir", required=True)
    for command_parser in sub.choices.values():
        output_group = command_parser.add_mutually_exclusive_group()
        output_group.add_argument("--json", dest="json_output", action="store_true", help="只输出机器可读 JSON")
        output_group.add_argument("--human", action="store_true", help="输出简体中文摘要")
    return parser


def main(argv=None) -> int:
    global _OUTPUT_MODE, _CURRENT_COMMAND
    args = build_parser().parse_args(argv)
    _OUTPUT_MODE = _resolve_output_mode(args)
    _CURRENT_COMMAND = str(args.command)
    store = Store(DB_PATH)
    try:
        if args.command == "new":
            guard = _scope(args.scope)
            run_id = store.create_run(args.target_id, guard.policy.digest(), args.mode)
            _json({"run_id": run_id, "scope_hash": guard.policy.digest(), "status": "created"})
            return 0
        if args.command == "status":
            _json(store.get_run(args.run_id) if args.run_id else store.list_runs())
            return 0
        if args.command == "findings":
            _json(store.list_findings(args.run_id))
            return 0
        if args.command == "reports":
            _json(store.list_reports())
            return 0
        if args.command == "tool-status":
            registry = ToolRegistry(search_paths=project_tool_search_paths(PROJECT_ROOT))
            _json({name: result.__dict__ for name, result in ToolSuite(registry).verify_all().items()})
            return 0
        if args.command == "model-status":
            models = load_mapping(MODELS_PATH)
            models["runtime_policy"] = _runtime_policy().to_mapping()
            route = ModelRouter(models).route("triage", "normal")
            provider = ModelRouter(models).provider_for(route)
            available = provider.health() if provider is not None else False
            _json({"lane": route.lane, "provider": route.provider, "model": route.model, "endpoint": route.endpoint, "available": available})
            return 0 if available else 4
        if args.command == "surface-plan":
            try:
                guard = _scope(args.scope)
                target = AttackSurfaceTarget.from_url(args.target_id, args.url)
                registry = ToolRegistry(search_paths=project_tool_search_paths(PROJECT_ROOT))
                available_tools = {
                    name for name, detail in registry.status().items() if detail.get("status") == "available"
                }
                plan = build_attack_surface_plan(target, guard, bool(args.automation_allowed), available_tools)
                output = _write_project_json(args.output, plan.to_mapping(), "output")
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "PLAN_READY", "output": str(output), "plan": plan.to_mapping(), "network_contact": False})
            return 0
        if args.command == "api-compare":
            try:
                owner = _response_snapshot(_read_object(_project_file(args.owner, "owner"), "owner"), "owner")
                peer = _response_snapshot(_read_object(_project_file(args.peer, "peer"), "peer"), "peer")
                anonymous = _response_snapshot(_read_object(_project_file(args.anonymous, "anonymous"), "anonymous"), "anonymous")
                result = compare_authorization_responses(owner, peer, anonymous)
                output = _write_project_json(args.output, result, "output")
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "COMPLETED", "output": str(output), "result": result, "network_contact": False})
            return 0
        if args.command == "api-object-diff":
            try:
                before = _read_object(_project_file(args.before, "before"), "before")
                after = _read_object(_project_file(args.after, "after"), "after")
                result = compare_api_objects(before, after)
                output = _write_project_json(args.output, result, "output")
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "COMPLETED", "output": str(output), "result": result, "network_contact": False})
            return 0
        if args.command == "defense-plan":
            try:
                asset = DefenseAsset.from_mapping(_read_object(_project_file(args.asset, "asset"), "asset"))
                plan = build_defense_plan(asset)
                output = _write_project_json(args.output, plan, "output")
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "PLAN_READY", "output": str(output), "plan": plan, "network_contact": False})
            return 0
        if args.command == "defense-diff":
            try:
                before = _read_object(_project_file(args.before, "before"), "before")
                after = _read_object(_project_file(args.after, "after"), "after")
                result = compare_defense_snapshots(before, after)
                output = _write_project_json(args.output, result, "output")
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "COMPLETED", "output": str(output), "result": result, "network_contact": False})
            return 0
        if args.command == "log-review":
            try:
                result = analyse_jsonl_security_log(_project_file(args.input, "input"), max_events=args.max_events)
                output = _write_project_json(args.output, result, "output")
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "COMPLETED", "output": str(output), "result": result, "network_contact": False})
            return 0
        if args.command == "session-list":
            try:
                profiles = SessionVault(PROJECT_ROOT).list_profiles()
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED", "reason": str(exc), "network_contact": False})
                return 3
            _json({"status": "COMPLETED", "profiles": profiles, "network_contact": False})
            return 0
        if args.command == "local-labs":
            try:
                manager = LocalLabManager(PROJECT_ROOT, LOCAL_LABS_PATH, LOCAL_LABS_COMPOSE)
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED_CONFIGURATION", "reason": str(exc), "network_contact": False})
                return 3
            if args.action == "status" and not args.lab:
                result = [manager.status(spec.lab_id) for spec in load_lab_specs(LOCAL_LABS_PATH)]
                _json({"status": "COMPLETED", "labs": result, "network_contact": False})
                return 0
            if not args.lab:
                _json({"status": "BLOCKED_ARGUMENT", "reason": "lab_required", "network_contact": False})
                return 3
            try:
                result = manager.operate(args.action, args.lab, wait=args.action in ("start", "reset"))
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "BLOCKED_CONFIGURATION", "reason": str(exc), "network_contact": False})
                return 3
            _json(result)
            return 0 if result.get("status") in ("READY", "COMPLETED", "STOPPED", "STARTING", "BLOCKED_NO_HEALTH") else 4
        if args.command == "local-validation":
            try:
                from tools.run_local_lab_validation import run_validation

                result = run_validation(args.repeat_rounds, args.labs)
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                _json({"status": "FAIL", "reason": "local_validation_failed", "detail": str(exc)[:500], "network_contact": False})
                return 4
            _json(result)
            return 0 if result.get("status") == "AUTHORIZED_LOCAL_VALIDATION_READY" else 4
        if args.command == "local-regression":
            try:
                from .local_regression import run_regression

                result = run_regression(
                    PROJECT_ROOT,
                    repeat_rounds=args.repeat_rounds,
                    labs=args.labs,
                    case_ids=args.case_ids,
                )
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                _json({"status": "FAIL", "reason": "local_regression_failed", "detail": str(exc)[:500], "network_contact": False})
                return 4
            _json(result)
            return 0 if result.get("status") == "COMPLETED" else 4
        if args.command == "juice-shop-status":
            runtime = _runtime_policy()
            dependency = local_dependency_status()
            runtime_allowed, runtime_reason = runtime.decide_url(args.url)
            try:
                if not runtime_allowed:
                    raise LocalTargetError(runtime_reason, args.url)
                result = probe_local_target(runtime, args.url)
            except LocalTargetError as exc:
                result = {
                    "status": "blocked_scope",
                    "reason": exc.reason,
                    "url": args.url,
                    "network_contact": False,
                }
            result["runtime_policy"] = runtime.to_mapping()
            result["dependency"] = dependency
            _json(result)
            if result.get("status") == "reachable":
                return 0
            if result.get("status") == "blocked_scope":
                return 3
            return 4
        if args.command == "juice-shop-baseline":
            runtime = _runtime_policy()
            scan_id = "juice-shop-baseline-" + uuid.uuid4().hex[:12]
            scan_started_at = datetime.now(timezone.utc).isoformat()
            scan_started = time.perf_counter()
            try:
                out_dir = Path(args.out_dir).resolve()
                out_dir.relative_to(PROJECT_ROOT.resolve())
            except (OSError, ValueError):
                _json({"status": "blocked_output", "reason": "output_outside_project_root", "network_contact": False})
                return 3
            try:
                guard = _scope(args.scope)
            except (OSError, ValueError, TypeError):
                _json({"status": "blocked_scope", "reason": "scope_invalid", "network_contact": False})
                return 3
            dependency = local_dependency_status()
            try:
                runtime_allowed, runtime_reason = runtime.decide_url(args.url)
                scope_decision = guard.decide(args.url)
                if not runtime_allowed:
                    raise LocalTargetError(runtime_reason, args.url)
                if not scope_decision.allowed:
                    raise LocalTargetError(scope_decision.reason, args.url)
                probe = probe_local_target(runtime, args.url)
            except LocalTargetError as exc:
                path = baseline_document(
                    out_dir / "baseline_results.json",
                    "BLOCKED_SCOPE",
                    exc.reason,
                    args.url,
                    {"status": "blocked_scope", "network_contact": False},
                    [],
                    [],
                    None,
                    environment={"dependency": dependency, "runtime_policy": runtime.to_mapping()},
                )
                _json({"status": "BLOCKED_SCOPE", "reason": exc.reason, "artifact": str(path), "network_contact": False})
                return 3
            if probe.get("status") != "reachable":
                _write_juice_shop_metrics(out_dir, "NOT_RUN", "juice_shop_unreachable", args.url)
                path = baseline_document(
                    out_dir / "baseline_results.json",
                    "BLOCKED_DEPENDENCY",
                    "juice_shop_unreachable",
                    args.url,
                    probe,
                    [],
                    [],
                    None,
                    environment={"dependency": dependency, "runtime_policy": runtime.to_mapping()},
                )
                _json(
                    {
                        "status": "BLOCKED_DEPENDENCY",
                        "reason": "juice_shop_unreachable",
                        "artifact": str(path),
                        "probe": probe,
                        "dependency": dependency,
                    }
                )
                return 4
            tools = run_discovery_tools(PROJECT_ROOT, guard, args.url)
            discovery = summarize_discovery_tools(runtime, tools)
            scan_metadata = {
                "scan_id": scan_id,
                "started_at": scan_started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(time.perf_counter() - scan_started, 3),
                "http_request_count": 1,
                "http_request_count_scope": "control_preflight_only",
                "discovered_urls": discovery["discovered_urls"],
                "discovered_url_count": discovery["discovered_url_count"],
                "external_urls_excluded": discovery["external_urls_excluded"],
                "external_excluded_count": discovery["external_excluded_count"],
                "discovery_tools": discovery["tools_run"],
                "vulnerability_scanners_run": False,
                "local_model_calls": 0,
                "remote_ai_calls": 0,
                "remote_cost_cny": 0.0,
            }
            _write_juice_shop_metrics(
                out_dir,
                "NOT_RUN",
                "vulnerability_scanners_not_run",
                args.url,
                scan_metadata=scan_metadata,
            )
            path = baseline_document(
                out_dir / "baseline_results.json",
                "COMPLETED_DISCOVERY_ONLY",
                "vulnerability_scanners_not_run",
                args.url,
                probe,
                tools,
                [],
                None,
                environment={"dependency": dependency, "runtime_policy": runtime.to_mapping()},
                scan_metadata=scan_metadata,
            )
            _json(
                {
                    "status": "COMPLETED_DISCOVERY_ONLY",
                    "reason": "vulnerability_scanners_not_run",
                    "artifact": str(path),
                    "probe": probe,
                    "tools": tools,
                    "network_contact": True,
                }
            )
            return 0
        if args.command == "juice-shop-zap":
            runtime = _runtime_policy()
            if not args.confirm_local:
                _json(
                    {
                        "status": "blocked_confirmation",
                        "reason": "confirm_local_required",
                        "network_contact": False,
                    }
                )
                return 3
            try:
                out_dir = Path(args.out_dir).resolve()
                out_dir.relative_to(PROJECT_ROOT.resolve())
                out_dir.mkdir(parents=True, exist_ok=True)
            except (OSError, ValueError):
                _json({"status": "blocked_output", "reason": "output_outside_project_root", "network_contact": False})
                return 3
            try:
                guard = _scope(args.scope)
                runtime_allowed, runtime_reason = runtime.decide_url(args.url)
                scope_decision = guard.decide(args.url)
                if not runtime_allowed:
                    raise LocalTargetError(runtime_reason, args.url)
                if not scope_decision.allowed:
                    raise LocalTargetError(scope_decision.reason, args.url)
                probe = probe_local_target(runtime, args.url)
            except (LocalTargetError, OSError, ValueError, TypeError) as exc:
                reason = getattr(exc, "reason", "scope_invalid")
                _json({"status": "BLOCKED_SCOPE", "reason": reason, "network_contact": False})
                return 3
            if probe.get("status") != "reachable":
                _json({"status": "BLOCKED_DEPENDENCY", "reason": "juice_shop_unreachable", "probe": probe, "network_contact": True})
                return 4
            report_path = out_dir / "zap_quick_report.json"
            run_result = run_zap_quick_scan(PROJECT_ROOT, args.url, report_path)
            if run_result.get("status") != "completed" or not report_path.is_file():
                artifact = out_dir / "zap_findings.json"
                artifact.write_text(
                    json.dumps(
                        {
                            "status": "SCAN_FAILED",
                            "reason": run_result.get("detail", "zap_scan_failed"),
                            "target_url": args.url,
                            "network_contact": True,
                            "run": run_result,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                _json({"status": "SCAN_FAILED", "artifact": str(artifact), "run": run_result, "network_contact": True})
                return 4
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                _json({"status": "SCAN_FAILED", "reason": "zap_report_invalid", "detail": str(exc)[:300], "network_contact": True})
                return 4
            parsed = parse_zap_report(report, runtime)
            artifact = out_dir / "zap_findings.json"
            document = with_zh_fields({
                "status": "POSSIBLE_FINDINGS",
                "reason": "manual_verification_required",
                "target_url": args.url,
                "network_contact": True,
                "scanner": "zap",
                "scanner_version": str(report.get("@version", "")),
                "report_path": str(report_path),
                "alert_count": parsed["alert_count"],
                "finding_count": parsed["finding_count"],
                "findings": parsed["findings"],
                "external_urls_excluded": parsed["external_urls_excluded"],
                "external_excluded_count": parsed["external_excluded_count"],
                "remote_ai_calls": 0,
                "remote_cost_cny": 0.0,
                "local_model_calls": 0,
                "run": {
                    "status": run_result.get("status"),
                    "returncode": run_result.get("returncode"),
                    "report_path": run_result.get("report_path"),
                },
            })
            artifact.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            _json(
                {
                    "status": document["status"],
                    "reason": document["reason"],
                    "artifact": str(artifact),
                    "report_path": str(report_path),
                    "alert_count": document["alert_count"],
                    "finding_count": document["finding_count"],
                    "network_contact": True,
                }
            )
            return 0
        if args.command == "remote-status":
            _json(_remote_status())
            return 0
        if args.command in ("remote-preview", "remote-triage"):
            config, provider_error = _remote_provider_gate(args.provider)
            if provider_error:
                _json(provider_error)
                return 3
            run, finding, context = _remote_finding_context(store, args.run_id, args.finding_id, args.scope)
            if isinstance(context, dict):
                _json(context)
                return 3 if context.get("status", "").startswith("blocked") else 2
            request = RemoteReviewRequest.from_finding(finding)
            if args.command == "remote-preview":
                _json(
                    {
                        "status": "preview",
                        "network_contact": False,
                        "run_id": args.run_id,
                        "finding_id": int(finding["id"]),
                        "finding_fingerprint": finding["fingerprint"],
                        "provider": args.provider,
                        "model": str(config.get("model", "")),
                        "payload": request.payload,
                        "payload_digest": request.digest,
                    }
                )
                return 0
            if not args.confirm_external:
                _json(
                    {
                        "status": "blocked_confirmation",
                        "reason": "confirm_external_required",
                        "network_contact": False,
                        "payload_digest": request.digest,
                    }
                )
                return 3
            supplied_digest = str(args.confirm_digest or "").strip().lower()
            if not hmac.compare_digest(supplied_digest, request.digest):
                _json(
                    {
                        "status": "blocked_digest",
                        "reason": "payload_digest_mismatch",
                        "network_contact": False,
                        "payload_digest": request.digest,
                    }
                )
                return 3
            if (PROJECT_ROOT / "STOP").exists() or str(run.get("status", "")) == "stopped":
                _json({"status": "blocked_stop", "reason": "stop_requested", "network_contact": False})
                return 3
            key_env = str(config.get("key_env", ""))
            if not key_env or not os.environ.get(key_env, "").strip():
                _json({"status": "blocked_provider", "reason": "provider_key_missing", "network_contact": False})
                return 3
            try:
                provider = _remote_provider(args.provider, config)
            except (TypeError, ValueError, KeyError):
                _json({"status": "error", "reason": "remote_provider_configuration_invalid", "network_contact": False})
                return 2
            network_attempted = True
            try:
                review = provider.review(finding)
            except RemoteProviderError as exc:
                reason = str(exc) or "remote_provider_failed"
                if reason in ("remote_input_token_limit_exceeded", "provider_key_missing", "provider_disabled"):
                    network_attempted = False
                store.record_event(args.run_id, "warning", "remote_ai_review_failed", {"provider": args.provider, "reason": reason})
                _json({"status": "failed", "reason": reason, "network_contact": network_attempted})
                return 4
            except (OSError, TypeError, ValueError):
                store.record_event(args.run_id, "warning", "remote_ai_review_failed", {"provider": args.provider, "reason": "remote_provider_failed"})
                _json({"status": "failed", "reason": "remote_provider_failed", "network_contact": network_attempted})
                return 4
            review_id = store.insert_ai_review(
                {
                    **review,
                    "run_id": args.run_id,
                    "finding_fingerprint": finding["fingerprint"],
                    "payload_digest": request.digest,
                }
            )
            store.record_event(
                args.run_id,
                "info",
                "remote_ai_review_completed",
                {
                    "provider": review.get("provider", args.provider),
                    "model": review.get("model", config.get("model", "")),
                    "payload_digest": request.digest,
                    "estimated_cost_usd": review.get("estimated_cost_usd", 0.0),
                    "ai_review_id": review_id,
                },
            )
            _json(
                {
                    "status": "completed",
                    "network_contact": True,
                    "ai_review_id": review_id,
                    "run_id": args.run_id,
                    "finding_id": int(finding["id"]),
                    "finding_fingerprint": finding["fingerprint"],
                    "payload_digest": request.digest,
                    "review": review,
                }
            )
            return 0
        if args.command == "target-review":
            result = review_target_selection(
                PROJECT_ROOT,
                Path(args.scope),
                Path(args.plan),
                confirm_selection=bool(args.confirm_selection),
            )
            _json(result)
            return 0 if result.get("status") in ("awaiting_selection", "selection_reviewed") else 3
        if args.command == "run-live":
            run = store.get_run(args.run_id)
            if not run:
                _json({"status": "error", "reason": "run_not_found"})
                return 2
            guard = _scope(args.scope)
            if run["scope_hash"] != guard.policy.digest():
                _json({"status": "blocked_scope", "reason": "scope_hash_mismatch"})
                store.set_run_status(args.run_id, "blocked_scope")
                return 3
            plan_path = Path(args.plan).resolve()
            try:
                plan_path.relative_to(PROJECT_ROOT.resolve())
            except ValueError:
                store.set_run_status(args.run_id, "blocked_plan")
                _json({"status": "blocked_plan", "reason": "plan_outside_project_root"})
                return 3
            try:
                plan = validate_live_plan(load_mapping(plan_path))
            except (OSError, ValueError, LivePlanError) as exc:
                store.set_run_status(args.run_id, "blocked_plan")
                _json({"status": "blocked_plan", "reason": str(exc)})
                return 3
            network_policy = load_mapping(POLICY_PATH).get("network", {})
            if not isinstance(network_policy, dict) or not bool(network_policy.get("allow_real_targets", False)):
                store.set_run_status(args.run_id, "blocked_policy")
                store.record_event(args.run_id, "warning", "live_policy_gate", {"plan_digest": plan["plan_digest"]})
                _json({"status": "blocked_policy", "reason": "allow_real_targets_is_false", "plan_digest": plan["plan_digest"]})
                return 3
            if not guard.policy.confirmed or not guard.policy.allow_network_contact:
                store.set_run_status(args.run_id, "blocked_scope")
                _json({"status": "blocked_scope", "reason": "scope_confirmation_required", "plan_digest": plan["plan_digest"]})
                return 3
            store.record_event(
                args.run_id,
                "info",
                "live_plan_reviewed",
                {"plan_digest": plan["plan_digest"], "operator": plan["operator"], "target_count": len(plan["target_urls"])},
            )
            if not plan["manual_execution_confirmed"]:
                store.set_run_status(args.run_id, "blocked_plan")
                _json({"status": "blocked_plan", "reason": "manual_execution_confirmed_is_false", "plan_digest": plan["plan_digest"]})
                return 3
            if not args.execute_live:
                store.set_run_status(args.run_id, "awaiting_manual_execution")
                _json(
                    {
                        "status": "awaiting_manual_execution",
                        "reason": "pass --execute-live after final operator review",
                        "plan_digest": plan["plan_digest"],
                        "sequence": plan["sequence"],
                        "target_urls": plan["target_urls"],
                    }
                )
                return 0
            registry = ToolRegistry(search_paths=project_tool_search_paths(PROJECT_ROOT))
            adapters = {name: SafeToolAdapter(name, registry) for name in plan["sequence"]}
            result = _runner(store, guard).run_external(
                args.run_id,
                plan["target_urls"],
                adapters=adapters,
                execute=True,
                sequence=plan["sequence"],
                tool_args=plan["commands"],
            )
            result["plan_digest"] = plan["plan_digest"]
            _json(result)
            return 0 if result["status"] == "completed_tools" else 4
        if args.command == "resolve-scope":
            path = ScopeResolver().write_candidate(Path(args.output_dir), load_mapping(Path(args.snapshot)))
            _json({"candidate": str(path), "confirmed": False, "allow_network_contact": False})
            return 0
        if args.command == "stop":
            marker = PROJECT_ROOT / "STOP"
            marker.write_text("stop requested\n", encoding="utf-8")
            if args.run_id:
                store.set_run_status(args.run_id, "stopped")
            _json({"status": "stop_requested", "run_id": args.run_id})
            return 0
        if args.command in ("run", "resume"):
            run_id = args.run_id
            guard = _scope(args.scope)
            run = store.get_run(run_id)
            if not run:
                _json({"status": "error", "reason": "run_not_found"})
                return 2
            if run["scope_hash"] != guard.policy.digest():
                _json({"status": "blocked_scope", "reason": "scope_hash_mismatch"})
                return 3
            if args.command == "resume":
                (PROJECT_ROOT / "STOP").unlink(missing_ok=True)
            runner = _runner(store, guard)
            if args.local_lab:
                result = runner.run_local(run_id, load_mapping(Path(args.fixture)))
            else:
                result = runner.run_external(run_id, [])
            _json(result)
            return 0 if result["status"] in ("completed", "awaiting_adapter") else 4
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

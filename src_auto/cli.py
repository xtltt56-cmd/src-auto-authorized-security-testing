import argparse
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict

from .adapters import SafeToolAdapter, ToolRegistry, ToolSuite
from .ai import AITriage, ModelRouter
from .config import load_mapping
from .controls import BudgetGovernor
from .live_plan import LivePlanError, validate_live_plan
from .pipeline import PipelineRunner
from .remote_ai import DeepSeekProvider, OpenAIProvider, RemoteProviderError, RemoteReviewRequest
from .scope import ScopeGuard, ScopePolicy
from .scope_resolver import ScopeResolver
from .store import Store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "src_auto.sqlite3"
DEFAULT_LOCAL_SCOPE = PROJECT_ROOT / "config" / "targets" / "local-lab" / "scope_confirmed.yaml"
DEFAULT_LOCAL_FIXTURE = PROJECT_ROOT / "lab" / "fixtures.json"
POLICY_PATH = PROJECT_ROOT / "config" / "policy.yaml"
MODELS_PATH = PROJECT_ROOT / "config" / "models.yaml"
REMOTE_PROVIDER_NAMES = ("deepseek", "openai")


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _scope(path: str) -> ScopeGuard:
    return ScopeGuard(ScopePolicy.from_file(Path(path)))


def _runner(store: Store, guard: ScopeGuard) -> PipelineRunner:
    policy = load_mapping(POLICY_PATH)
    models = load_mapping(MODELS_PATH)
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
        "urlopen_fn": urlopen_fn,
    }
    if provider == "deepseek":
        return DeepSeekProvider(**common)
    if provider == "openai":
        return OpenAIProvider(**common)
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
    if not bool(config.get("enabled", False)):
        return None, {"status": "blocked_provider", "reason": "provider_disabled"}
    if not bool(config.get("manual_only", True)):
        return None, {"status": "blocked_provider", "reason": "manual_only_required"}
    return config, None


def _remote_status() -> Dict[str, Any]:
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
            "network_contact": False,
        }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="src-auto", description="Fail-closed SRC automation control layer")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="create a run record")
    new.add_argument("--target-id", required=True)
    new.add_argument("--scope", required=True)
    new.add_argument("--mode", choices=["local", "real"], default="local")
    run = sub.add_parser("run", help="run local lab or guarded external workflow")
    run.add_argument("--run-id", required=True)
    run.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    run.add_argument("--local-lab", action="store_true")
    run.add_argument("--fixture", default=str(DEFAULT_LOCAL_FIXTURE))
    live = sub.add_parser("run-live", help="run a manually reviewed external-tool plan")
    live.add_argument("--run-id", required=True)
    live.add_argument("--scope", required=True)
    live.add_argument("--plan", required=True)
    live.add_argument("--execute-live", action="store_true", help="required to start external tools")
    status = sub.add_parser("status", help="show runs")
    status.add_argument("--run-id")
    findings = sub.add_parser("findings", help="show findings")
    findings.add_argument("--run-id")
    sub.add_parser("reports", help="show generated reports")
    stop = sub.add_parser("stop", help="request a manual stop")
    stop.add_argument("--run-id")
    resume = sub.add_parser("resume", help="resume a stopped local run")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    resume.add_argument("--local-lab", action="store_true")
    resume.add_argument("--fixture", default=str(DEFAULT_LOCAL_FIXTURE))
    sub.add_parser("tool-status", help="verify installed external tools")
    sub.add_parser("model-status", help="check configured local model endpoint")
    remote_status = sub.add_parser("remote-status", help="show manually enabled remote AI providers without network contact")
    remote_status.set_defaults(command="remote-status")
    remote_preview = sub.add_parser("remote-preview", help="preview a redacted remote Finding review payload")
    remote_preview.add_argument("--run-id", required=True)
    remote_preview.add_argument("--finding-id", required=True)
    remote_preview.add_argument("--provider", choices=REMOTE_PROVIDER_NAMES, required=True)
    remote_preview.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    remote_triage = sub.add_parser("remote-triage", help="send one manually confirmed remote Finding review")
    remote_triage.add_argument("--run-id", required=True)
    remote_triage.add_argument("--finding-id", required=True)
    remote_triage.add_argument("--provider", choices=REMOTE_PROVIDER_NAMES, required=True)
    remote_triage.add_argument("--scope", default=str(DEFAULT_LOCAL_SCOPE))
    remote_triage.add_argument("--confirm-external", action="store_true", help="confirm one external AI transmission")
    remote_triage.add_argument("--confirm-digest", required=True, help="exact SHA-256 digest shown by remote-preview")
    resolve = sub.add_parser("resolve-scope", help="normalize an explicit rule snapshot into a candidate")
    resolve.add_argument("--snapshot", required=True)
    resolve.add_argument("--output-dir", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
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
            registry = ToolRegistry(search_paths=[PROJECT_ROOT / "vendor" / "bin", PROJECT_ROOT / "vendor" / "zap" / "ZAP_2.17.0"])
            _json({name: result.__dict__ for name, result in ToolSuite(registry).verify_all().items()})
            return 0
        if args.command == "model-status":
            models = load_mapping(MODELS_PATH)
            route = ModelRouter(models).route("triage", "normal")
            provider = ModelRouter(models).provider_for(route)
            available = provider.health() if provider is not None else False
            _json({"lane": route.lane, "provider": route.provider, "model": route.model, "endpoint": route.endpoint, "available": available})
            return 0 if available else 4
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
            registry = ToolRegistry(
                search_paths=[PROJECT_ROOT / "vendor" / "bin", PROJECT_ROOT / "vendor" / "zap" / "ZAP_2.17.0"]
            )
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

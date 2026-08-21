import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .adapters import SafeToolAdapter, ToolRegistry, ToolSuite
from .ai import AITriage, ModelRouter
from .config import load_mapping
from .controls import BudgetGovernor
from .live_plan import LivePlanError, validate_live_plan
from .pipeline import PipelineRunner
from .scope import ScopeGuard, ScopePolicy
from .scope_resolver import ScopeResolver
from .store import Store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "src_auto.sqlite3"
DEFAULT_LOCAL_SCOPE = PROJECT_ROOT / "config" / "targets" / "local-lab" / "scope_confirmed.yaml"
DEFAULT_LOCAL_FIXTURE = PROJECT_ROOT / "lab" / "fixtures.json"
POLICY_PATH = PROJECT_ROOT / "config" / "policy.yaml"
MODELS_PATH = PROJECT_ROOT / "config" / "models.yaml"


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

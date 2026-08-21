import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .adapters import ToolRegistry, ToolSuite
from .config import load_mapping
from .pipeline import PipelineRunner
from .scope import ScopeGuard, ScopePolicy
from .scope_resolver import ScopeResolver
from .store import Store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "src_auto.sqlite3"
DEFAULT_LOCAL_SCOPE = PROJECT_ROOT / "config" / "targets" / "local-lab" / "scope_confirmed.yaml"
DEFAULT_LOCAL_FIXTURE = PROJECT_ROOT / "lab" / "fixtures.json"


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _scope(path: str) -> ScopeGuard:
    return ScopeGuard(ScopePolicy.from_file(Path(path)))


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
            runner = PipelineRunner(store, guard, PROJECT_ROOT)
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

"""Real LLM + local fixture; optionally reuse the healthy Docker Business API."""
import argparse
import importlib.util
import json
import shutil
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src_auto.agent_actions import LocalActions
from src_auto.agent_contracts import Limits
from src_auto.agent_provider import configured_model
from src_auto.agent_resources import WindowsResources
from src_auto.agent_runner import AgentHistory, AgentRunner
from src_auto.config import load_mapping
from src_auto.local_labs import LocalLabManager
from src_auto.remote_ai import remote_session_consent_enabled
from src_auto.agent_cloud_budget import DeepSeekAgentBudget


def grade_loop(row, case, expected):
    """No finding is not a pass unless the specified private object was tested."""
    compared = [x for x in row.get("observations", [])
                if x.get("action") == "compare_object_authorization" and x.get("reference") == case]
    statuses = [200, 200, 403] if expected else [200, 403, 403]
    covered = any(x.get("status") == "ok" and x.get("access") == "private"
                  and x.get("statuses") == statuses and x.get("candidate") == bool(expected)
                  for x in compared)
    return (row["state"] == "completed" and row["steps"] >= 2 and row["modelCalls"] >= 3
            and row["requests"] >= 3 and row["candidates"] == expected and covered
            and not row["confirmed"] and not row["submissionReady"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--docker-lab", action="store_true", help="Reuse the existing healthy loopback Business API container; do not start or stop it.")
    parser.add_argument("--provider", choices=("local", "deepseek"), default="local")
    parser.add_argument("--allow-cloud", action="store_true", help="Explicit consent to send synthetic/redacted observations; paid calls.")
    args = parser.parse_args()
    remote_enabled = remote_session_consent_enabled("deepseek")
    if args.provider != "local" and not (remote_enabled and args.allow_cloud):
        raise ValueError("remote_ai_disabled_for_session")
    cloud_budget = DeepSeekAgentBudget.configured(ROOT) if args.provider == "deepseek" else None
    directory = (ROOT / args.output).resolve()
    directory.relative_to(ROOT)
    if directory.exists():
        raise RuntimeError("new_output_directory_required")
    manager = LocalLabManager(ROOT, ROOT / "config/labs/local_labs.json", ROOT / "docker-compose.local-labs.yml")
    server = thread = None
    if args.docker_lab:
        if manager.status("business-api")["status"] != "READY":
            raise RuntimeError("healthy_docker_business_api_required")
    else:
        spec = importlib.util.spec_from_file_location("selection_fixture", str(ROOT / "lab/business-api/app.py"))
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        server = app.build_server("127.0.0.1", 8084)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
    directory.mkdir(parents=True)
    results = []
    try:
        for case, expected in (("case-01", 1), ("case-11", 0)):
            root = directory / case
            for relative in ("config/validation/local_only.json", "config/models.yaml", "config/policy.yaml", "config/agent/permissions.json"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(ROOT / relative), str(target))
            path = root / "config/agent/permissions.json"
            permissions = load_mapping(path)
            permissions["private_objects"] = [case]
            permissions["public_objects"] = ["case-16"]
            path.write_text(json.dumps(permissions, ensure_ascii=False), encoding="utf-8")
            limits = Limits(max_steps=4, max_model_calls=6, max_seconds=600)
            cancel = threading.Event()
            actions = LocalActions(root, manager, "business-api", limits, cancel)
            # This acceptance targets one chosen object, not automatic full-manifest coverage.
            # Keep the valid permission manifest, but do not offer the unrelated public control
            # as a selectable reference. No vulnerable/fixed answer is disclosed to the model.
            actions.references = ["entry", case]
            resources = WindowsResources(load_mapping(ROOT / "config/policy.yaml"))
            model = configured_model(ROOT, args.provider, remote_enabled, args.allow_cloud)
            row = AgentRunner(root, AgentHistory(root), model, actions, limits=limits,
                              provider=args.provider, resource_check=resources.check,
                              cloud_budget=cloud_budget).run("business-api", "api-permissions", cancel)
            passed = grade_loop(row, case, expected)
            result = {"case": case, "model": model.provider.model, "passed": passed, "expected_candidates": expected, "run": row}
            results.append(result)
            (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: row[k] for k in ("state", "reason", "steps", "requests", "modelCalls", "candidates", "tokens")}, ensure_ascii=False), flush=True)
        scope = "healthy Docker Business API on 127.0.0.1:8084" if args.docker_lab else "owned native loopback fixture, not Docker"
        report = {"ok": all(x["passed"] for x in results), "scope": scope + ", real LLM decisions, isolated test history", "results": results}
        (directory / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "passed": sum(x["passed"] for x in results), "total": len(results)}), flush=True)
        return 0 if report["ok"] else 1
    finally:
        if server is not None:
            server.shutdown()
            thread.join(5)
            server.server_close()
        if "model" in locals() and model.local:
            model.provider._request("/api/generate", {"model": model.provider.model, "keep_alive": 0})


if __name__ == "__main__":
    raise SystemExit(main())

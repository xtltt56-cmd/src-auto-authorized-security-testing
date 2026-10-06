"""Exercise the real bounded Agent workflow on the five pinned loopback labs.

This script does not start/stop containers, run ZAP active scans, access external
targets, submit reports, or read/print credentials. It uses an isolated Agent
history/report root, while DeepSeek budget reservations use the project ledger.
"""
import argparse
import json
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src_auto.agent_actions import LocalActions
from src_auto.agent_cloud_budget import DeepSeekAgentBudget
from src_auto.agent_contracts import Limits
from src_auto.agent_provider import configured_model
from src_auto.agent_resources import WindowsResources
from src_auto.agent_runner import AgentHistory, AgentRunner
from src_auto.config import load_mapping
from src_auto.local_labs import LocalLabManager
from src_auto.remote_ai import remote_session_consent_enabled


LABS = ("juice-shop", "dvwa", "webgoat", "vampi", "business-api")
REQUIRED_ACTIONS = {
    "juice-shop": ("run_local_regression",),
    "dvwa": ("run_local_regression", "validate_controlled_inputs"),
    "webgoat": ("run_local_regression",),
    "vampi": ("run_local_regression",),
    "business-api": ("run_local_regression", "compare_object_authorization_matrix"),
}
CONFIGS = (
    "config/validation/local_only.json",
    "config/validation/local_regression_cases.json",
    "config/agent/permissions.json",
    "config/models.yaml",
    "config/policy.yaml",
)


def recipe_passed(action, observation):
    if action == "run_local_regression":
        return (observation.get("profileStatus") == "COMPLETED"
                and observation.get("caseCount", 0) > 0
                and observation.get("passedCount") == observation.get("caseCount")
                and observation.get("failedCount") == 0
                and observation.get("blockedCount") == 0)
    if action == "validate_controlled_inputs":
        return observation.get("profileStatus") == "COMPLETED" and observation.get("requestCount", 0) >= 4
    if action == "compare_object_authorization_matrix":
        return (observation.get("profileStatus") == "COMPLETED"
                and observation.get("objectsTested") == 20 and observation.get("requests") == 60)
    return False


def grade(lab_id, row):
    observations = row.get("observations", [])
    complete = {item.get("action") for item in observations
                if item.get("action") in REQUIRED_ACTIONS[lab_id] and recipe_passed(item.get("action"), item)}
    return {
        "passed": row.get("state") == "completed" and set(REQUIRED_ACTIONS[lab_id]) <= complete
                  and row.get("modelCalls", 0) > 0 and not row.get("confirmed") and not row.get("submissionReady"),
        "required_actions": list(REQUIRED_ACTIONS[lab_id]),
        "completed_required_actions": [x for x in REQUIRED_ACTIONS[lab_id] if x in complete],
        "state": row.get("state"),
        "reason": row.get("reason"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("deepseek",), default="deepseek")
    parser.add_argument("--allow-cloud", action="store_true", help="Explicitly authorize paid DeepSeek calls for these local synthetic observations.")
    parser.add_argument("--output-name", default="", help="Optional new subdirectory name under validation/.")
    args = parser.parse_args()
    if not args.allow_cloud or not remote_session_consent_enabled("deepseek"):
        raise SystemExit("blocked: require --allow-cloud and SRC_AUTO_DEEPSEEK_CONSENT enabled in this process")

    output_name = args.output_name or "agent-deepseek-five-labs-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    if not output_name.replace("-", "").replace("_", "").isalnum() or output_name in {".", ".."}:
        raise SystemExit("invalid output directory name")
    output_root = (ROOT / "validation" / output_name).resolve()
    output_root.relative_to(ROOT)
    if output_root.exists():
        raise SystemExit("output directory already exists")
    output_root.mkdir(parents=True)

    manager = LocalLabManager(ROOT, ROOT / "config/labs/local_labs.json", ROOT / "docker-compose.local-labs.yml")
    resources = WindowsResources(load_mapping(ROOT / "config/policy.yaml"))
    cloud_budget = DeepSeekAgentBudget.configured(ROOT)
    summary = {"scope": "only fixed project Docker labs on 127.0.0.1; no external targets or ZAP active scan",
               "provider": "deepseek", "model": "deepseek-flash", "output_root": str(output_root.relative_to(ROOT).as_posix()),
               "results": []}

    for lab_id in LABS:
        status = manager.status(lab_id).get("status")
        if status != "READY":
            summary["results"].append({"lab_id": lab_id, "passed": False, "blocked_before_run": status})
            continue
        run_root = output_root / lab_id
        for relative in CONFIGS:
            source, target = ROOT / relative, run_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(source), str(target))

        limits = Limits()
        cancel = threading.Event()
        actions = LocalActions(run_root, manager, lab_id, limits, cancel, mode="local-assessment")
        model = configured_model(ROOT, "deepseek", True, True)
        history = AgentHistory(run_root)
        runner = AgentRunner(run_root, history, model, actions, limits=limits,
                             provider="deepseek", resource_check=resources.check,
                             cloud_budget=cloud_budget)
        row = runner.run(lab_id, "local-assessment", cancel)
        verdict = grade(lab_id, row)
        result = {"lab_id": lab_id, "grade": verdict,
                  "counts": {key: row.get(key) for key in ("steps", "requests", "modelCalls", "tokens", "candidates", "estimatedCostCny", "reservedCostCny")},
                  "observations": [{key: item.get(key) for key in ("id", "action", "status", "profileStatus", "caseCount", "passedCount", "failedCount", "blockedCount", "requestCount", "objectsTested", "candidateCount", "candidateKinds", "candidateObjects", "confirmed", "submissionReady") if key in item}
                                   for item in row.get("observations", [])],
                  "report": row.get("reportId"),
                  "confirmed": row.get("confirmed", False), "submission_ready": row.get("submissionReady", False)}
        (run_root / "acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary["results"].append(result)
        print(json.dumps({"lab": lab_id, "passed": verdict["passed"], "state": row.get("state"),
                          "reason": row.get("reason"), "steps": row.get("steps"), "requests": row.get("requests"),
                          "model_calls": row.get("modelCalls"), "candidates": row.get("candidates")}, ensure_ascii=False), flush=True)
        if model.local:
            model.provider._request("/api/generate", {"model": model.provider.model, "prompt": "", "stream": False,
                                                       "think": False, "options": {"num_predict": 1}, "keep_alive": 0})

    summary["passed"] = len(summary["results"]) == len(LABS) and all(x.get("grade", {}).get("passed", False) for x in summary["results"])
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "labs": len(summary["results"]),
                      "passed_count": sum(bool(x.get("grade", {}).get("passed")) for x in summary["results"]),
                      "summary": summary["output_root"] + "/summary.json"}, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

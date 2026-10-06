"""Opt-in local model proof, no cloud calls; output contains no credentials."""
import argparse
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src_auto.agent_actions import LocalActions
from src_auto.agent_contracts import Limits
from src_auto.agent_provider import configured_model
from src_auto.agent_runner import AgentHistory, AgentRunner
from src_auto.agent_resources import WindowsResources
from src_auto.config import load_mapping
from src_auto.local_labs import LocalLabManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", default="business-api", choices=["business-api", "juice-shop", "dvwa", "webgoat", "vampi"])
    parser.add_argument("--mode", choices=["api-permissions", "candidate-review"])
    args = parser.parse_args()
    mode = args.mode or ("api-permissions" if args.lab == "business-api" else "candidate-review")
    if mode == "api-permissions" and args.lab != "business-api":
        parser.error("api-permissions requires the fixed business-api lab")
    manager = LocalLabManager(ROOT, ROOT / "config/labs/local_labs.json", ROOT / "docker-compose.local-labs.yml")
    cancel = threading.Event()
    actions = LocalActions(ROOT, manager, args.lab, Limits(), cancel)
    model = configured_model(ROOT, "local")
    resources = WindowsResources(load_mapping(ROOT / "config/policy.yaml"))
    result = AgentRunner(ROOT, AgentHistory(ROOT), model, actions, resource_check=resources.check).run(args.lab, mode, cancel)
    directory = ROOT / "validation/agent-upgrade"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "live-model-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("id", "state", "reason", "steps", "requests", "modelCalls", "tokens", "reportId")}, ensure_ascii=False))
    return 0 if result["state"] == "completed" and result["steps"] >= 2 else 1


if __name__ == "__main__": raise SystemExit(main())

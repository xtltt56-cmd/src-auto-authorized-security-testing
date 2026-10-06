"""Real Windows resource checks + real synthetic loopback requests, never AI."""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT))
    from src_auto.agent_resources import WindowsResources
    from src_auto.config import load_mapping
    from src_auto.controls import DiskGuard, StopController
    from src_auto.pipeline import PipelineRunner
    from src_auto.scope import ScopeGuard
    from src_auto.store import Store
    from tests.test_local_application import LocalApplicationHTTPTests

    started = datetime.now(timezone(timedelta(hours=8)))
    output = ROOT / "validation" / "local-application-l1" / (started.strftime("%Y%m%d-%H%M%S-%f") + "-smoke")
    output.mkdir(parents=True, exist_ok=False)
    fixture, store = LocalApplicationHTTPTests(), None
    fixture.setUp()
    try:
        scope, plan = fixture.plan(paths=("/", "/api/health"))
        (output / "scope.json").write_text(json.dumps(scope.canonical(), ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "plan.json").write_text(json.dumps(plan.canonical(), ensure_ascii=False, indent=2), encoding="utf-8")
        policy = load_mapping(ROOT / "config" / "policy.yaml")
        store = Store(output / "state.sqlite3")
        run_id = store.create_run(scope.target_id, scope.digest(), "local")
        runner = PipelineRunner(store, ScopeGuard(scope), ROOT, resource_guard=WindowsResources(policy),
                                disk_guard=DiskGuard(ROOT, policy.get("disk_warning_gb", 80), policy.get("disk_hard_limit_gb", 90)),
                                stop_controller=StopController(ROOT / "STOP"))
        timer = time.monotonic()
        result = runner.run_local_application(run_id, plan)
        elapsed = round(time.monotonic() - timer, 3)
        checkpoint = store.load_checkpoint(run_id, "local_application_observations")
        secret_retained = "SYNTHETIC_PRIVATE" in json.dumps(checkpoint)
        resource_records = [json.loads(row[0]) for row in store.conn.execute(
            "SELECT payload_json FROM events WHERE run_id=? AND message='resource_guard'", (run_id,))]
        expected = [("GET", "/"), ("GET", "/api/health")]
        summary = dict(result, started_at=started.isoformat(), elapsed_seconds=elapsed, resources_mocked=False,
                       actual_received_requests=fixture.received, resource_checks=resource_records,
                       external_target_gate=policy.get("network", {}).get("allow_real_targets"),
                       synthetic_secret_retained=secret_retained, real_quant_application_contact=False,
                       success=result["status"] == "completed_observation" and fixture.received == expected
                               and not secret_retained and bool(resource_records)
                               and all(row.get("known") and row.get("allowed") for row in resource_records))
        report = output / "summary.json"
        report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(dict(summary, report_path=str(report)), ensure_ascii=False, indent=2))
        return 0 if summary["success"] else 1
    finally:
        if store is not None:
            store.close()
        fixture.tearDown()


if __name__ == "__main__":
    sys.exit(main())

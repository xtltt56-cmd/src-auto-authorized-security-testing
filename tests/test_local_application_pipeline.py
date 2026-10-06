import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src_auto import cli
from src_auto.controls import ResourceGuard
from src_auto.pipeline import PipelineRunner
from src_auto.scope import ScopeGuard, ScopePolicy
from src_auto.store import Store
from tests import test_local_application as local_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LocalApplicationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.fixture = local_fixture.LocalApplicationHTTPTests()
        self.fixture.setUp()
        self.temp = tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT / "validation"))
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state.sqlite3")
        self.scope, self.plan = self.fixture.plan(paths=("/", "/api/health"))
        self.run_id = self.store.create_run(self.scope.target_id, self.scope.digest(), "local")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
        self.fixture.tearDown()

    def runner(self):
        return PipelineRunner(self.store, ScopeGuard(self.scope), self.root,
                              resource_guard=ResourceGuard(metrics_fn=lambda: (1, 1)))

    def write_inputs(self):
        scope_path, plan_path = self.root / "scope.json", self.root / "plan.json"
        scope_path.write_text(json.dumps(self.scope.canonical()), encoding="utf-8")
        plan_path.write_text(json.dumps(self.plan.canonical()), encoding="utf-8")
        return str(scope_path), str(plan_path)

    def run_cli(self, argv):
        stream = io.StringIO()
        with patch.object(cli, "PROJECT_ROOT", self.root), patch.object(cli, "DB_PATH", self.store.path), redirect_stdout(stream):
            code = cli.main(argv + ["--json"])
        return code, json.loads(stream.getvalue())

    def test_pipeline_saves_real_minimal_observations_and_no_cloud_calls(self):
        with patch("src_auto.ai.AITriage.classify", side_effect=AssertionError("no AI in L1")):
            result = self.runner().run_local_application(self.run_id, self.plan)
        self.assertEqual(result["status"], "completed_observation")
        self.assertEqual(result["requests"], 2)
        self.assertEqual(self.store.get_run(self.run_id)["status"], "completed_observation")
        checkpoint = self.store.load_checkpoint(self.run_id, "local_application_observations")
        self.assertEqual(len(checkpoint["observations"]), 2)
        self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(checkpoint))
        self.assertEqual(self.store.list_findings(self.run_id), [])

    def test_completed_run_cannot_be_replayed_and_target_lease_is_released(self):
        self.runner().run_local_application(self.run_id, self.plan)
        received = list(self.fixture.received)
        result = self.runner().run_local_application(self.run_id, self.plan)
        self.assertEqual(result["status"], "blocked_run")
        self.assertEqual(self.fixture.received, received)
        other = self.store.create_run(self.scope.target_id, self.scope.digest(), "local")
        self.assertEqual(self.runner().run_local_application(other, self.plan)["status"], "completed_observation")

    def test_resource_and_stop_gates_prevent_network(self):
        (self.root / "STOP").write_text("test", encoding="utf-8")
        self.assertEqual(self.runner().run_local_application(self.run_id, self.plan)["status"], "cancelled")
        self.assertEqual(self.fixture.received, [])

    def test_atomic_claim_rejects_another_run_on_same_origin(self):
        lease = self.store.claim_local_application(self.run_id, self.scope.digest(), self.scope.target_id, self.scope.local_web.origin)
        other = self.store.create_run("other-name", self.scope.digest(), "local")
        with self.assertRaisesRegex(RuntimeError, "local_application_conflict"):
            self.store.claim_local_application(other, self.scope.digest(), "other-name", self.scope.local_web.origin)
        self.store.release_local_application(self.run_id, lease)

    def test_stale_owner_is_interrupted_without_replaying_requests(self):
        self.store.claim_local_application(self.run_id, self.scope.digest(), self.scope.target_id, self.scope.local_web.origin)
        other = self.store.create_run(self.scope.target_id, self.scope.digest(), "local")
        with patch("src_auto.agent_runner.owner_is_alive", return_value=False):
            token = self.store.claim_local_application(other, self.scope.digest(), self.scope.target_id, self.scope.local_web.origin)
        self.assertEqual(self.store.get_run(self.run_id)["status"], "interrupted")
        self.assertEqual(self.fixture.received, [])
        self.store.release_local_application(other, token)

    def test_resource_failure_and_run_scope_mismatch_do_not_issue_requests(self):
        runner = self.runner()
        runner.resource_guard = ResourceGuard(metrics_fn=lambda: (99, 99))
        self.assertEqual(runner.run_local_application(self.run_id, self.plan)["reason"], "paused_resource")
        self.assertEqual(self.fixture.received, [])
        other = self.store.create_run(self.scope.target_id, "different-approval", "local")
        self.assertEqual(self.runner().run_local_application(other, self.plan)["status"], "blocked_run")
        self.assertEqual(self.fixture.received, [])

    def test_cli_review_and_missing_execution_switch_never_contact_service(self):
        scope_path, plan_path = self.write_inputs()
        with patch("http.client.HTTPConnection.connect", side_effect=AssertionError("preview must stay offline")):
            code, result = self.run_cli(["local-app-review", "--scope", scope_path, "--plan", plan_path])
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "local_plan_reviewed")
            self.assertFalse(result["network_contact"])
            code, result = self.run_cli(["local-app-run", "--scope", scope_path, "--plan", plan_path, "--run-id", self.run_id])
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "awaiting_manual_execution")
        self.assertEqual(self.fixture.received, [])

    def test_cli_paths_outside_project_are_rejected_without_reading_or_network(self):
        scope_path, plan_path = self.write_inputs()
        code, result = self.run_cli(["local-app-review", "--scope", str(self.root.parent / "outside.json"), "--plan", plan_path])
        self.assertEqual(code, 3)
        self.assertEqual(result["reason"], "scope_outside_project_root")
        self.assertEqual(self.fixture.received, [])

    def test_legacy_scope_cannot_enter_local_execution_lane(self):
        scope_path, plan_path = self.write_inputs()
        Path(scope_path).write_text(json.dumps({"target_id": "legacy", "allowed_hosts": ["127.0.0.1"],
                                              "allowed_ports": [self.fixture.server.server_port],
                                              "confirmed": True, "allow_network_contact": True}), encoding="utf-8")
        code, result = self.run_cli(["local-app-review", "--scope", scope_path, "--plan", plan_path])
        self.assertEqual(code, 3)
        self.assertEqual(result["reason"], "local_scope_required")
        self.assertEqual(self.fixture.received, [])

    def test_explicit_cli_run_works_with_external_gate_closed_and_no_ai(self):
        scope_path, plan_path = self.write_inputs()
        policy_path = self.root / "policy.json"
        policy_path.write_text(json.dumps({"network": {"allow_real_targets": False}}), encoding="utf-8")
        with patch.object(cli, "POLICY_PATH", policy_path), patch("src_auto.agent_resources.WindowsResources.check", return_value={"allowed": True, "known": True}), patch("src_auto.ai.AITriage.classify", side_effect=AssertionError("no AI")):
            code, result = self.run_cli(["local-app-run", "--scope", scope_path, "--plan", plan_path,
                                         "--run-id", self.run_id, "--execute-local"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "completed_observation")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(self.fixture.received, [("GET", "/"), ("GET", "/api/health")])


if __name__ == "__main__":
    unittest.main()

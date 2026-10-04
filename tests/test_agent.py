"""Controlled Agent regressions: no live cloud or external targets."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src_auto.agent_contracts import Decision, Limits
from src_auto.agent_runner import AgentRunner, AgentHistory, project_path
from src_auto.agent_actions import GuardedHTTP, LocalActions


def decision(action, reference="entry", evidence=None):
    return json.dumps({"action": action, "reference": reference,
                       "evidence": evidence or [], "reason": "根据观察进行下一项检查"})


class ScriptedModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        return {"text": next(self.outputs), "input_tokens": 30, "output_tokens": 20}


class FakeActions:
    scope_hash = "fixed-scope"
    config_hash = "fixed-config"
    references = ["entry", "case-01"]
    requests = 0

    def execute(self, value):
        self.requests += 1
        return {"status": "ok", "summary": "只读合成观察", "candidate": value.action == "compare_object_authorization"}


class ContractTests(unittest.TestCase):
    def test_strict_decision(self):
        value = Decision.parse(decision("inspect_headers"), ["entry"], [])
        self.assertEqual(value.action, "inspect_headers")

    def test_twenty_rejected_inputs(self):
        invalid = [None, [], {}, "not-json", '```json\n{}\n```', '{"action":"finish","action":"shell"}']
        base = json.loads(decision("inspect_headers"))
        invalid += [dict(base, action=x) for x in ("shell", "POST", "download_template", "submit_report")]
        invalid += [dict(base, reference=x) for x in ("https://example.org", "../private", "foreign-case")]
        invalid += [dict(base, evidence=x) for x in (["foreign-evidence"], "o1", [1])]
        invalid += [dict(base, **{x: "secret"}) for x in ("url", "command", "apiKey", "confirmed")]
        self.assertEqual(len(invalid), 20)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Decision.parse(json.dumps(value) if not isinstance(value, str) else value, ["entry"], [])

    def test_limits_are_mandatory_and_bounded(self):
        self.assertEqual(Limits().max_steps, 8)
        for key in ("max_steps", "max_requests", "max_model_calls", "max_seconds", "max_tokens"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Limits.from_mapping({key: 0})
        for key, value in (("max_requests", 31), ("max_seconds", 901), ("max_tokens", 20001)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Limits.from_mapping({key: value})


class HTTPGateTests(unittest.TestCase):
    def test_foreign_origin_and_credentials_never_reach_opener(self):
        calls = []
        class Opener:
            def open(self, *args, **kwargs):
                calls.append(args)
                raise AssertionError("must not open")
        client = GuardedHTTP("http://127.0.0.1:8084/health", Limits(), threading.Event(), opener=Opener())
        for url in ("https://example.org", "http://localhost:8084/health", "http://127.0.0.1:3000/", "file:///private", "http://user:secret@127.0.0.1:8084/"):
            with self.subTest(url=url), self.assertRaisesRegex(RuntimeError, "scope_blocked"):
                client.fetch(url)
        self.assertEqual(calls, [])

    def test_request_limit_counts_failures(self):
        class Opener:
            def open(self, *args, **kwargs):
                raise OSError("unreachable")
        client = GuardedHTTP("http://127.0.0.1:8084/health", Limits(max_requests=1), threading.Event(), opener=Opener())
        with self.assertRaises(OSError): client.fetch(client.entry)
        self.assertEqual(client.requests, 1)
        with self.assertRaisesRegex(RuntimeError, "request_limit"): client.fetch(client.entry)

    def test_redirect_to_foreign_host_is_stopped_before_second_request(self):
        calls = []
        class Response:
            headers = {"Location": "https://example.org/outside"}
            closed = False
            def getcode(self): return 302
            def close(self): self.closed = True
        response = Response()
        class Opener:
            def open(self, request, **kwargs):
                calls.append(request.full_url); return response
        client = GuardedHTTP("http://127.0.0.1:8084/health", Limits(), threading.Event(), opener=Opener())
        with self.assertRaisesRegex(RuntimeError, "scope_blocked"): client.fetch(client.entry)
        self.assertEqual(calls, [client.entry])
        self.assertTrue(response.closed)

    def test_output_path_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "agent_path_outside_project"):
                project_path(Path(directory), "..", "outside.md")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.history = AgentHistory(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, outputs, limits=None, actions=None):
        return AgentRunner(self.root, self.history, ScriptedModel(outputs), actions or FakeActions(),
                           limits=limits or Limits(), resource_check=lambda: {"allowed": True})

    def test_feedback_and_manual_candidate_gate(self):
        runner = self.runner([decision("inspect_headers"), decision("compare_object_authorization", "case-01", ["o1"]), decision("finish", evidence=["o2"])])
        result = runner.run("business-api", "api-permissions", threading.Event())
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["steps"], 2)
        self.assertEqual(result["candidates"], 1)
        self.assertEqual(runner.model.contexts[1]["observations"][0]["id"], "o1")
        self.assertFalse(result["confirmed"])
        self.assertFalse(result["submissionReady"])
        self.assertTrue((self.root / result["reportId"]).is_file())

    def test_stop_before_model(self):
        (self.root / "STOP").touch()
        runner = self.runner([])
        result = runner.run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["modelCalls"], 0)

    def test_cancel_before_model(self):
        cancel = threading.Event(); cancel.set()
        result = self.runner([]).run("business-api", "candidate-review", cancel)
        self.assertEqual(result["state"], "cancelled")

    def test_one_format_repair_only(self):
        result = self.runner(["{}", "{}"]).run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "needs-human")
        self.assertEqual(result["modelCalls"], 2)
        self.assertEqual(result["steps"], 0)

    def test_steps_limit_and_no_repeat(self):
        result = self.runner([decision("inspect_headers"), decision("inspect_headers")]).run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "needs-human")
        self.assertEqual(result["steps"], 1)

    def test_model_failure_is_not_success(self):
        result = self.runner([]).run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "paused")
        self.assertEqual(result["reason"], "model_unavailable")

    def test_history_interrupted_without_autoresume(self):
        row = self.history.create("business-api", "candidate-review", "local", Limits(), FakeActions())
        self.history.update(row["id"], state="running")
        with patch("src_auto.agent_runner.owner_is_alive", return_value=False):
            restored = AgentHistory(self.root)
        self.assertEqual(restored.get(row["id"])["state"], "interrupted")

    def test_second_reader_does_not_interrupt_a_live_owner(self):
        row = self.history.create("business-api", "candidate-review", "local", Limits(), FakeActions())
        restored = AgentHistory(self.root)
        self.assertEqual(restored.get(row["id"])["state"], "queued")
        with self.assertRaisesRegex(RuntimeError, "agent_operation_conflict"):
            restored.create("business-api", "candidate-review", "local", Limits(), FakeActions())

    def test_reader_detects_owner_exit_without_a_dashboard_restart(self):
        row = self.history.create("business-api", "candidate-review", "local", Limits(), FakeActions())
        with patch("src_auto.agent_runner.owner_is_alive", return_value=False):
            self.assertEqual(self.history.list()[0]["state"], "interrupted")
        self.assertEqual(self.history.get(row["id"])["reason"], "service_interrupted")

    def test_unknown_owner_liveness_is_not_treated_as_dead(self):
        row = self.history.create("business-api", "candidate-review", "local", Limits(), FakeActions())
        with patch("src_auto.agent_runner.owner_is_alive", return_value=None):
            restored = AgentHistory(self.root)
        self.assertEqual(restored.get(row["id"])["state"], "queued")

    def test_selected_candidate_cannot_finish_without_review(self):
        actions = FakeActions(); actions.references = ["entry", "candidate"]
        result = self.runner([decision("inspect_headers"), decision("finish", evidence=["o1"])], actions=actions).run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "needs-human")
        self.assertEqual(result["reason"], "candidate_review_incomplete")

    def test_finish_must_reference_relevant_permission_evidence(self):
        result = self.runner([decision("inspect_headers"), decision("compare_object_authorization", "case-01"), decision("finish", evidence=["o1"])]).run("business-api", "api-permissions", threading.Event())
        self.assertEqual(result["state"], "needs-human")
        self.assertEqual(result["reason"], "permission_check_incomplete")

    def test_changed_scope_cannot_resume(self):
        result = self.runner([]).run("business-api", "candidate-review", threading.Event())
        actions = FakeActions(); actions.scope_hash = "changed"
        with self.assertRaisesRegex(ValueError, "resume_context_changed"):
            self.runner([], actions=actions).run("business-api", "candidate-review", threading.Event(), resume_id=result["id"])

    def test_resume_uses_recorded_limits_and_keeps_observations(self):
        runner = self.runner([decision("inspect_headers")])
        first = runner.run("business-api", "candidate-review", threading.Event())
        self.assertEqual(first["state"], "paused")
        second = self.runner([decision("finish", evidence=["o1"])], limits=Limits(max_steps=1)).run("business-api", "candidate-review", threading.Event(), resume_id=first["id"])
        self.assertEqual(second["state"], "completed")
        self.assertEqual(second["limits"]["max_steps"], 8)
        self.assertEqual(len(second["observations"]), 1)

    def test_resource_limit_before_model(self):
        runner = self.runner([])
        runner.resource_check = lambda: {"allowed": False, "known": True}
        result = runner.run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "paused")
        self.assertEqual(result["modelCalls"], 0)

    def test_unmeasured_resources_do_not_grant_permission(self):
        runner = AgentRunner(self.root, self.history, ScriptedModel([]), FakeActions())
        result = runner.run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "paused")
        self.assertEqual(result["modelCalls"], 0)

    def test_max_steps_allow_finish_without_another_tool(self):
        result = self.runner([decision("inspect_headers"), decision("finish", evidence=["o1"])], limits=Limits(max_steps=1)).run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "completed")

    def test_invalid_action_reference_is_repaired_without_network(self):
        result = self.runner([decision("discover_surface", "case-01"), decision("inspect_headers"), decision("finish", evidence=["o1"])]).run("business-api", "candidate-review", threading.Event())
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["steps"], 1)
        self.assertEqual(result["trace"][0]["result"], "rejected")


if __name__ == "__main__":
    unittest.main()

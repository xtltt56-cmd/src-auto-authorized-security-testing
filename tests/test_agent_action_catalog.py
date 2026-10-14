"""Task-owned menus: local synthetic inputs only, no real network/model."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src_auto.agent_actions import LocalActions
from src_auto.agent_contracts import Decision, Limits, ActionRegistry, ActionSpec, CATALOG_VERSION
from src_auto.agent_runner import AgentHistory, AgentRunner
from src_auto.runtime_policy import RuntimePolicy
from tests.test_agent import FakeActions, ScriptedModel, decision


class ActionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parents[1] / 'validation'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def actions(self, lab='juice-shop', mode='candidate-review'):
        permissions = dict(private_objects=['case-{:02d}'.format(i) for i in range(1, 11)],
            public_objects=['case-{:02d}'.format(i) for i in range(11, 21)],
            owner='buyer-a', peer='buyer-b', anonymous='anonymous')
        manager = SimpleNamespace(spec=lambda name: SimpleNamespace(health_url='http://127.0.0.1:3000/', host_port=3000))
        policy = RuntimePolicy.from_mapping(dict(allowed_hosts=['127.0.0.1'], allowed_ports=[3000]))
        with patch('src_auto.agent_actions.RuntimePolicy.from_file', return_value=policy), \
             patch('src_auto.agent_actions.load_mapping', side_effect=lambda path: permissions if path.name == 'permissions.json' else {}):
            return LocalActions(self.root, manager, lab, Limits(), threading.Event(), mode=mode)

    def test_fixed_lab_menu_never_inherits_specialized_actions(self):
        specialized = {'inspect_local_route', 'analyze_passive_capture', 'compare_business_object', 'validate_business_controls'}
        for lab in ('juice-shop', 'dvwa', 'webgoat', 'vampi', 'business-api'):
            with self.subTest(lab=lab):
                self.assertFalse(specialized & set(self.actions(lab).capabilities))

    def test_known_but_unavailable_action_never_reaches_executor(self):
        actions = FakeActions()
        actions.capabilities = ['inspect_headers', 'finish', 'request_human_review']
        actions.references = ['entry']
        model = ScriptedModel([decision('analyze_passive_capture'), decision('inspect_headers'), decision('finish', evidence=['o1'])])
        calls = []
        original = actions.execute
        actions.execute = lambda value: (calls.append(value.action), original(value))[1]
        runner = AgentRunner(self.root, AgentHistory(self.root), model, actions, resource_check=lambda: {'allowed': True})
        result = runner.run('juice-shop', 'candidate-review', threading.Event())
        self.assertNotIn('analyze_passive_capture', calls)
        self.assertEqual(result['steps'], 1)

    def test_decision_validates_task_action_reference_binding(self):
        with self.assertRaisesRegex(ValueError, 'action_reference_mismatch'):
            Decision.parse(decision('inspect_local_route', 'entry'), ['entry', 'route-001'], [],
                           action_references={'inspect_local_route': ['route-001']})

    def test_control_handoff_is_not_a_tool_call(self):
        model = ScriptedModel([decision('request_human_review')])
        actions = self.actions()
        runner = AgentRunner(self.root, AgentHistory(self.root), model, actions, resource_check=lambda: {'allowed': True})
        result = runner.run('juice-shop', 'candidate-review', threading.Event())
        self.assertEqual((result['state'], result['reason'], result['steps'], result['requests']),
                         ('needs-human', 'request_human_review', 0, 0))

    def run_script(self, outputs, actions=None):
        model = ScriptedModel(outputs)
        actions = actions or FakeActions()
        runner = AgentRunner(self.root, AgentHistory(self.root), model, actions, resource_check=lambda: {'allowed': True})
        return runner.run('business-api', 'candidate-review', threading.Event()), model, actions

    def test_menu_matches_registered_callable_handlers_and_bound_references(self):
        for lab in ('juice-shop', 'dvwa', 'webgoat', 'vampi', 'business-api'):
            actions = self.actions(lab, 'local-assessment')
            self.assertEqual(set(actions.capabilities) - {'finish', 'request_human_review'}, set(actions.action_registry.specs))
            for spec in actions.action_registry.specs.values():
                self.assertTrue(callable(spec.handler))
                self.assertLessEqual(set(spec.references), set(actions.references))

    def test_matrix_and_dvwa_controls_only_registered_in_correct_mode_and_lab(self):
        self.assertIn('validate_controlled_inputs', self.actions('dvwa', 'local-assessment').capabilities)
        self.assertNotIn('validate_controlled_inputs', self.actions('juice-shop', 'local-assessment').capabilities)
        self.assertNotIn('validate_controlled_inputs', self.actions('dvwa').capabilities)
        self.assertIn('compare_object_authorization_matrix', self.actions('business-api', 'local-assessment').capabilities)
        self.assertNotIn('compare_object_authorization_matrix', self.actions('vampi', 'local-assessment').capabilities)

    def test_direct_wrong_task_action_and_reference_make_zero_requests(self):
        actions = self.actions()
        with patch.object(actions.client, 'fetch', side_effect=AssertionError('must not request')) as fetch:
            for action, reference in (('analyze_passive_capture', 'entry'), ('inspect_headers', 'case-01')):
                with self.assertRaises(RuntimeError): actions.execute(Decision(action, reference, (), '合成错误'))
            fetch.assert_not_called()

    def test_registry_rejects_unknown_control_duplicate_or_unbound_handler(self):
        for name, refs, handler in (('shell', ('entry',), lambda _: {}), ('finish', ('entry',), lambda _: {}),
                                    ('inspect_headers', (), lambda _: {}), ('inspect_headers', ('entry',), None)):
            with self.subTest(name=name), self.assertRaises(ValueError): ActionSpec(name, refs, handler)
        spec = ActionSpec('inspect_headers', ('entry',), lambda _: {})
        with self.assertRaises(ValueError): ActionRegistry([spec, spec])

    def test_phase_condition_is_shared_by_menu_and_direct_execution(self):
        ready, calls = [False], []
        registry = ActionRegistry([ActionSpec('analyze_passive_capture', ('entry',), lambda value: calls.append(value.action), lambda: ready[0])])
        self.assertEqual(registry.options(), {})
        with self.assertRaises(RuntimeError): registry.execute(Decision('analyze_passive_capture', 'entry', (), '合成'))
        self.assertEqual(calls, [])
        ready[0] = True
        self.assertIn('analyze_passive_capture', registry.options())
        registry.execute(Decision('analyze_passive_capture', 'entry', (), '合成'))
        self.assertEqual(calls, ['analyze_passive_capture'])

    def test_used_binding_is_removed_without_removing_other_objects(self):
        registry = ActionRegistry([ActionSpec('compare_business_object', ('object-001', 'object-002'), lambda _: {})])
        self.assertEqual(registry.options({('compare_business_object', 'object-001')}), {'compare_business_object': ['object-002']})

    def test_known_selection_error_corrects_once_without_fake_tool_steps(self):
        row, model, actions = self.run_script([decision('analyze_passive_capture'), decision('inspect_headers'), decision('finish', evidence=['o1'])])
        self.assertEqual((row['state'], row['steps'], actions.requests, row['modelCalls']), ('completed', 1, 1, 3))
        self.assertEqual(row['trace'][0]['reason'], 'action_not_available')
        self.assertEqual(row['trace'][0]['validation'], 'rejected')
        self.assertNotIn('analyze_passive_capture', model.contexts[0]['actionReferences'])
        self.assertNotIn('finish', model.contexts[0]['capabilities'])
        self.assertIn('finish', model.contexts[-1]['capabilities'])
        self.assertEqual(row['actionMenu']['catalogVersion'], CATALOG_VERSION)

    def test_selection_repair_and_format_repair_share_one_total_allowance(self):
        row, _, actions = self.run_script(['{}', decision('analyze_passive_capture'), decision('inspect_headers')])
        self.assertEqual((row['state'], row['modelCalls'], row['steps'], actions.requests), ('needs-human', 2, 0, 0))

    def test_unknown_action_is_fatal_without_another_model_call(self):
        row, _, actions = self.run_script([decision('shell'), decision('inspect_headers')])
        self.assertEqual((row['state'], row['modelCalls'], actions.requests), ('needs-human', 1, 0))

    def test_foreign_reference_is_fatal_without_another_model_call(self):
        row, _, actions = self.run_script([decision('inspect_headers', 'https://example.invalid'), decision('inspect_headers')])
        self.assertEqual((row['state'], row['modelCalls'], actions.requests), ('needs-human', 1, 0))

    def test_forbidden_parameter_is_fatal_and_not_saved_in_trace(self):
        payload = dict(json.loads(decision('inspect_headers')), command='DO_NOT_RETAIN_PRIVATE_COMMAND')
        row, _, actions = self.run_script([json.dumps(payload), decision('inspect_headers')])
        self.assertEqual((row['state'], row['modelCalls'], actions.requests), ('needs-human', 1, 0))
        self.assertNotIn('DO_NOT_RETAIN_PRIVATE_COMMAND', json.dumps(row))

    def test_fabricated_evidence_is_not_repaired_as_a_normal_selection_error(self):
        row, _, actions = self.run_script([decision('finish', evidence=['o999']), decision('inspect_headers')])
        self.assertEqual((row['state'], row['modelCalls'], actions.requests), ('needs-human', 1, 0))

    def test_missing_registry_fails_closed_instead_of_global_catalog_fallback(self):
        actions = SimpleNamespace(scope_hash='scope', config_hash='config', references=['entry'], requests=0)
        row, model, _ = self.run_script([decision('inspect_headers')], actions)
        self.assertEqual((row['state'], row['reason'], row['steps']), ('failed', 'action_catalog_invalid', 0))
        self.assertEqual(model.contexts, [])

    def test_old_catalog_checkpoint_cannot_silently_resume(self):
        actions = FakeActions()
        history = AgentHistory(self.root)
        row = history.create('business-api', 'candidate-review', 'local', Limits(), actions)
        history.update(row['id'], state='paused', catalogVersion='local-readonly-v4')
        runner = AgentRunner(self.root, history, ScriptedModel([]), actions, resource_check=lambda: {'allowed': True})
        with self.assertRaisesRegex(ValueError, 'resume_context_changed'):
            runner.run('business-api', 'candidate-review', threading.Event(), resume_id=row['id'])
        self.assertEqual(actions.requests, 0)

    def test_stop_after_invalid_selection_prevents_repair_and_target_calls(self):
        model = ScriptedModel([decision('analyze_passive_capture')])
        original = model.decide
        def stop(context):
            answer = original(context)
            (self.root / 'STOP').touch()
            return answer
        model.decide = stop
        actions = FakeActions()
        row = AgentRunner(self.root, AgentHistory(self.root), model, actions, resource_check=lambda: {'allowed': True}).run('business-api', 'candidate-review', threading.Event())
        self.assertEqual((row['state'], row['modelCalls'], actions.requests), ('cancelled', 1, 0))


if __name__ == '__main__':
    unittest.main()

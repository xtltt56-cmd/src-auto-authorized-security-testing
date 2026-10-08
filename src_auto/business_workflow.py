"""L4 bounded business recipes on an explicitly approved isolated loopback app.

The model selects finite object references, never URLs, credentials or payloads.
Uses the existing HTTP transport, permission guard, worker, lease and spend ledger.
"""
import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser

from .agent_contracts import Decision, Limits
from .agent_runner import AgentRunner, project_path
from .agent_resources import WindowsResources
from .business_preparation import BusinessPreparation, ROLES
from .controls import DiskGuard, StopController
from .config import load_mapping
from .dashboard_workspace import safe_text
from .local_application import LocalApplicationHTTP, LocalApplicationError, LocalReadOnlyPlan
from .local_application_workflow import LocalApplicationCoordinator, listener_identity
from .local_scope import aware_timestamp
from .scope import ScopeGuard, ScopePolicy
from .session_vault import SessionVault
from .store import Store

ERROR_CODES = {'business_request_invalid', 'business_context_changed', 'business_preparation_incomplete',
    'business_coverage_incomplete', 'business_object_baseline_invalid', 'controlled_fixture_required',
    'controlled_fixture_changed', 'approval_already_used', 'business_approval_expired', 'redirect_not_allowed',
    'manual_execution_confirmation_required', 'remote_ai_disabled_for_session', 'agent_disabled',
    'agent_operation_conflict', 'dashboard_closing', 'outside_test_window', 'application_identity_changed',
    'application_identity_unavailable', 'resource_limit', 'blocked_disk', 'cancelled', 'task_timeout',
    'request_timeout', 'request_failed', 'request_limit', 'session_expired', 'queue_unavailable'}


def context_snapshot(root, row):
    prep = BusinessPreparation(root)
    current = next((x for x in prep._rows() if x['id'] == row['id']), None)
    if current != row or not prep.preview({'id': row['id']})['readyForNextStage']:
        raise ValueError('business_context_changed')
    return prep._target(row['targetId'], row['targetRevision'])


class _Marker(HTMLParser):
    def __init__(self): super().__init__(); self.found = False
    def handle_starttag(self, tag, attrs):
        if tag == 'x-src-auto-marker': self.found = True


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate_json_key')
        result[key] = value
    return result


class BusinessHTTP(LocalApplicationHTTP):
    _deny_redirects = True
    def __init__(self, guard, plan, cancel, gate, before_request, stop):
        super().__init__(guard, plan, cancel, stop=stop, before_request=before_request)
        self.gate, self.session_headers = gate, {}

    def _check(self, url, method):
        return super()._check(url, method) or self.gate()

    def _headers(self, request):
        return dict(super()._headers(request), **self.session_headers)

    def _observe(self, data, result):
        output = {'objectMatched': False, 'jsonFingerprint': '', 'rowCount': -1, 'markerParsed': False}
        if result['body_truncated']: return output
        try:
            parsed = json.loads(data.decode('utf-8'), object_pairs_hook=_unique,
                                parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid_json_number')))
            if isinstance(parsed, dict):
                # Identity is deliberately narrow: exact top-level string id.
                output['objectMatched'] = type(parsed.get('id')) is str and parsed['id'] == getattr(self, 'object_id', None)
                output['jsonFingerprint'] = hashlib.sha256(json.dumps(parsed, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()
                if (set(parsed) == {'rows'} and isinstance(parsed['rows'], list) and len(parsed['rows']) <= 2
                        and all(type(x) is str and len(x) <= 40 for x in parsed['rows'])):
                    output['rowCount'] = len(parsed['rows'])
        except (ValueError, UnicodeError, RecursionError): pass
        try:
            parser = _Marker(); parser.feed(data.decode('utf-8')); output['markerParsed'] = parser.found
        except (ValueError, UnicodeError, RecursionError): pass
        return output


class BusinessActions:
    def __init__(self, root, approval, cancel):
        self.root, self.approval, self.cancel = root, approval, cancel
        self.scope, self.plan, self.row = (approval[k] for k in ('scope', 'plan', 'row'))
        self.scope_hash = self.scope.digest()
        self.config_hash = hashlib.sha256((self.row['revision'] + approval['identity'] + str(approval['controls'])).encode()).hexdigest()
        self.objects = {'object-{:03d}'.format(i+1): x for i, x in enumerate(self.row['cases'])}
        self.references = ['entry'] + list(self.objects)
        self.capabilities = ['compare_business_object', 'finish', 'request_human_review']
        if approval['controls']: self.capabilities.insert(1, 'validate_business_controls')
        self.permissions = {'objects': {ref: {'expected': case['expected'], 'owner': case['owner']} for ref, case in self.objects.items()},
                            'allObjectReferencesRequired': True, 'controlsRequired': approval['controls'], 'rawBodyAllowed': False,
                            'summary': '四角色、同一精确对象；固定合成输入对照；必须引用全部已执行观察才能完成'}
        self.resources = WindowsResources(load_mapping(root / 'config/policy.yaml'))
        self.completed, self.standard_run_id = set(), ''
        self.client = BusinessHTTP(ScopeGuard(self.scope), self.plan, cancel, self.permission_gate, self._before_request,
                                   lambda: StopController(root / 'STOP').requested())

    @property
    def requests(self): return self.client.request_count
    @requests.setter
    def requests(self, number): self.client.request_count = number

    def resource_check(self):
        self.last_resource_check = self.resources.check()
        return self.last_resource_check

    def permission_gate(self):
        if self.cancel.is_set() or StopController(self.root / 'STOP').requested(): return 'cancelled'
        if not self.scope.local_web.window_start <= datetime.now(timezone.utc) < self.scope.local_web.window_end: return 'outside_test_window'
        try:
            context_snapshot(self.root, self.row)
            if listener_identity(self.scope.local_web.origin) != self.approval['identity']: return 'application_identity_changed'
            if self.approval['controls']:
                from .l4_lab import registered_fixture
                if not registered_fixture(self.root, self.scope.local_web.origin, self.approval['identity']): return 'controlled_fixture_changed'
        except (ValueError, RuntimeError, OSError): return 'business_context_changed'
        return ''

    def _before_request(self):
        reason = self.permission_gate()
        if reason: return reason
        if not self.resource_check().get('allowed'): return 'resource_limit'
        try: DiskGuard(self.root).assert_allowed()
        except Exception: return 'blocked_disk'
        return ''

    def _fetch(self, path, role='anonymous', object_id=None):
        reason = self.permission_gate()
        if reason: raise LocalApplicationError(reason)
        request = next(x for x in self.plan.requests if x.path == path)
        self.client.object_id = object_id
        self.client.session_headers = {} if role == 'anonymous' else dict(SessionVault(self.root).load_for_target(
            self.row['sessions'][role], self.row['targetId'], self.scope.local_web.origin, role).headers)
        try: return self.client.fetch(request)
        finally: self.client.session_headers = {}; self.client.object_id = None

    def execute(self, value):
        if value.action not in self.capabilities: raise LocalApplicationError('capability_unavailable')
        if value.reference in self.completed: raise LocalApplicationError('duplicate_action')
        if value.action == 'compare_business_object' and value.reference in self.objects:
            case = self.objects[value.reference]
            snapshots = {role: self._fetch(case['path'], role, case['id']) for role in ROLES}
            owner = case['owner'] if case['owner'] != 'public' else next(x for x in ROLES if case['expected'][x])
            baseline = snapshots[owner]
            valid = 200 <= baseline['status_code'] < 300 and baseline['objectMatched'] and bool(baseline['jsonFingerprint'])
            equivalent = {role: bool(valid and 200 <= obs['status_code'] < 300 and obs['objectMatched']
                                     and obs['jsonFingerprint'] == baseline['jsonFingerprint']) for role, obs in snapshots.items()}
            unexpected = [role for role in ROLES if not case['expected'][role] and equivalent[role]]
            mismatches = [role for role in ROLES if case['expected'][role] and not equivalent[role]]
            uncertain = [role for role, obs in snapshots.items() if not equivalent[role] and obs['status_code'] not in (401, 403, 404)]
            result = dict(status='ok', summary='四角色对象对照；正文仅在内存比较，未保留或发送', path=case['path'],
                expected=case['expected'], statuses={r: x['status_code'] for r, x in snapshots.items()},
                fingerprints={r: x['jsonFingerprint'] for r, x in snapshots.items()}, baselineValid=valid,
                equivalent=equivalent, unexpectedRoles=unexpected, missingExpectedRoles=mismatches, inconclusiveRoles=uncertain,
                candidate=bool(unexpected), candidateCount=int(bool(unexpected)), confirmed=False,
                validated=bool(valid and not mismatches and not uncertain))
        elif value.action == 'validate_business_controls' and value.reference == 'entry' and self.approval['controls']:
            from .l4_lab import CONTROL_PATHS
            observations = {path: self._fetch(path) for path in CONTROL_PATHS}
            checks = {}
            for variant in ('vulnerable', 'protected'):
                sql = [observations['/l4/sqli/{}/{}'.format(variant, probe)] for probe in ('baseline', 'true', 'false')]
                checks[variant] = {'sqli': bool(all(x['status_code'] == 200 for x in sql) and sql[0]['rowCount'] == sql[1]['rowCount'] == 1
                    and sql[0]['jsonFingerprint'] == sql[1]['jsonFingerprint'] and sql[2]['rowCount'] == 0),
                    'counts': [x['rowCount'] for x in sql], 'htmlReflection': observations['/l4/xss/{}/marker'.format(variant)]['markerParsed']}
            valid = (all(x['status_code'] == 200 and not x['body_truncated'] for x in observations.values())
                     and checks['vulnerable']['sqli'] and not checks['protected']['sqli']
                     and checks['vulnerable']['htmlReflection'] and not checks['protected']['htmlReflection']
                     and checks['protected']['counts'] == [1, 0, 0])
            result = dict(status='ok', summary='固定合成 SQL 布尔差异与惰性 HTML 反射正负对照；脚本执行未验证',
                controlsValid=valid, checks=checks, candidate=valid, candidateCount=2 if valid else 0,
                candidateKinds=['boolean-sqli-differential', 'inert-html-reflection'] if valid else [],
                confirmed=False, validated=valid, scriptExecutionVerified=False)
        else: raise LocalApplicationError('capability_unavailable')
        self.completed.add(value.reference)
        return result

    def completion_ready(self, evidence):
        required = set(self.objects) | ({'entry'} if self.approval['controls'] else set())
        return required <= {x.get('reference') for x in evidence if x.get('validated') is True}

    def persist_candidates(self, key, value, observation):
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            kinds = observation.get('candidateKinds', ['object-authorization'])
            return [str(store.insert_finding({'run_id': self.standard_run_id, 'title': '隔离业务验证候选 · ' + kind,
                'url': self.scope.local_web.origin + observation.get('path', '/l4'), 'parameter': value.reference + ':' + kind,
                'severity': 'medium', 'status': 'candidate', 'evidence': json.dumps(observation, ensure_ascii=False),
                'triage': {'agent_id': key, 'confirmed': False, 'submission_ready': False, 'category': kind}}).row_id) for kind in kinds]
        finally: store.close()


class BusinessCoordinator(LocalApplicationCoordinator):
    def preview(self, value, remote):
        fields = {'id', 'revision', 'confirmIsolation', 'windowStart', 'windowEnd', 'mode', 'provider', 'allowCloud', 'controls'}
        if not isinstance(value, dict) or set(value) != fields or value['confirmIsolation'] is not True or type(value['controls']) is not bool:
            raise ValueError('business_request_invalid')
        self.cloud_gate(value['mode'], value['provider'], value['allowCloud'], remote)
        prep = BusinessPreparation(self.root)
        row = next((x for x in prep._rows() if x['id'] == value['id']), None)
        if row is None or row['revision'] != value['revision']: raise ValueError('business_context_changed')
        if not prep.preview({'id': row['id']})['readyForNextStage']: raise ValueError('business_preparation_incomplete')
        target = context_snapshot(self.root, row)
        if target['method'] != 'GET' or (value['mode'] == 'agent' and len(row['cases']) + int(value['controls']) > 7):
            raise ValueError('business_request_invalid')
        for case in row['cases']:
            if not case['expected'].get(case['owner'], any(case['expected'].values())):
                raise ValueError('business_object_baseline_invalid')
        now = datetime.now(timezone.utc)
        start, end = aware_timestamp(value['windowStart'], 'start'), aware_timestamp(value['windowEnd'], 'end')
        if not start <= now < end or (end - now).total_seconds() > 900: raise ValueError('outside_test_window')
        paths = list(dict.fromkeys(x['path'] for x in row['cases']))
        identity = listener_identity(target['origin'])
        if value['controls']:
            from .l4_lab import CONTROL_PATHS, registered_fixture
            if not registered_fixture(self.root, target['origin'], identity) or any(p not in target['paths'] for p in CONTROL_PATHS):
                raise ValueError('controlled_fixture_required')
            paths.extend(CONTROL_PATHS)
        requests = len(row['cases']) * 4 + (8 if value['controls'] else 0)
        scope = ScopePolicy.from_mapping(dict(schema_version=2, target_type='local_web', target_id=target['id'], origin=target['origin'],
            confirmed=True, allow_network_contact=True, automation_allowed=True, allowed_paths=paths, excluded_paths=target['excluded'],
            allowed_methods=['GET'], window_start=start.isoformat(), window_end=end.isoformat(), authorization_note='人工确认隔离测试账号及只读精确对象与固定用例',
            profile_id='readonly-baseline-v1', limits=dict(concurrency=1, request_limit=requests, task_timeout_seconds=600,
                request_timeout_seconds=5, response_limit_bytes=65536, output_limit_bytes=1048576)))
        plan = LocalReadOnlyPlan.from_mapping(dict(plan_version=1, scope_digest=scope.digest(), manual_execution_confirmed=True,
            requests=[dict(path=p, method='GET') for p in paths]), scope)
        key = uuid.uuid4().hex
        with self.service.control._lock:
            if self.service.control._closing: raise RuntimeError('dashboard_closing')
            self.approvals = {k: a for k, a in self.approvals.items() if not a['used'] and a['scope'].local_web.window_end > now}
            if len(self.approvals) >= 50: raise ValueError('business_request_invalid')
            self.approvals[key] = dict(scope=scope, plan=plan, row=row, identity=identity, mode=value['mode'], provider=value['provider'],
                                      allowCloud=value['allowCloud'], controls=value['controls'], used=False)
        return dict(approvalId=key, origin=target['origin'], applicationIdentity=identity, scopeDigest=scope.digest(),
                    preparationRevision=row['revision'], requestCount=requests, objectCount=len(row['cases']), controls=value['controls'],
                    expiresAt=end.isoformat(), networkContact=False, modelCalls=0, mode=value['mode'], provider=value['provider'])

    def start(self, value, remote):
        if not isinstance(value, dict) or set(value) != {'approvalId', 'confirmStart'} or value['confirmStart'] is not True:
            raise ValueError('manual_execution_confirmation_required')
        service = self.service
        with service.control._lock:
            approval = self.approvals.get(value['approvalId']) if isinstance(value['approvalId'], str) else None
            if approval is None: raise ValueError('business_approval_expired')
            if approval['used']: raise ValueError('approval_already_used')
            self.cloud_gate(approval['mode'], approval['provider'], approval['allowCloud'], remote)
            if service.control._closing: raise RuntimeError('dashboard_closing')
            if approval['mode'] == 'agent' and not service.enabled: raise RuntimeError('agent_disabled')
            if service.active or service.control.lifecycle()['activeWork']: raise RuntimeError('agent_operation_conflict')
            cancel = threading.Event()
            actions = BusinessActions(self.root, approval, cancel)
            denial = actions.permission_gate()
            if denial: raise ValueError(denial)
            cloud = self.cloud_budget_factory(self.root) if approval['provider'] == 'deepseek' else None
            model = service.model_factory(self.root, approval['provider'], remote, approval['allowCloud']) if approval['mode'] == 'agent' else None
            limits = Limits(max_steps=7 if model else len(actions.objects)+int(approval['controls']), max_requests=approval['scope'].local_web.limits.request_limit,
                            max_model_calls=12 if model else 0, max_tokens=20000 if model else 0, max_seconds=600)
            mode = 'business-assessment' if model else 'business-standard'
            row = service.history.create(approval['row']['targetId'], mode, approval['provider'], limits, actions)
            store = Store(self.root / 'data/src_auto.sqlite3')
            try:
                actions.standard_run_id = store.create_run(approval['row']['targetId'], actions.scope_hash, 'local')
                store.save_checkpoint(actions.standard_run_id, 'business_approval', dict(scope=approval['scope'].canonical(),
                    preparationId=approval['row']['id'], revision=approval['row']['revision'], applicationIdentity=approval['identity']))
                service.history.update(row['id'], standardRunId=actions.standard_run_id, targetType='business_local', origin=approval['scope'].local_web.origin)
            except Exception:
                service.history.update(row['id'], state='failed', reason='business_setup_failed')
                if actions.standard_run_id: store.set_run_status(actions.standard_run_id, 'failed')
                raise RuntimeError('business_setup_failed') from None
            finally: store.close()
            approval['used'], service.current_id, service.cancel = True, row['id'], cancel
            try: service.executor.submit(self._run, row['id'], approval, actions, model, limits, cloud, cancel)
            except Exception:
                service.current_id = None; service.history.update(row['id'], state='failed', reason='queue_unavailable')
                store = Store(self.root / 'data/src_auto.sqlite3')
                try: store.set_run_status(actions.standard_run_id, 'failed')
                finally: store.close()
                raise RuntimeError('queue_unavailable') from None
            return {'accepted': True, 'id': row['id']}

    def _run(self, key, approval, actions, model, limits, cloud, cancel):
        service, lease, started = self.service, None, time.monotonic()
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            lease = store.claim_local_application(actions.standard_run_id, actions.scope_hash, actions.row['targetId'], actions.scope.local_web.origin)
            if model:
                AgentRunner(self.root, service.history, model, actions, limits, approval['provider'], actions.resource_check, cloud).run(
                    actions.row['targetId'], 'business-assessment', cancel, run_id=key)
            else:
                service.history.acquire(key)
                observations, trace = [], []
                recipes = [('compare_business_object', ref) for ref in actions.objects]
                if approval['controls']: recipes.append(('validate_business_controls', 'entry'))
                for action, reference in recipes:
                    value = Decision(action, reference, (), '人工批准的固定业务对照配方')
                    entry = dict(index=len(trace)+1, decision=value.to_mapping(), result='executing'); trace.append(entry)
                    service.history.update(key, trace=trace, reason='tool_executing')
                    result = dict(actions.execute(value), id='o{}'.format(len(observations)+1), action=action, reference=reference)
                    if result.get('candidate'): result['findingIds'] = actions.persist_candidates(key, value, result)
                    observations.append(result); entry.update(result='ok', observationId=result['id'])
                    service.history.update(key, observations=observations, trace=trace, steps=len(observations), requests=actions.requests,
                        candidates=sum(x.get('candidateCount', 0) for x in observations), elapsedSeconds=round(time.monotonic()-started, 2))
                ready = actions.completion_ready(observations)
                service.history.update(key, state='completed' if ready else 'needs-human', reason='business_recipes_completed' if ready else 'business_object_baseline_invalid')
        except Exception as exc:
            code = getattr(exc, 'reason', str(exc))
            code = code if code in ERROR_CODES else 'business_execution_failed'
            service.history.update(key, state='cancelled' if code == 'cancelled' else 'needs-human', reason=code)
        finally:
            try:
                row = service.history.update(key, requests=actions.requests, resourceCheck=getattr(actions, 'last_resource_check', None), elapsedSeconds=round(time.monotonic()-started, 2))
                path = project_path(self.root, 'reports', 'agent', key + '.md'); path.parent.mkdir(parents=True, exist_ok=True)
                text = '# L4 隔离业务验证报告\n\n四角色同一对象、预期权限与真实请求对照。\n\n'
                text += '状态：{}；请求 {}；模型调用 {}；候选 {}；未自动确认或提交。\n\n'.format(row['state'], row['requests'], row['modelCalls'], row['candidates'])
                text += '消耗词元：{}{}；耗时 {} 秒；配置估算费用 {} 元（非账单）。\n\n'.format(row['tokens'], '（含估算）' if row['usageEstimated'] else '', row['elapsedSeconds'], row.get('estimatedCostCny', 0))
                text += '未覆盖：任意业务流程、写操作、并发竞态、盲注、存储型 XSS、跨站攻击；脚本执行未验证。HTML 反射只属于待复核候选。\n\n'
                text += '正文、凭据不保留，不发送云端；隔离仍由操作员负责，声明不是系统证明。\n\n```json\n' + json.dumps(row, ensure_ascii=False, indent=2) + '\n```\n'
                path.write_text(safe_text(text, 200000), encoding='utf-8')
                report_id = path.relative_to(self.root).as_posix()
                store.save_report(actions.standard_run_id, report_id); store.save_checkpoint(actions.standard_run_id, 'business_result', row)
                store.set_run_status(actions.standard_run_id, row['state']); service.history.update(key, reportId=report_id)
            except Exception:
                service.history.update(key, state='failed', reason='business_report_failed')
                store.set_run_status(actions.standard_run_id, 'failed')
            finally:
                if lease: store.release_local_application(actions.standard_run_id, lease)
                store.close()
                with service.control._lock: service.current_id = None

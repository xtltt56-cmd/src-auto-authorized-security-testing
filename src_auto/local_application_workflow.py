"""Manual local-Web workflow using the existing Agent loop and report store."""
import ctypes
import hashlib
import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .agent_contracts import Limits
from .agent_resources import WindowsResources
from .agent_runner import AgentRunner, process_identity, project_path
from .agent_cloud_budget import DeepSeekAgentBudget
from .config import load_mapping
from .controls import DiskGuard, StopController
from .dashboard_workspace import safe_text
from .local_application import LocalApplicationHTTP, LocalApplicationError, LocalReadOnlyPlan
from .scope import ScopeGuard, ScopePolicy
from .store import Store

LOCAL_ERRORS = {
    'remote_ai_disabled_for_session': '本次启动禁止云端 AI；保存密钥不会解除此限制',
    'application_identity_unavailable': '无法取得本机监听实例，请确认服务已启动且入口端口正确',
    'application_identity_changed': '应用监听实例已变化，请重新核对审批摘要',
    'local_approval_expired': '审批摘要已失效，请重新核对',
    'approval_already_used': '该审批已提交，不能重复启动；请查看历史任务',
    'agent_disabled': '请先启用本次受控 Agent',
    'agent_operation_conflict': '已有任务执行中，不能并行启动',
    'dashboard_closing': '控制台正在关闭，请重新启动',
    'manual_execution_confirmation_required': '需要再次确认按审批快照执行',
    'local_agent_route_limit': 'Agent 首版最多批准 6 条路由；更多路由可使用标准只读方式',
    'local_scope_required': '必须提供本机 Web 应用范围',
    'local_ui_single_method_required': '每次审批只选择一种只读方法',
    'local_application_setup_failed': '准备任务文件失败；任务已标记失败且未访问目标',
    'queue_unavailable': '任务队列不可用，请核对执行服务',
    'invalid_local_application_request': '本机任务请求格式无效',
    'path_excluded': '允许路由与排除路由冲突；排除规则优先',
    'outside_time_window': '当前不在批准时间窗内',
}


def listener_identity(origin):
    """Read Windows listener PID + creation time; never enumerate program files.

    Uses GetExtendedTcpTable / OWNER_PID_LISTENER, not shell-built commands.
    Identity is change detection, not proof that the application's data is safe.
    """
    if os.name != 'nt':
        raise ValueError('application_identity_unavailable')
    parsed = urlsplit(origin)
    if parsed.hostname not in ('127.0.0.1', '::1') or not parsed.port:
        raise ValueError('application_identity_unavailable')
    from ctypes import wintypes
    dword = wintypes.DWORD
    class Row4(ctypes.Structure):
        _fields_ = [(name, dword) for name in ('state', 'local', 'port', 'remote', 'remotePort', 'pid')]
    class Row6(ctypes.Structure):
        _fields_ = [('local', ctypes.c_ubyte * 16), ('scope', dword), ('port', dword),
                    ('remote', ctypes.c_ubyte * 16), ('remoteScope', dword), ('remotePort', dword),
                    ('state', dword), ('pid', dword)]
    ipv6 = parsed.hostname == '::1'
    row_type, family = (Row6, 23) if ipv6 else (Row4, 2)
    get_table = ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(dword), wintypes.BOOL, dword, ctypes.c_int, dword]
    get_table.restype = dword
    size = dword()
    if get_table(None, ctypes.byref(size), False, family, 3, 0) not in (0, 122) or not 4 <= size.value <= 4 * 1024 * 1024:
        raise ValueError('application_identity_unavailable')
    buffer = ctypes.create_string_buffer(size.value)
    if get_table(buffer, ctypes.byref(size), False, family, 3, 0) != 0:
        raise ValueError('application_identity_unavailable')
    count = dword.from_buffer_copy(buffer.raw[:4]).value
    if 4 + count * ctypes.sizeof(row_type) > size.value:
        raise ValueError('application_identity_unavailable')
    owners = set()
    for index in range(count):
        row = row_type.from_buffer_copy(buffer, 4 + index * ctypes.sizeof(row_type))
        if row.state != 2 or socket.ntohs(row.port & 0xffff) != parsed.port:
            continue
        address = (socket.inet_ntop(socket.AF_INET6, bytes(row.local)) if ipv6
                   else socket.inet_ntoa(int(row.local).to_bytes(4, 'little')))
        if address in (parsed.hostname, '::' if ipv6 else '0.0.0.0'):
            owners.add(int(row.pid))
    if len(owners) != 1:
        raise ValueError('application_identity_unavailable')
    pid = owners.pop()
    created = process_identity(pid)
    if created is False or created is None:
        raise ValueError('application_identity_unavailable')
    return hashlib.sha256('{}:{}:{}'.format(origin, pid, created).encode('utf-8')).hexdigest()


class LocalWebActions:
    """Only approved route references are executable. No model-provided URL."""
    def __init__(self, root, scope, plan, identity, cancel):
        self.root, self.scope, self.plan, self.identity = root, scope, plan, identity
        self.scope_hash = scope.digest()
        self.config_hash = hashlib.sha256((plan.digest() + identity + 'local-web-v1').encode()).hexdigest()
        self.routes = {'route-{:03d}'.format(i + 1): request for i, request in enumerate(plan.requests)}
        self.references = ['entry'] + list(self.routes)
        self.capabilities = ['inspect_local_route', 'finish', 'request_human_review']
        self.permissions = {'target_type': 'local_web', 'routeReferences': list(self.routes),
                            'requiredRouteCount': len(self.routes), 'rawBodyAllowed': False,
                            'note': '必须逐个检查全部批准 routeReferences；完成时引用全部观察。只读，不允许新增地址。'}
        self.resources = WindowsResources(load_mapping(root / 'config/policy.yaml'))
        self.client = LocalApplicationHTTP(ScopeGuard(scope), plan, cancel,
                                           stop=StopController(root / 'STOP').requested, before_request=self.before_request)
        self.completed_routes = set()
        self.standard_run_id = ''

    @property
    def requests(self):
        return self.client.request_count

    @requests.setter
    def requests(self, value):
        self.client.request_count = value

    def before_request(self):
        denial = self.permission_gate()
        if denial:
            return denial
        if not DiskGuard(self.root).check()['allowed']:
            return 'blocked_disk'
        if not self.resources.check().get('allowed'):
            return 'resource_limit'
        return ''

    def permission_gate(self):
        denial = self.client._check(self.scope.local_web.origin + self.plan.requests[0].path, self.plan.requests[0].method)
        if denial:
            return denial
        try:
            if listener_identity(self.scope.local_web.origin) != self.identity:
                return 'application_identity_changed'
        except (ValueError, OSError):
            return 'application_identity_unavailable'
        return ''

    def execute(self, value):
        if value.action != 'inspect_local_route' or value.reference not in self.routes or value.reference in self.completed_routes:
            raise RuntimeError('capability_unavailable')
        observation = dict(self.client.fetch(self.routes[value.reference]))
        self.completed_routes.add(value.reference)
        anomaly = observation['status_code'] >= 500
        return dict(observation, status='ok', summary='批准路由已真实检查；仅保存响应元数据',
                    candidate=anomaly, candidateCount=int(anomaly), confirmed=False,
                    category='functional-anomaly' if anomaly else 'readonly-observation')

    def completion_ready(self, evidence):
        checked = {x.get('reference') for x in evidence if x.get('action') == 'inspect_local_route'}
        return set(self.routes) <= checked

    def persist_candidates(self, agent_id, value, observation):
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            result = store.insert_finding({'run_id': self.standard_run_id,
                'title': '本机批准路由返回服务器错误（功能异常待复核）',
                'url': self.scope.local_web.origin + observation['path'], 'parameter': observation['method'],
                'severity': 'info', 'status': 'candidate',
                'evidence': '真实 HTTP {}；观察 {}。不代表可利用漏洞，需人工确认业务影响。'.format(observation['status_code'], observation['id']),
                'triage': {'confirmed': False, 'submission_ready': False, 'agent_id': agent_id,
                           'scope_digest': self.scope_hash, 'category': 'functional-anomaly'}})
            return [str(result.row_id)]
        finally:
            store.close()

    def link_report(self, agent_id, path):
        store = Store(self.root / 'data/src_auto.sqlite3')
        try:
            store.save_report(self.standard_run_id, path.relative_to(self.root).as_posix())
        finally:
            store.close()


def write_local_report(root, row, scope, plan, identity):
    """Safe Markdown text, no target body or model HTML is rendered/executed."""
    path = project_path(root, 'reports', 'local-app', row['id'] + '.md')
    path.parent.mkdir(parents=True, exist_ok=True)
    observations = row.get('observations', [])
    checked = {x.get('reference') for x in observations}
    remaining = [{'path': x.path, 'method': x.method} for i, x in enumerate(plan.requests)
                 if 'route-{:03d}'.format(i + 1) not in checked]
    advisories = [{'path': x.get('path'), 'missing': [k for k, present in x.get('header_presence', {}).items()
                                                  if not present and k != 'strict-transport-security']}
                  for x in observations if x.get('header_presence')]
    report = ['# 本机应用审查报告（人工复核草稿）', '',
              '本报告区分只读观察、配置建议和功能异常候选。缺响应头不等于漏洞；零候选不表示系统完全安全。', '',
              '任务 ID：{}；关联标准记录：{}'.format(row['id'], row.get('standardRunId', '')),
              '入口：{}；模式：{}；模型提供商：{}'.format(scope.local_web.origin, row['mode'], row['provider']),
              '状态：{}；原因：{}'.format(row['state'], row['reason']),
              '范围摘要：{}；计划摘要：{}；应用实例摘要：{}'.format(scope.digest(), plan.digest(), identity),
              '已完成批准配方：{}/{}；实际连接尝试（含跳转）：{}；模型调用：{}；Token：{}{}；耗时：{} 秒'.format(
                  len(checked), len(plan.requests), row['requests'], row['modelCalls'], row['tokens'],
                  '（估算）' if row.get('usageEstimated') else '', row['elapsedSeconds']), '',
              '## 实际观察与覆盖', '', '```json', json.dumps(observations, ensure_ascii=False, indent=2), '```', '',
              '## 配置建议（不计为已确认漏洞）', '', '```json', json.dumps(advisories, ensure_ascii=False, indent=2), '```', '',
              '## 未执行与未覆盖', '', '未完成配方：' + json.dumps(remaining, ensure_ascii=False),
              '未覆盖：整站爬虫、登录/会话、业务权限、IDOR、XSS、SQLi、源码审查、第三方扫描器。未访问首页链接或排除路由。', '',
              '## Agent 执行记录', '', '模型简述仅是建议，不能改变批准范围或确认漏洞。', '',
              '```json', json.dumps(row.get('trace', []), ensure_ascii=False, indent=2), '```', '',
              '模型费用保守估算 {} 元，预算预留 {} 元；最终以服务商账单为准。'.format(
                  row.get('estimatedCostCny', 0), row.get('reservedCostCny', 0)),
              '所有候选均待人工复核；不会自动提交补天。响应正文、Cookie 和响应头值未保存。']
    text = safe_text('\n'.join(report) + '\n', 1048576)
    path.write_text(text, encoding='utf-8')
    return path.relative_to(root).as_posix()


class LocalApplicationCoordinator:
    """Session approval snapshots + existing AgentService worker, not a daemon."""
    def __init__(self, service):
        self.service, self.root, self.approvals = service, service.root, {}
        self.cloud_budget_factory = DeepSeekAgentBudget.configured

    @staticmethod
    def cloud_gate(mode, provider, allow, remote):
        if mode not in ('standard', 'agent') or provider not in ('none', 'local', 'deepseek') or type(allow) is not bool:
            raise ValueError('invalid_local_application_request')
        if (mode == 'standard' and (provider != 'none' or allow)) or (mode == 'agent' and provider == 'none'):
            raise ValueError('invalid_local_application_request')
        if provider == 'deepseek' and not (remote is True and allow is True):
            raise ValueError('remote_ai_disabled_for_session')
        if provider != 'deepseek' and allow:
            raise ValueError('invalid_local_application_request')

    def preview(self, document, remote):
        if not isinstance(document, dict) or set(document) != {'scope', 'mode', 'provider', 'allowCloud'}:
            raise ValueError('invalid_local_application_request')
        mode, provider, allow = (document[k] for k in ('mode', 'provider', 'allowCloud'))
        self.cloud_gate(mode, provider, allow, remote)
        scope = ScopePolicy.from_mapping(document['scope'])
        if scope.local_web is None:
            raise ValueError('local_scope_required')
        if len(scope.local_web.allowed_methods) != 1:
            raise ValueError('local_ui_single_method_required')
        requests = [{'path': x, 'method': scope.local_web.allowed_methods[0]} for x in scope.local_web.allowed_paths]
        plan = LocalReadOnlyPlan.from_mapping({'plan_version': 1, 'scope_digest': scope.digest(),
                    'manual_execution_confirmed': True, 'requests': requests}, scope)
        for request in plan.requests:
            decision = ScopeGuard(scope).decide(scope.local_web.origin + request.path, method=request.method)
            if not decision.allowed:
                raise ValueError(decision.reason)
        if mode == 'agent' and len(plan.requests) > 6:
            raise ValueError('local_agent_route_limit')
        identity = listener_identity(scope.local_web.origin)
        key = uuid.uuid4().hex
        with self.service.control._lock:
            if self.service.control._closing:
                raise RuntimeError('dashboard_closing')
            self.approvals = {k: v for k, v in self.approvals.items() if not v['used'] and v['scope'].local_web.window_end > datetime.now(timezone.utc)}
            if len(self.approvals) >= 50:
                raise ValueError('local_approval_limit')
            self.approvals[key] = dict(scope=scope, plan=plan, identity=identity, mode=mode, provider=provider, allowCloud=allow, used=False)
        return {'approvalId': key, 'scopeDigest': scope.digest(), 'planDigest': plan.digest(),
                'origin': scope.local_web.origin, 'requests': requests, 'applicationIdentity': identity,
                'networkContact': False, 'modelCalls': 0, 'mode': mode, 'provider': provider,
                'limits': scope.local_web.canonical()['limits'], 'expiresAt': scope.local_web.window_end.isoformat(),
                'dataPolicy': '仅响应元数据与批准路径；不保存/发送原始正文、Cookie、账户及交易数据'}

    def start(self, document, remote):
        if not isinstance(document, dict) or set(document) != {'approvalId', 'confirmStart'} or document['confirmStart'] is not True:
            raise ValueError('manual_execution_confirmation_required')
        if not isinstance(document['approvalId'], str):
            raise ValueError('invalid_local_application_request')
        service = self.service
        with service.control._lock:
            approval = self.approvals.get(document['approvalId'])
            if not approval:
                raise ValueError('local_approval_expired')
            if approval['used']:
                raise ValueError('approval_already_used')
            mode, provider, allow = (approval[k] for k in ('mode', 'provider', 'allowCloud'))
            self.cloud_gate(mode, provider, allow, remote)
            if service.control._closing:
                raise RuntimeError('dashboard_closing')
            if mode == 'agent' and not service.enabled:
                raise RuntimeError('agent_disabled')
            if service.active or service.control.lifecycle()['activeWork']:
                raise RuntimeError('agent_operation_conflict')
            scope, plan = approval['scope'], approval['plan']
            for request in plan.requests:
                decision = ScopeGuard(scope).decide(scope.local_web.origin + request.path, method=request.method)
                if not decision.allowed:
                    raise ValueError(decision.reason)
            if listener_identity(scope.local_web.origin) != approval['identity']:
                raise ValueError('application_identity_changed')
            cloud_budget = self.cloud_budget_factory(self.root) if provider == 'deepseek' else None
            model = service.model_factory(self.root, provider, remote, allow) if mode == 'agent' else None
            limits = Limits(max_steps=8, max_requests=min(100, scope.local_web.limits.request_limit),
                            max_seconds=scope.local_web.limits.task_timeout_seconds)
            if mode == 'standard':
                # Standard recipes are not model decisions: report the finite
                # approved plan's limits, rather than unrelated Agent defaults.
                limits = Limits(max_steps=len(plan.requests), max_requests=scope.local_web.limits.request_limit,
                                max_model_calls=0, max_tokens=0,
                                max_seconds=scope.local_web.limits.task_timeout_seconds)
            cancel = threading.Event()
            actions = LocalWebActions(self.root, scope, plan, approval['identity'], cancel)
            row = service.history.create(scope.target_id, 'local-web-assessment' if mode == 'agent' else 'local-web-standard', provider, limits, actions)
            store = Store(self.root / 'data/src_auto.sqlite3')
            try:
                actions.standard_run_id = store.create_run(scope.target_id, scope.digest(), 'local')
                store.save_checkpoint(actions.standard_run_id, 'local_application_approval',
                                      {'scope': scope.canonical(), 'plan': plan.canonical(), 'applicationIdentity': approval['identity'], 'agentId': row['id']})
                target = project_path(self.root, 'config', 'targets', 'local-web-' + row['id'])
                target.mkdir(parents=True, exist_ok=False)
                (target / 'scope_confirmed.yaml').write_text(json.dumps(scope.canonical(), ensure_ascii=False, indent=2), encoding='utf-8')
                (target / 'plan.json').write_text(json.dumps(plan.canonical(), ensure_ascii=False, indent=2), encoding='utf-8')
                service.history.update(row['id'], standardRunId=actions.standard_run_id, targetType='local_web',
                                       origin=scope.local_web.origin, applicationIdentity=approval['identity'], planHash=plan.digest())
            except Exception:
                service.history.update(row['id'], state='failed', reason='local_application_setup_failed')
                if actions.standard_run_id:
                    store.set_run_status(actions.standard_run_id, 'failed')
                raise RuntimeError('local_application_setup_failed') from None
            finally:
                store.close()
            approval['used'] = True
            service.current_id, service.cancel = row['id'], cancel
            try:
                service.executor.submit(self._run, row['id'], approval, actions, model, limits, cloud_budget, cancel)
            except Exception:
                service.current_id = None
                service.history.update(row['id'], state='failed', reason='queue_unavailable')
                store = Store(self.root / 'data/src_auto.sqlite3')
                try: store.set_run_status(actions.standard_run_id, 'failed')
                finally: store.close()
                raise RuntimeError('queue_unavailable') from None
            return {'accepted': True, 'id': row['id']}

    def _run(self, key, approval, actions, model, limits, cloud_budget, cancel):
        service, lease = self.service, None
        store = Store(self.root / 'data/src_auto.sqlite3')
        started = time.monotonic()
        try:
            lease = store.claim_local_application(actions.standard_run_id, actions.scope_hash, actions.scope.target_id, actions.scope.local_web.origin)
            if model is not None:
                runner = AgentRunner(self.root, service.history, model, actions, limits, approval['provider'],
                                     resource_check=actions.resources.check, cloud_budget=cloud_budget)
                row = runner.run(actions.scope.target_id, 'local-web-assessment', cancel, run_id=key)
            else:
                row = service.history.acquire(key)
                observations, trace = [], []
                for index, reference in enumerate(actions.routes):
                    from .agent_contracts import Decision
                    value = Decision('inspect_local_route', reference, (), '人工批准的标准只读配方')
                    entry = {'index': index + 1, 'decision': value.to_mapping(), 'result': 'executing'}
                    trace.append(entry)
                    service.history.update(key, reason='tool_executing', trace=trace)
                    try:
                        observation = dict(actions.execute(value), id='o{}'.format(index + 1), action=value.action, reference=reference)
                    except Exception as exc:
                        entry.update(result='failed', reason=exc.reason if isinstance(exc, LocalApplicationError) else 'tool_failed')
                        service.history.update(key, trace=trace)
                        raise
                    observations.append(observation)
                    if observation.get('candidate'):
                        observation['findingIds'] = actions.persist_candidates(key, value, observation)
                    entry.update(result='ok', observationId=observation['id'])
                    service.history.update(key, observations=observations, trace=trace, steps=len(observations), requests=actions.requests,
                                           candidates=sum(bool(x.get('candidate')) for x in observations), elapsedSeconds=round(time.monotonic() - started, 2))
                row = service.history.update(key, state='completed', reason='readonly_recipes_completed')
        except Exception as exc:
            code = exc.reason if isinstance(exc, LocalApplicationError) else 'local_application_execution_failed'
            row = service.history.update(key, state='cancelled' if code == 'cancelled' else 'needs-human', reason=code)
        finally:
            try:
                row = service.history.update(key, requests=actions.requests, elapsedSeconds=round(time.monotonic() - started, 2))
                report_id = write_local_report(self.root, row, actions.scope, actions.plan, approval['identity'])
                row['reportId'] = report_id
                store.save_report(actions.standard_run_id, report_id)
                store.save_checkpoint(actions.standard_run_id, 'local_application_result', row)
                store.set_run_status(actions.standard_run_id, row['state'])
                service.history.update(key, reportId=report_id)
            except Exception:
                service.history.update(key, state='failed', reason='local_application_report_failed')
            finally:
                if lease:
                    store.release_local_application(actions.standard_run_id, lease)
                store.close()
                with service.control._lock:
                    service.current_id = None

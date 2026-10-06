"""Explicit real DeepSeek/local-HTTP acceptance; no private app or credential copy.

Use --execute-cloud for the comparison, or additionally --serve-browser for
foreground browser QA. Outputs are isolated under the project's validation dir.
"""
import argparse
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src_auto.agent_cloud_budget import DeepSeekAgentBudget
from src_auto.agent_provider import configured_model
from src_auto.agent_resources import WindowsResources
from src_auto.agent_service import AgentService
from src_auto.config import load_mapping
from src_auto.dashboard_server import create_server
from src_auto.dashboard_workspace import DashboardWorkspace


class SyntheticApplication:
    def __init__(self):
        self.received = []
        received = self.received
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append([self.command, self.path])
                body = b'{"token":"SYNTHETIC_PRIVATE_BODY","account":"SYNTHETIC_PRIVATE_ACCOUNT"}'
                self.send_response(500 if self.path == '/failure' else 200)
                self.send_header('Set-Cookie', 'token=SYNTHETIC_PRIVATE_COOKIE')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if self.command != 'HEAD': self.wfile.write(body)
            do_HEAD = do_GET
            def log_message(self, *args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.1), daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:{}'.format(self.server.server_port)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)


class SyntheticControl:
    lab_ids = ()
    def __init__(self, root):
        self._lock, self._closing, self.root = threading.RLock(), False, root
        self.agent = None
    def lifecycle(self):
        return {'activeWork': bool(self.agent and self.agent.active), 'closing': self._closing}
    def snapshot(self):
        return dict(source='loopback', tasks=[], labs=[], events=[], findings=[], reports=[],
                    dependency={'executionServiceReady': True, 'dockerReady': False, 'message': '本机应用验收服务：合成数据，不使用 Docker'})
    def prepare_shutdown(self):
        return not self.lifecycle()['activeWork']


class MeteredModel:
    def __init__(self, model, records):
        self.model, self.records, self.provider = model, records, model.provider
    def decide(self, context):
        rendered = json.dumps(context, ensure_ascii=False)
        # Fail before sending any private synthetic body/header marker.
        if 'SYNTHETIC_PRIVATE' in rendered: raise RuntimeError('synthetic_secret_in_context')
        result = self.model.decide(context)
        self.records.append({'inputTokens': result['input_tokens'], 'outputTokens': result['output_tokens'],
                             'usageEstimated': result['usage_estimated'], 'priorObservations': len(context['observations'])})
        return result


def document(origin, mode='standard'):
    now = datetime.now(timezone.utc)
    return {'scope': {'schema_version': 2, 'target_type': 'local_web', 'target_id': 'synthetic-local-application',
        'origin': origin, 'confirmed': True, 'allow_network_contact': True, 'automation_allowed': True,
        'allowed_paths': ['/', '/api/health', '/failure'], 'excluded_paths': ['/api/trade', '/api/reset', '/api/account'],
        'allowed_methods': ['GET'], 'window_start': (now - timedelta(minutes=1)).isoformat(),
        'window_end': (now + timedelta(minutes=15)).isoformat(), 'authorization_note': 'Explicit synthetic application acceptance only',
        'profile_id': 'readonly-baseline-v1', 'limits': {'concurrency': 1, 'request_limit': 10, 'task_timeout_seconds': 300,
            'request_timeout_seconds': 5, 'response_limit_bytes': 65536, 'output_limit_bytes': 65536}},
        'mode': mode, 'provider': 'deepseek' if mode == 'agent' else 'none', 'allowCloud': mode == 'agent'}


def run(service, value, remote=True):
    preview = service.local_app.preview(value, remote)
    result = service.local_app.start({'approvalId': preview['approvalId'], 'confirmStart': True}, remote)
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        row = service.history.get(result['id'])
        if row.get('reportId') and service.current_id != result['id']: return row
        time.sleep(.2)
    service.cancel_run(result['id'])
    raise RuntimeError('acceptance_task_timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-cloud', action='store_true')
    parser.add_argument('--serve-browser', action='store_true')
    args = parser.parse_args()
    if not args.execute_cloud:
        print('No network/model test started. Explicit --execute-cloud is required.')
        return 2
    output = ROOT / 'validation/local-application-l2' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    (output / 'config').mkdir(parents=True, exist_ok=False)
    for name in ('models.yaml', 'policy.yaml'):
        shutil.copyfile(str(ROOT / 'config' / name), str(output / 'config' / name))
    os.environ['SRC_AUTO_REMOTE_AI_CONSENT'] = 'yes'
    os.environ['SRC_AUTO_DEEPSEEK_CONSENT'] = 'yes'
    records, factory_calls = [], []
    def factory(root, provider, remote, allow):
        factory_calls.append(provider)
        # Saved DPAPI key stays in its original protected file; never copy it.
        return MeteredModel(configured_model(ROOT, provider, remote, allow), records)
    app, control = SyntheticApplication(), SyntheticControl(output)
    service = AgentService(output, control, model_factory=factory)
    control.agent = service
    # Charge validation reservations against the real shared project ledger.
    service.local_app.cloud_budget_factory = lambda root: DeepSeekAgentBudget.configured(ROOT)
    server = None
    try:
        blocked = False
        try: service.local_app.preview(document(app.origin, 'agent'), False)
        except ValueError as exc: blocked = str(exc) == 'remote_ai_disabled_for_session'
        gate_calls = len(factory_calls)
        standard = run(service, document(app.origin))
        standard_received = list(app.received)
        service.set_enabled(True)
        agent = run(service, document(app.origin, 'agent'))
        agent_received = app.received[len(standard_received):]
        report_text = '\n'.join(p.read_text(encoding='utf-8') for p in (output / 'reports').rglob('*.md'))
        database_secret = any(b'SYNTHETIC_PRIVATE' in p.read_bytes() for p in (output / 'data').glob('*') if p.is_file())
        workspace = DashboardWorkspace(output)
        linked = all(workspace.read_report(row['reportId'])['content'] for row in (standard, agent))
        expected = [['GET', '/'], ['GET', '/api/health'], ['GET', '/failure']]
        checks = {'standard_actual_coverage': standard['state'] == 'completed' and standard_received == expected,
                  'cloud_agent_actual_coverage': agent['state'] == 'completed' and sorted(agent_received) == sorted(expected),
                  'real_model_feedback': len(records) >= 4 and [r['priorObservations'] for r in records] == list(range(len(records))),
                  'zero_cloud_calls_when_disabled': blocked and gate_calls == 0,
                  'one_functional_candidate_per_run': standard['candidates'] == agent['candidates'] == 1,
                  'sensitive_routes_not_contacted': all(x[1] not in ('/api/trade', '/api/reset', '/api/account') for x in app.received),
                  'secret_not_retained': 'SYNTHETIC_PRIVATE' not in report_text and not database_secret,
                  'reports_linked_and_readable': bool(linked), 'actual_usage_reported': bool(records) and all(not r['usageEstimated'] for r in records),
                  'no_extra_target_requests': len(app.received) == 6}
        resource = WindowsResources(load_mapping(output / 'config/policy.yaml')).check()
        summary = {'success': all(checks.values()), 'checks': checks, 'resourcesMocked': False, 'resourceCheck': resource,
                   'apiModel': load_mapping(ROOT / 'config/models.yaml')['remote_providers']['deepseek']['model'],
                   'standard': standard, 'agent': agent, 'realCloudCalls': records,
                   'standardReceived': standard_received, 'agentReceived': agent_received,
                   'realQuantApplicationContact': False, 'privateCodeSent': False, 'credentialCopied': False,
                   'reportPath': str(output / 'summary.json')}
        (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'success': summary['success'], 'checks': checks, 'reportPath': summary['reportPath'],
                          'syntheticOrigin': app.origin, 'standardSeconds': standard['elapsedSeconds'], 'agentSeconds': agent['elapsedSeconds'],
                          'modelCalls': agent['modelCalls'], 'tokens': agent['tokens'], 'estimatedCostCny': agent.get('estimatedCostCny')}, ensure_ascii=False), flush=True)
        if args.serve_browser:
            server = create_server(control, port=4174, project_root=output, remote_ai_enabled=True)
            print('Foreground synthetic Dashboard API ready on 127.0.0.1:4174', flush=True)
            server.serve_forever(poll_interval=.2)
        return 0 if summary['success'] else 1
    finally:
        service.close()
        deadline = time.monotonic() + 65
        while service.current_id and time.monotonic() < deadline: time.sleep(.2)
        if server: server.server_close()
        app.close()


if __name__ == '__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt: pass

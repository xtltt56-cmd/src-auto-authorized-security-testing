"""Bounded platform collection + pinned ZAP offline import. No live scanner argv.

The scanner has a separate network namespace with ONLY its own loopback, no
published ports, no host alias/socket, and cannot replay the recorded requests.
Only reviewed header presence is retained: body-dependent rules are disabled.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .local_application import LocalApplicationError
from .local_scope import PASSIVE_PROFILE, safe_local_path
from .scope import ScopeGuard
from .agent_runner import project_path

RULES = {'10020': '缺少防点击劫持响应头', '10021': '缺少内容类型嗅探防护响应头',
         '10038': '缺少内容安全策略响应头'}
HEADER_NAMES = {'content-security-policy', 'x-content-type-options', 'x-frame-options',
                'referrer-policy', 'permissions-policy', 'strict-transport-security'}


def scanner_config_hash(root, source=False):
    names = ['config/integrations/source_scanners.json', 'config/integrations/source_wheels.json',
             'config/integrations/source_rules.json', 'tools/source_audit_container.py'] if source else ['config/integrations/passive_scanners.json']
    values = []
    for name in names:
        path = Path(root) / name
        values.append((name, hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'missing'))
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.count, self.limited = [], 0, False

    def handle_starttag(self, tag, attrs):
        # No JS/resources/forms: these can have side effects or contain secrets.
        if tag != 'a':
            return
        for name, value in attrs:
            if name == 'href' and value:
                self.count += 1
                if self.count <= 128:
                    self.links.append(value[:2048])
                else:
                    self.limited = True


class PassiveCapture:
    def __init__(self, scope):
        self.scope, self.guard = scope, ScopeGuard(scope)
        self.entries, self.discoveries = [], []
        self.limit = scope.local_web.limits.output_limit_bytes
        self.truncated = 0

    def record(self, url, method, status, headers, body, truncated):
        denial = self.guard.decide(url, method=method)
        if not denial.allowed:
            raise LocalApplicationError(denial.reason)
        content_type, filtered = '', []
        for name, value in headers:
            name = name.lower()
            if name == 'content-type':
                mime = value.split(';', 1)[0].strip().lower()
                if mime in ('text/html', 'application/json', 'text/plain', 'application/xml', 'text/xml'):
                    content_type = mime
                # Other values are deliberately NOT persisted as tool evidence.
                filtered.append({'name': 'Content-Type', 'value': content_type or '[value-not-retained]'})
            elif name in HEADER_NAMES:
                filtered.append({'name': name, 'value': '[value-not-retained]'})
        discovery = {'approved_paths': [], 'blocked_counts': {}, 'link_limit_reached': False}
        if content_type == 'text/html' and method == 'GET':
            parser = _Links()
            parser.feed(body.decode('utf-8', errors='replace'))
            approved = set()
            for link in parser.links:
                reason = ''
                try:
                    # urljoin normalizes ../; reject it BEFORE resolution.
                    parsed = urlsplit(link)
                    if any(x in link for x in ('?', '#', '%', '\\')) or any(x in ('.', '..') for x in parsed.path.split('/')):
                        reason = 'ambiguous_or_sensitive_link'
                    else:
                        destination = urljoin(url, link)
                        result = self.guard.decide(destination, method=method)
                        reason = '' if result.allowed else result.reason
                        if not reason:
                            approved.add(safe_local_path(urlsplit(destination).path or '/'))
                except (ValueError, UnicodeError):
                    reason = 'invalid_link'
                if reason:
                    # Never store rejected URLs: a query/host/path can be private.
                    counts = discovery['blocked_counts']
                    counts[reason] = counts.get(reason, 0) + 1
            discovery.update(approved_paths=sorted(approved), link_limit_reached=parser.limited)
        entry = {'startedDateTime': datetime.now(timezone.utc).isoformat(), 'time': 0,
                 'request': {'method': method, 'url': url, 'httpVersion': 'HTTP/1.1',
                             'headers': [], 'queryString': [], 'cookies': [], 'headersSize': -1, 'bodySize': 0},
                 'response': {'status': status, 'statusText': '', 'httpVersion': 'HTTP/1.1',
                              'headers': filtered, 'cookies': [], 'redirectURL': '', 'headersSize': -1,
                              'bodySize': 0, 'content': {'size': 0, 'mimeType': content_type, 'text': ''}},
                 'cache': {}, 'timings': {'send': 0, 'wait': 0, 'receive': 0}}
        projected = {'log': {'version': '1.2', 'creator': {'name': 'SRC-Auto header-only', 'version': '1'},
                             'entries': self.entries + [entry]}}
        if len(json.dumps(projected, ensure_ascii=False).encode('utf-8')) > self.limit:
            raise LocalApplicationError('output_limit')
        self.entries.append(entry)
        self.discoveries.append(discovery)
        self.truncated += int(truncated)
        return {'discovery': discovery, 'passive_capture': 'sanitized-header-presence-only'}

    def har(self):
        return {'log': {'version': '1.2', 'creator': {'name': 'SRC-Auto header-only', 'version': '1'}, 'entries': self.entries}}

    def coverage(self):
        return {'messages': len(self.entries), 'truncated_responses': self.truncated,
                'body_rules_enabled': False, 'raw_body_retained': False, 'raw_header_values_retained': False,
                'discovered_approved_paths': sorted({x for row in self.discoveries for x in row['approved_paths']}),
                'blocked_link_count': sum(sum(row['blocked_counts'].values()) for row in self.discoveries),
                'link_limit_reached': any(row['link_limit_reached'] for row in self.discoveries)}


def offline_plan(scope):
    return {'env': {'contexts': [{'name': 'approved', 'urls': [scope.local_web.origin],
                                  'includePaths': [re.escape(scope.local_web.origin + path) + '$'
                                                   for path in scope.local_web.allowed_paths]}],
                    'parameters': {'failOnError': True, 'failOnWarning': True, 'progressToStdout': False}},
            'jobs': [{'type': 'passiveScan-config', 'parameters': {'disableAllRules': True,
                       'maxAlertsPerRule': 20, 'scanOnlyInScope': True, 'enableTags': False},
                      'rules': [{'id': int(rule), 'threshold': 'Medium'} for rule in RULES]},
                     # Pinned exim 0.21 imports messages only, without replay.
                     {'type': 'import', 'parameters': {'type': 'har', 'fileName': '/input/input.har'}},
                     {'type': 'passiveScan-wait', 'parameters': {'maxDuration': 1}},
                     {'type': 'report', 'parameters': {'template': 'traditional-json', 'reportDir': '/out',
                          'reportFile': 'report.json', 'displayReport': False}}]}


def normalize_alerts(document, scope, observed):
    if not isinstance(document, dict) or not isinstance(document.get('site'), list):
        raise LocalApplicationError('tool_report_invalid')
    guard, result, seen = ScopeGuard(scope), [], set()
    for site in document['site']:
        for alert in site.get('alerts', []):
            rule = str(alert.get('pluginid', ''))
            if rule not in RULES:
                continue
            for instance in alert.get('instances', []):
                url, method = instance.get('uri'), instance.get('method')
                if not isinstance(url, str) or method not in ('GET', 'HEAD'):
                    continue
                if not guard.decide(url, method=method).allowed:
                    continue
                path = urlsplit(url).path or '/'
                key = rule, path, method
                if (path, method) not in observed or key in seen:
                    continue
                required = {'10020': 'x-frame-options', '10021': 'x-content-type-options', '10038': 'content-security-policy'}[rule]
                if isinstance(observed, dict) and required in observed[(path, method)]:
                    # Header values were redacted; never mislabel the resulting
                    # placeholder as a missing header or assess its correctness.
                    continue
                seen.add(key)
                result.append({'rule_id': rule, 'title': RULES[rule], 'path': path, 'method': method,
                               'severity': 'info', 'category': 'configuration-advisory',
                               'scanner': 'zap-offline', 'confirmed': False, 'submission_ready': False})
                if len(result) > 80:
                    raise LocalApplicationError('tool_alert_limit')
    return result


class ManagedProcess:
    """Drain a bounded pipe, poll STOP/timeout, reap only our direct child."""
    def __init__(self, cancel, gate):
        self.cancel, self.gate, self.last_process = cancel, gate, None

    def run(self, args, timeout, output_limit=65536, check=True, accepted_codes=(0,)):
        if check:
            reason = 'cancelled' if self.cancel.is_set() else self.gate()
            if reason:
                raise LocalApplicationError(reason)
        env = dict(os.environ)
        for key in list(env):
            if key.upper().endswith('_PROXY') or key.upper().startswith('DOCKER_') or key.upper() in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS'):
                del env[key]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.last_process = process
        output, excessive = bytearray(), threading.Event()
        def drain():
            while True:
                part = process.stdout.read(4096)
                if not part:
                    break
                if len(output) + len(part) > output_limit:
                    excessive.set()
                elif not excessive.is_set():
                    output.extend(part)
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline, reason = time.monotonic() + max(0.01, timeout), ''
        try:
            while process.poll() is None:
                if excessive.is_set(): reason = 'tool_output_limit'
                elif time.monotonic() >= deadline: reason = 'tool_timeout'
                elif check: reason = 'cancelled' if self.cancel.is_set() else self.gate()
                if reason:
                    raise LocalApplicationError(reason)
                time.sleep(0.05)
            reader.join(timeout=2)
            if excessive.is_set():
                raise LocalApplicationError('tool_output_limit')
            self.last_output = bytes(output)
            if process.returncode not in accepted_codes:
                raise LocalApplicationError('tool_exit_failed')
            return bytes(output)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)
            reader.join(timeout=2)
            process.stdout.close()


class ZapOfflineScanner:
    registry_file = 'passive_scanners.json'
    image_pattern = r'ghcr\.io/zaproxy/zaproxy@sha256:[a-f0-9]{64}'
    def __init__(self, root, cancel, gate):
        self.root = Path(root).resolve()
        self.cancel, self.gate = cancel, gate
        self.process = ManagedProcess(cancel, gate)
        self.docker, self.image, self.image_id = '', '', ''

    def _docker_args(self, *args):
        endpoint = ['--host', 'npipe:////./pipe/dockerDesktopLinuxEngine'] if os.name == 'nt' else []
        return [self.docker] + endpoint + list(args)

    def prepare(self):
        try:
            config = json.loads((self.root / 'config/integrations' / self.registry_file).read_text(encoding='utf-8'))
            if set(config) != {'schema_version', 'image', 'image_id', 'docker_sha256'} or config['schema_version'] != 1:
                raise ValueError('invalid_registry')
            self.image, self.image_id = config['image'], config['image_id']
            if not re.fullmatch(self.image_pattern, self.image):
                raise ValueError('untrusted_image')
            binary = self.root / 'vendor/bin/docker.exe'
            if not binary.is_file() or binary.is_symlink() or binary.resolve().parent != (self.root / 'vendor/bin').resolve():
                raise ValueError('untrusted_binary')
            if hashlib.sha256(binary.read_bytes()).hexdigest() != config['docker_sha256']:
                raise ValueError('changed_binary')
            self.docker = str(binary.resolve())
            # Inspect only: no pulling, package/plugin updating or external scan.
            value = json.loads(self.process.run(self._docker_args('image', 'inspect', self.image), 8, 65536))
            if len(value) != 1 or value[0]['Id'] != self.image_id or self.image not in value[0]['RepoDigests']:
                raise ValueError('image_changed')
        except LocalApplicationError as exc:
            if exc.reason in ('cancelled', 'task_timeout', 'resource_limit', 'blocked_disk',
                              'outside_test_window', 'application_identity_changed', 'scanner_configuration_changed', 'source_configuration_changed'):
                raise
            raise LocalApplicationError('passive_scanner_unavailable') from None
        except (OSError, ValueError, KeyError, TypeError):
            raise LocalApplicationError('passive_scanner_unavailable') from None

    def command(self, work, name):
        return self._docker_args('create', '--name', name, '--label', 'src-auto.passive.owner=' + name,
            '--pull', 'never', '--network', 'none', '--hostname', 'localhost', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--cpus', '1', '--memory', '1536m', '--memory-swap', '1536m',
            '--pids-limit', '128', '--log-driver', 'none', '--user', '1000:1000', '--no-healthcheck',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=32m', '--tmpfs', '/home/zap/.ZAP:rw,nosuid,size=384m,uid=1000,gid=1000',
            '--tmpfs', '/out:rw,nosuid,noexec,size=4m,uid=1000,gid=1000',
            '--mount', 'type=bind,source={},target=/input,readonly'.format(work.resolve()),
            '--env', 'JAVA_TOOL_OPTIONS=-Xmx384m -Djava.io.tmpdir=/tmp',
            '--entrypoint', '/bin/sh', self.image, '-c',
            '/zap/zap.sh -Xmx384m -cmd -silent -dir /home/zap/.ZAP -autorun /input/plan.yaml >/out/driver.log 2>&1; '
            'rc=$?; if [ "$rc" -ne 0 ]; then cat /out/driver.log; exit "$rc"; fi; cat /out/report.json')

    def run(self, scope, capture, timeout):
        self.prepare()
        name = 'src-auto-passive-' + uuid.uuid4().hex
        work = project_path(self.root, 'runs', 'passive', name)
        plan = offline_plan(scope)
        content = json.dumps(capture.har(), ensure_ascii=False).encode('utf-8')
        if len(content) > capture.limit:
            raise LocalApplicationError('output_limit')
        work.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        def remaining():
            value = timeout - (time.monotonic() - started)
            if value <= 0: raise LocalApplicationError('task_timeout')
            return value
        try:
            (work / 'input.har').write_bytes(content)
            (work / 'plan.yaml').write_text(json.dumps(plan), encoding='utf-8')
            self.process.run(self.command(work, name), min(8, remaining()), 4096)
            inspected = json.loads(self.process.run(self._docker_args('inspect', name), min(8, remaining()), 65536))[0]
            host = inspected['HostConfig']
            if (host['NetworkMode'] != 'none' or host.get('PortBindings') or not host['ReadonlyRootfs']
                    or host.get('Privileged') or host.get('ExtraHosts') or inspected['Image'] != self.image_id
                    or inspected['Config']['Labels'].get('src-auto.passive.owner') != name
                    or len(inspected['Mounts']) != 1 or inspected['Mounts'][0]['RW']
                    or inspected['Mounts'][0]['Destination'] != '/input'):
                raise LocalApplicationError('tool_isolation_invalid')
            raw_report = self.process.run(self._docker_args('start', '-a', name), remaining(), scope.local_web.limits.output_limit_bytes)
            status = json.loads(self.process.run(self._docker_args('inspect', name), min(8, remaining()), 65536))[0]['State']
            if status['ExitCode'] != 0 or status.get('OOMKilled'):
                raise LocalApplicationError('tool_exit_failed')
            document = json.loads(raw_report)
            observed = {(urlsplit(x['request']['url']).path or '/', x['request']['method']):
                        {header['name'].lower() for header in x['response']['headers']} for x in capture.entries}
            findings = normalize_alerts(document, scope, observed)
            return {'status': 'completed', 'scanner': 'zap-offline', 'image': self.image, 'image_id': self.image_id,
                    'plan_hash': hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
                    'network_mode': 'none', 'scanner_target_requests': 0, 'findings': findings,
                    'coverage': capture.coverage(), 'elapsed_seconds': round(time.monotonic() - started, 2)}
        except (ValueError, KeyError, TypeError):
            raise LocalApplicationError('tool_report_invalid') from None
        finally:
            # This unique named container belongs to this task. No target process,
            # engine, existing lab or other container is stopped/removed here.
            cleanup_error = None
            try: self.process.run(self._docker_args('rm', '-f', name), 8, 4096, check=False)
            except (OSError, LocalApplicationError):
                try: self.process.run(self._docker_args('inspect', name), 8, 65536, check=False)
                except (OSError, LocalApplicationError):
                    if not any(x in getattr(self.process, 'last_output', b'') for x in (b'No such object', b'No such container')):
                        cleanup_error = 'tool_cleanup_failed'
                else: cleanup_error = 'tool_cleanup_failed'
            try:
                for filename in ('input.har', 'plan.yaml'):
                    (work / filename).unlink(missing_ok=True)
                work.rmdir()
            finally:
                if cleanup_error: raise LocalApplicationError(cleanup_error)

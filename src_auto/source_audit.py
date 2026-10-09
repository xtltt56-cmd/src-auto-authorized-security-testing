"""Separate directory authorization and offline, read-only source audit lane."""
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from .agent_contracts import Limits
from .agent_runner import project_path
from .controls import DiskGuard, StopController
from .agent_resources import WindowsResources
from .agent_cloud_budget import DeepSeekAgentBudget
from .remote_ai import RemoteReviewRequest, RemoteProviderError
from .config import load_mapping
from .dashboard_workspace import safe_text
from .guarded_passive import ZapOfflineScanner, scanner_config_hash
from .local_application import LocalApplicationError
from .store import Store

EXTENSIONS = {'python': {'.py'}, 'javascript': {'.js', '.jsx', '.ts', '.tsx'}}
EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', 'vendor', 'logs', 'reports',
            'runs', 'evidence', '__pycache__', 'dist', 'build', '.next', '.cache', 'coverage'}
TITLES = {'B102': '动态执行代码', 'B105': '疑似硬编码密码', 'B106': '疑似硬编码密码参数', 'B107': '疑似硬编码密码默认值',
          'B201': 'Web 调试模式', 'B301': '不安全的反序列化', 'B307': '动态 eval 执行', 'B324': '弱哈希算法',
          'B501': '关闭 TLS 证书校验', 'B506': '不安全的 YAML 加载', 'B602': '使用 shell 执行子进程',
          'B608': '拼接 SQL 语句', 'B701': '模板自动转义被关闭', 'B703': '绕过 HTML 转义',
          'src-auto.js-dynamic-eval': '动态 eval 执行', 'src-auto.js-function-constructor': '动态构造函数',
          'src-auto.js-shell-exec': '调用 shell 执行命令', 'src-auto.js-html-sink': '直接写入 HTML'}


def _reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 1024)


def _read(path, root):
    """Check actual opened handle before reading; do not follow junction swaps."""
    for parent in [path] + list(path.parents):
        if _reparse(parent): raise ValueError('source_link_not_allowed')
        if parent == root: break
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(str(path), flags)
    try:
        if os.name == 'nt':
            import msvcrt
            get_path = ctypes.WinDLL('kernel32').GetFinalPathNameByHandleW
            get_path.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
            get_path.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            size = get_path(msvcrt.get_osfhandle(descriptor), buffer, len(buffer), 0)
            actual = buffer.value[4:] if buffer.value.startswith('\\\\?\\') else buffer.value
            if not size or size >= len(buffer) or os.path.normcase(actual) != os.path.normcase(str(path)):
                raise ValueError('source_link_not_allowed')
        elif Path('/proc/self/fd').is_dir() and os.readlink('/proc/self/fd/' + str(descriptor)) != str(path):
            raise ValueError('source_link_not_allowed')
        if not stat.S_ISREG(os.fstat(descriptor).st_mode): raise ValueError('source_file_invalid')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            value = stream.read(1048577)
        if len(value) > 1048576: raise ValueError('source_file_limit')
        return value
    finally:
        if descriptor is not None: os.close(descriptor)


def source_manifest(directory, languages, authorized, max_bytes=20 * 1048576, gate=lambda: ''):
    if authorized is not True: raise ValueError('source_authorization_required')
    if not isinstance(languages, list) or not languages or set(languages) - set(EXTENSIONS): raise ValueError('source_languages_invalid')
    path = Path(directory)
    if not path.is_absolute() or str(path).startswith('\\\\') or len(path.parts) < 2 or not path.is_dir(): raise ValueError('source_directory_invalid')
    if path == Path.home() or path in [Path.home() / x for x in ('Desktop', 'Downloads', 'Documents')]: raise ValueError('source_directory_too_broad')
    for parent in [path] + list(path.parents):
        if _reparse(parent): raise ValueError('source_link_not_allowed')
    path = path.resolve()
    suffixes = set().union(*(EXTENSIONS[x] for x in languages))
    files, counts, exclusions, total, visited = [], {}, [], 0, 0
    def skip(reason, relative=''):
        counts[reason] = counts.get(reason, 0) + 1
        if relative and len(exclusions) < 500:
            exclusions.append(dict(path=safe_text(relative, 4096), reason=reason))
    for base, directories, names in os.walk(str(path), followlinks=False):
        reason = gate()
        if reason: raise LocalApplicationError(reason)
        visited += len(directories) + len(names)
        if visited > 10000: raise ValueError('source_enumeration_limit')
        kept = []
        for name in sorted(directories):
            item = Path(base) / name
            relative = item.relative_to(path).as_posix()
            if name.lower() in EXCLUDED or name.startswith('.') or _reparse(item): skip('excluded_directory', relative)
            # Root-level runtime storage stays excluded; nested business modules
            # and Python packages called data/runtime are not storage by name alone.
            elif Path(base) == path and name.lower() in {'data', 'runtime'} and not (item / '__init__.py').is_file():
                skip('runtime_directory', relative)
            else: kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            item = Path(base) / name
            relative = item.relative_to(path).as_posix()
            if item.suffix.lower() not in suffixes or re.search(r'(?i)(secret|credential|wallet|private[_-]?key|\.env)', relative):
                skip('excluded_file', relative); continue
            if name.lower().endswith('.min.js'):
                skip('bundled_javascript', relative); continue
            if _reparse(item) or safe_text(relative, 4096) != relative or any(ord(x) < 32 for x in relative):
                skip('unsafe_file', relative); continue
            reason = gate()
            if reason: raise LocalApplicationError(reason)
            try: content = _read(item, path); content.decode('utf-8-sig')
            except UnicodeDecodeError: skip('unsupported_encoding', relative); continue
            total += len(content)
            if len(files) >= 2000 or total > max_bytes: raise ValueError('source_total_limit')
            files.append(dict(path=relative, size=len(content), sha256=hashlib.sha256(content).hexdigest(), lines=content.count(b'\n') + 1))
    if not files: raise ValueError('source_no_supported_files')
    payload = dict(directory=str(path), languages=sorted(set(languages)), files=files, bytes=total, excluded=counts,
                   exclusions=exclusions, exclusionsTruncated=sum(counts.values()) > len(exclusions))
    payload['digest'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()
    return payload


def normalize_source_results(raw, manifest):
    if not isinstance(raw, dict) or 'driver_error' in raw: raise LocalApplicationError('source_tool_failed')
    expected = {'bandit' for x in manifest['languages'] if x == 'python'} | {'semgrep' for x in manifest['languages'] if x == 'javascript'}
    if set(raw) != expected: raise LocalApplicationError('source_tool_report_invalid')
    approved = {x['path']: x for x in manifest['files']}
    results, seen, errors, unprocessed, details = [], set(), 0, [], []
    for scanner, document in raw.items():
        if not isinstance(document, dict) or not isinstance(document.get('results'), list): raise LocalApplicationError('source_tool_report_invalid')
        failures = document.get('errors', 0)
        errors += len(failures) if isinstance(failures, list) else failures if type(failures) is int and failures >= 0 else 1
        suffixes = EXTENSIONS['python' if scanner == 'bandit' else 'javascript']
        expected_files = {x for x in approved if Path(x).suffix.lower() in suffixes}
        scanned = {x[len('/input/'):] for x in document.get('scanned', []) if isinstance(x, str) and x.startswith('/input/')}
        unprocessed.extend(sorted(expected_files - scanned))
        skipped = {x.get('path'): x.get('reason') for x in document.get('skipped', []) if isinstance(x, dict)}
        for relative in sorted(expected_files - scanned):
            reason = skipped.get('/input/' + relative, 'not_reported_by_scanner')
            if reason not in {'parse_error', 'timeout', 'excluded', 'too_large', 'minified', 'analysis_failed'}:
                reason = 'not_reported_by_scanner'
            details.append(dict(path=relative, scanner=scanner, reason=reason))
        for row in document['results']:
            filename = row.get('filename' if scanner == 'bandit' else 'path', '')
            if not isinstance(filename, str) or not filename.startswith('/input/'): continue
            relative = filename[len('/input/'):]
            rule = row.get('test_id' if scanner == 'bandit' else 'check_id', '')
            line = row.get('line_number') if scanner == 'bandit' else row.get('start', {}).get('line')
            if relative not in approved or rule not in TITLES or type(line) is not int or not 1 <= line <= approved[relative]['lines']: continue
            key = scanner, rule, relative, line
            if key in seen: continue
            seen.add(key)
            results.append(dict(scanner=scanner, rule_id=rule, title=TITLES[rule], path=relative, line=line,
                                severity='review', category='source-risk-candidate', confirmed=False, submission_ready=False))
            if len(results) > 500: raise LocalApplicationError('source_finding_limit')
    return dict(findings=results, toolErrors=errors, unprocessedFiles=sorted(set(unprocessed)), unprocessedDetails=details,
                scannedFiles=len(approved) - len(set(unprocessed)), complete=errors == 0 and not unprocessed, rawCodeRetained=False, modelCalls=0,
                networkMode='none', sourceFiles=len(approved), sourceBytes=manifest['bytes'])


class SourceScanner(ZapOfflineScanner):
    registry_file = 'source_scanners.json'
    image_pattern = r'semgrep/semgrep@sha256:[a-f0-9]{64}'

    def prepare(self):
        super().prepare()
        try:
            self.wheels = json.loads((self.root / 'config/integrations/source_wheels.json').read_text(encoding='utf-8'))
            for name, digest in self.wheels.items():
                if Path(name).name != name or not name.endswith('.whl'): raise ValueError()
                if hashlib.sha256((self.root / 'vendor/source-audit/wheels' / name).read_bytes()).hexdigest() != digest: raise ValueError()
        except (OSError, ValueError, TypeError): raise LocalApplicationError('source_scanner_unavailable') from None

    def command(self, work, name):
        return self._docker_args('create', '--name', name, '--label', 'src-auto.passive.owner=' + name,
            '--pull', 'never', '--network', 'none', '--hostname', 'localhost', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--cpus', '1', '--memory', '1024m', '--memory-swap', '1024m',
            '--pids-limit', '64', '--log-driver', 'none', '--user', '1000:1000', '--no-healthcheck',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=32m,uid=1000,gid=1000',
            '--tmpfs', '/tools:rw,nosuid,size=32m,uid=1000,gid=1000', '--tmpfs', '/out:rw,nosuid,size=16m,uid=1000,gid=1000',
            '--mount', 'type=bind,source={},target=/input,readonly'.format((work / 'input').resolve()),
            '--mount', 'type=bind,source={},target=/trusted,readonly'.format((work / 'trusted').resolve()),
            '--mount', 'type=bind,source={},target=/input-manifest.json,readonly'.format((work / 'manifest.json').resolve()),
            '--entrypoint', '/usr/bin/python3', self.image, '/trusted/driver.py')

    def run_source(self, manifest, cancel, gate, timeout=300):
        self.prepare()
        work = project_path(self.root, 'runs', 'source', 'src-auto-source-' + uuid.uuid4().hex)
        work.mkdir(parents=True, exist_ok=False)
        owned_files, owned_dirs, name = [], [work], work.name
        started = time.monotonic()
        def remaining():
            value = timeout - (time.monotonic() - started)
            if value <= 0: raise LocalApplicationError('task_timeout')
            return value
        def write(relative, content):
            destination = work / relative
            for directory in reversed([destination.parent] + list(destination.parent.parents)):
                if directory == work or work not in directory.parents: continue
                if not directory.exists(): directory.mkdir(); owned_dirs.append(directory)
            # Register ownership before writing so a partial disk write is also cleaned up.
            owned_files.append(destination)
            destination.write_bytes(content)
        try:
            for index, file in enumerate(manifest['files']):
                reason = 'cancelled' if cancel.is_set() else gate()
                if reason: raise LocalApplicationError(reason)
                content = _read(Path(manifest['directory']) / file['path'], Path(manifest['directory']))
                if hashlib.sha256(content).hexdigest() != file['sha256']: raise LocalApplicationError('source_changed_after_approval')
                write('input/' + file['path'], content)
                if index % 10 == 0 or index + 1 == len(manifest['files']):
                    getattr(self, 'progress', lambda **value: None)(phase='snapshot', prepared=index + 1, total=len(manifest['files']))
            write('manifest.json', json.dumps({'languages': manifest['languages']}).encode())
            # The approval manifest, not Semgrep's default ignore template, owns
            # file selection. Never copy the reviewed project's ignore rules/hooks.
            write('input/.semgrepignore', b'')
            for filename, digest in self.wheels.items():
                content = (self.root / 'vendor/source-audit/wheels' / filename).read_bytes()
                if hashlib.sha256(content).hexdigest() != digest: raise LocalApplicationError('source_configuration_changed')
                write('trusted/wheels/' + filename, content)
            write('trusted/driver.py', (self.root / 'tools/source_audit_container.py').read_bytes())
            write('trusted/rules.json', (self.root / 'config/integrations/source_rules.json').read_bytes())
            write('trusted/empty.ini', b'[bandit]\n')
            write('trusted/bandit.json', json.dumps({'tests': [x for x in TITLES if x.startswith('B')]}).encode())
            reason = 'cancelled' if cancel.is_set() else gate()
            if reason: raise LocalApplicationError(reason)
            self.process.run(self.command(work, name), min(8, remaining()), 4096)
            row = json.loads(self.process.run(self._docker_args('inspect', name), min(8, remaining()), 65536))[0]
            host = row['HostConfig']
            if host['NetworkMode'] != 'none' or host.get('PortBindings') or host.get('Privileged') or not host['ReadonlyRootfs'] or host.get('ExtraHosts') or row['Image'] != self.image_id or len(row['Mounts']) != 3 or any(x['RW'] for x in row['Mounts']):
                raise LocalApplicationError('tool_isolation_invalid')
            getattr(self, 'progress', lambda **value: None)(phase='scanner', prepared=len(manifest['files']), total=len(manifest['files']))
            raw = json.loads(self.process.run(self._docker_args('start', '-a', name), remaining(), 1048576))
            result = normalize_source_results(raw, manifest)
            result.update(image=self.image, banditVersion='1.9.4', semgrepVersion='1.179.0',
                          rulePackHash=hashlib.sha256((self.root / 'config/integrations/source_rules.json').read_bytes()).hexdigest())
            return result
        except (KeyError, TypeError, json.JSONDecodeError): raise LocalApplicationError('source_tool_report_invalid') from None
        finally:
            cleanup_error = None
            try:
                # Unique task-owned name; rm is attempted even if create timed out.
                self.process.run(self._docker_args('rm', '-f', name), 8, 4096, check=False)
            except (OSError, LocalApplicationError):
                # Absence after a failed create is harmless; an owned live
                # container is not silently reported as cleaned up.
                try: self.process.run(self._docker_args('inspect', name), 8, 4096, check=False)
                except LocalApplicationError:
                    if not any(x in getattr(self.process, 'last_output', b'') for x in (b'No such object', b'No such container')):
                        cleanup_error = 'tool_cleanup_failed'
                else: cleanup_error = 'tool_cleanup_failed'
            try:
                for file in reversed(owned_files): file.unlink(missing_ok=True)
                for directory in sorted(set(owned_dirs), key=lambda x: len(x.parts), reverse=True): directory.rmdir()
            finally:
                if cleanup_error: raise LocalApplicationError(cleanup_error)


class SourceExecutionGuard:
    """Task-scoped measurement: bounded sampling, conservative growth allowance.

    STOP, deadline, configuration, free space and resource checks remain live on
    every call. Expensive workspace traversal is sampled, never assumed allowed.
    """
    def __init__(self, root, cancel, scanner_hash, source_bytes):
        self.root, self.cancel, self.scanner_hash = root, cancel, scanner_hash
        self.started, self.measured, self.disk = time.monotonic(), None, None
        self.disk_guard = DiskGuard(root)
        self.resources = WindowsResources(load_mapping(root / 'config/policy.yaml'))
        self.reserve_bytes = source_bytes + 64 * 1048576
        self.model_hash = ''
        self.pulse, self.pulsed = None, time.monotonic()

    def __call__(self, force=False):
        if self.cancel.is_set() or StopController(self.root / 'STOP').requested(): return 'cancelled'
        if self.scanner_hash and scanner_config_hash(self.root, True) != self.scanner_hash: return 'source_configuration_changed'
        if self.model_hash and hashlib.sha256((self.root / 'config/models.yaml').read_bytes()).hexdigest() != self.model_hash:
            return 'source_configuration_changed'
        if time.monotonic() - self.started > 300: return 'task_timeout'
        if force or self.measured is None or time.monotonic() - self.measured >= 5:
            self.disk = self.disk_guard.check()
            self.measured = time.monotonic()
        if not self.disk.get('allowed') or not self.disk.get('known'): return 'blocked_disk'
        if float(self.disk['used_gb']) + .001 + self.reserve_bytes / 1024**3 >= self.disk_guard.hard_used_gb: return 'blocked_disk'
        try:
            if shutil.disk_usage(self.root).free < self.reserve_bytes: return 'blocked_disk'
        except OSError: return 'blocked_disk'
        if not self.resources.check()['allowed']: return 'resource_limit'
        if time.monotonic() - self.started > 300: return 'task_timeout'
        if self.pulse and time.monotonic() - self.pulsed >= 1:
            self.pulse()
            self.pulsed = time.monotonic()
        return ''


class SourceAuditCoordinator:
    def __init__(self, service):
        self.service, self.root, self.approvals = service, service.root, {}

    def preview(self, document):
        if not isinstance(document, dict) or set(document) != {'directory', 'languages', 'confirmRead', 'confirmSnapshot'} or document['confirmSnapshot'] is not True:
            raise ValueError('source_authorization_required')
        if self.service.control._closing: raise RuntimeError('dashboard_closing')
        deadline = time.monotonic() + 30
        def gate():
            if StopController(self.root / 'STOP').requested(): return 'cancelled'
            if time.monotonic() > deadline: return 'task_timeout'
            return ''
        manifest = source_manifest(document['directory'], document['languages'], document['confirmRead'], gate=gate)
        SourceScanner(self.root, threading.Event(), gate).prepare()
        key = uuid.uuid4().hex
        with self.service.control._lock:
            self.approvals = {k: v for k, v in self.approvals.items() if v['expires'] > time.monotonic() and not v['used']}
            if len(self.approvals) >= 20: raise ValueError('source_approval_limit')
            self.approvals[key] = dict(manifest=manifest, expires=time.monotonic() + 1800, used=False, scannerHash=scanner_config_hash(self.root, True))
        return dict(approvalId=key, digest=manifest['digest'], directory=manifest['directory'], languages=manifest['languages'],
                    files=len(manifest['files']), bytes=manifest['bytes'], excluded=manifest['excluded'], networkContact=False,
                    fileList=[x['path'] for x in manifest['files']], exclusions=manifest['exclusions'], exclusionsTruncated=manifest['exclusionsTruncated'],
                    modelCalls=0, expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())

    def start(self, document, remote_session_enabled=False):
        if (not isinstance(document, dict) or not {'approvalId', 'confirmStart'} <= set(document)
                or set(document) - {'approvalId', 'confirmStart', 'allowCloud'} or document['confirmStart'] is not True
                or type(document.get('allowCloud', False)) is not bool): raise ValueError('manual_execution_confirmation_required')
        cloud = document.get('allowCloud', False)
        if cloud and not remote_session_enabled: raise ValueError('remote_ai_disabled_for_session')
        service = self.service
        with service.control._lock:
            approval = self.approvals.get(document['approvalId'])
            if not approval or approval['expires'] <= time.monotonic(): raise ValueError('source_approval_expired')
            if approval['used']: raise ValueError('approval_already_used')
            if service.control._closing: raise RuntimeError('dashboard_closing')
            if service.active or service.control.lifecycle()['activeWork']: raise RuntimeError('agent_operation_conflict')
            manifest = approval['manifest']
            if scanner_config_hash(self.root, True) != approval['scannerHash']: raise ValueError('source_configuration_changed')
            cancel = threading.Event()
            gate = SourceExecutionGuard(self.root, cancel, approval['scannerHash'], manifest['bytes'])
            # Revalidate before queueing and again during the bounded snapshot.
            current = source_manifest(manifest['directory'], manifest['languages'], True, gate=gate)
            if current['digest'] != manifest['digest']: raise ValueError('source_changed_after_approval')
            scanner = SourceScanner(self.root, cancel, gate)
            scanner.prepare()
            budget, provider = None, None
            if cloud:
                gate.model_hash = hashlib.sha256((self.root / 'config/models.yaml').read_bytes()).hexdigest()
                budget = DeepSeekAgentBudget.configured(self.root)
                provider = service.model_factory(self.root, 'deepseek', remote_session_enabled, True).provider
                provider.max_output_tokens = 512
                reason = gate()
                if reason: raise LocalApplicationError(reason)
            config_hash = hashlib.sha256((manifest['digest'] + approval['scannerHash']).encode()).hexdigest()
            if cloud: config_hash = hashlib.sha256((config_hash + gate.model_hash).encode()).hexdigest()
            actions = SimpleNamespace(scope_hash=manifest['digest'], config_hash=config_hash)
            row = service.history.create('source-' + manifest['digest'][:12], 'source-audit', 'deepseek' if cloud else 'none',
                Limits(max_model_calls=4 if cloud else 0, max_tokens=20000 if cloud else 0, max_seconds=300), actions)
            service.history.update(row['id'], targetType='source_audit', directory=manifest['directory'])
            approval['used'] = True
            service.current_id, service.cancel = row['id'], cancel
            try: service.executor.submit(self._run, row['id'], manifest, scanner, gate, cancel, provider, budget)
            except Exception:
                service.current_id = None
                service.history.update(row['id'], state='failed', reason='queue_unavailable')
                raise RuntimeError('queue_unavailable') from None
            return {'accepted': True, 'id': row['id']}

    def _review(self, key, standard_id, result, provider, budget, store, gate):
        grouped = {}
        for finding in result['findings']:
            grouped.setdefault(finding['rule_id'], []).append(finding)
        review = dict(groups=[], errors=[], maxCalls=4, reviewedCandidates=0, unreviewedCandidates=len(result['findings']),
                      payloadPolicy='anonymous_rule_counts_only', reservedCny=0, estimatedCny=0, usageEstimated=False)
        result['cloudReview'] = review
        for rule in sorted(grouped)[:4]:
            if self.service.history.get(key)['tokens'] + 8000 > 20000:
                review['errors'].append(dict(rule=rule, reason='model_token_limit')); break
            reason = gate(force=True)
            if reason: raise LocalApplicationError(reason)
            group = grouped[rule]
            payload = dict(title=TITLES[rule], url='', parameter='', severity='review',
                evidence=json.dumps(dict(scanner=group[0]['scanner'], rule=rule, candidates=len(group),
                    sourceCodeProvided=False, dataflowVerified=False, exploitabilityVerified=False), ensure_ascii=False))
            request = RemoteReviewRequest.from_finding(payload)
            try: reserved = budget.reserve(standard_id)
            except RuntimeError:
                review['errors'].append(dict(rule=rule, reason='cloud_budget_limit')); break
            review['reservedCny'] = round(review['reservedCny'] + reserved, 8)
            row = self.service.history.get(key)
            calls = row['modelCalls'] + 1
            result['modelCalls'] = calls
            self.service.history.update(key, modelCalls=calls, reason='source_cloud_review', sourceAudit=result)
            provider.timeout_seconds = max(1, min(60, int(300 - (time.monotonic() - gate.started))))
            try:
                response = provider.review(payload)
                estimated = response.get('usage_estimated', False)
                cost = budget.estimate(response['input_tokens'], response['output_tokens'], estimated)
                # Bookkeeping remains truthful even if STOP/configuration changes
                # arrive during a request that has already been billed.
                review['estimatedCny'] = round(review['estimatedCny'] + cost, 8)
                review['usageEstimated'] = review['usageEstimated'] or estimated
                tokens = row['tokens'] + (8000 if estimated else response['input_tokens'] + response['output_tokens'])
                self.service.history.update(key, tokens=tokens, sourceAudit=result)
                reason = gate()
                if reason: raise LocalApplicationError(reason)
                record = dict(response, run_id=standard_id, finding_fingerprint='source-rule:' + rule, payload_digest=request.digest)
                store.insert_ai_review(record)
                review['groups'].append(dict(rule=rule, candidates=len(group), **response))
                review['reviewedCandidates'] += len(group)
                review['unreviewedCandidates'] -= len(group)
                self.service.history.update(key, tokens=tokens, sourceAudit=result)
            except RemoteProviderError:
                # A billed but malformed/failed request is not a zero-cost success.
                review['errors'].append(dict(rule=rule, reason='remote_review_failed'))
                review['estimatedCny'] = round(review['estimatedCny'] + reserved, 8)
                review['usageEstimated'] = True
                self.service.history.update(key, tokens=row['tokens'] + 8000, sourceAudit=result)
        result['modelCalls'] = self.service.history.get(key)['modelCalls']

    def _run(self, key, manifest, scanner, gate, cancel, provider=None, budget=None):
        service, started = self.service, time.monotonic()
        store, lease, standard_id = Store(self.root / 'data/src_auto.sqlite3'), None, ''
        result = None
        gate.pulse = lambda: service.history.update(key, elapsedSeconds=round(time.monotonic() - started, 2))
        try:
            service.history.acquire(key)
            standard_id = store.create_run('source-' + manifest['digest'][:12], manifest['digest'], 'local')
            lease = store.claim_local_application(standard_id, manifest['digest'], 'source-' + manifest['digest'][:12], 'source:' + manifest['directory'])
            service.history.update(key, standardRunId=standard_id, reason='source_snapshot_and_scanner')
            scanner.progress = lambda **value: service.history.update(key, sourceProgress=value,
                elapsedSeconds=round(time.monotonic() - started, 2))
            reason = gate(force=True)
            if reason: raise LocalApplicationError(reason)
            result = scanner.run_source(manifest, cancel, gate)
            service.history.update(key, candidates=len(result['findings']), sourceAudit=result, steps=1,
                                   observations=[dict(id='o1', action='source_audit', reference='entry', summary='已真实静态分析批准快照；候选待人工复核')])
            for finding in result['findings']:
                store.insert_finding(dict(run_id=standard_id, title=finding['title'], url='source://' + finding['path'], parameter=str(finding['line']),
                    severity='info', status='candidate', evidence='{} {} 行 {}；仅静态风险，不代表可利用漏洞'.format(finding['scanner'], finding['rule_id'], finding['line']),
                    triage={'confirmed': False, 'submission_ready': False, 'category': finding['category'], 'agent_id': key}))
            if provider:
                self._review(key, standard_id, result, provider, budget, store, gate)
            cloud_incomplete = provider and (result['cloudReview']['errors'] or result['cloudReview']['unreviewedCandidates'])
            reason = gate()
            if reason: raise LocalApplicationError(reason)
            service.history.update(key, state='completed' if result['complete'] and not cloud_incomplete else 'needs-human',
                reason='source_cloud_review_incomplete' if cloud_incomplete else 'source_audit_completed' if result['complete'] else 'source_parser_errors',
                sourceAudit=result, steps=2 if provider else 1)
        except Exception as exc:
            reason = exc.reason if isinstance(exc, LocalApplicationError) else 'source_audit_failed'
            service.history.update(key, state='cancelled' if reason == 'cancelled' else 'needs-human', reason=reason)
        finally:
            try:
                row = service.history.update(key, elapsedSeconds=round(time.monotonic() - started, 2), sourceAudit=result)
                report = project_path(self.root, 'reports', 'source', key + '.md')
                report.parent.mkdir(parents=True, exist_ok=True)
                text = '\n'.join(['# 源码安全审查（人工复核草稿）', '', '状态：{}；原因：{}'.format(row['state'], row['reason']),
                    '目录：' + manifest['directory'], '快照摘要：' + manifest['digest'],
                    '批准文件 {} 个，{} 字节；排除计数：{}'.format(len(manifest['files']), manifest['bytes'], json.dumps(manifest['excluded'], ensure_ascii=False)),
                    '云端调用 {} 次，目标 HTTP 请求 0 次。静态扫描器断网；可选云端仅发送匿名规则与数量摘要。未执行代码、安装被审项目依赖或上传源码。'.format(row['modelCalls']),
                    '排除项（最多 500 项；目录排除含整个子树）：', '```json', json.dumps(manifest['exclusions'], ensure_ascii=False, indent=2), '```',
                    '```json', json.dumps(result, ensure_ascii=False, indent=2), '```',
                    '未覆盖：运行时业务逻辑、可利用性、依赖 CVE、Git 历史、非批准语言、被排除文件及超过额度的项目。',
                    '零候选不表示安全。所有候选需要人工核验，不能自动提交补天。'])
                report.write_text(safe_text(text, 1048576), encoding='utf-8')
                report_id = report.relative_to(self.root).as_posix()
                service.history.update(key, reportId=report_id)
                if standard_id:
                    store.save_report(standard_id, report_id)
                    store.set_run_status(standard_id, row['state'])
            except Exception: service.history.update(key, state='failed', reason='source_report_failed')
            finally:
                if lease: store.release_local_application(standard_id, lease)
                store.close()
                with service.control._lock: service.current_id = None

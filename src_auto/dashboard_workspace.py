"""Project-local Dashboard storage and read-only access to existing artifacts."""
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .ai import _redact, _safe_url
from .offline_scope_picker import inspect_review_targets
from .target_review import review_target_selection


def safe_text(value, limit=262144):
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b', '[REDACTED]', str(value or ''))
    text = re.sub(r'(?im)^(.*(?:authorization|cookie|api[_-]?key|password|secret|token)[\"\s]*[:=]).*$', r'\1 [REDACTED]', text)
    text = re.sub(r'https?://[^\s<>"`]+', lambda m: _safe_url(m.group()), text)
    return _redact(text, limit)


class DashboardWorkspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.targets = self.root / 'config' / 'targets'

    def _inside(self, path, root=None):
        resolved = Path(path).resolve()
        resolved.relative_to((root or self.root).resolve())
        return resolved

    def save_draft(self, value):
        fields = ('projectName', 'targetUrl', 'allowedHosts', 'allowedPorts', 'excludedPaths',
                  'windowStart', 'windowEnd', 'allowedMethods', 'concurrency', 'requestLimit', 'authorizationNote')
        if not isinstance(value, dict) or set(value) != set(fields):
            raise ValueError('draft_fields_invalid')
        if any(not isinstance(value[k], str) or len(value[k]) > 4000 for k in fields):
            raise ValueError('draft_value_invalid')
        value = {k: value[k].strip() for k in fields}
        if any(not value[k] for k in fields if k != 'excludedPaths'):
            raise ValueError('draft_required_fields')
        parsed = urlsplit(value['targetUrl'])
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('draft_url_invalid')
        hosts = [h.strip().lower() for h in value['allowedHosts'].split(',')]
        if not any(parsed.hostname.lower() == h or (h.startswith('*.') and parsed.hostname.lower().endswith(h[1:])) for h in hosts):
            raise ValueError('draft_host_outside_scope')
        ports = [int(p.strip()) for p in value['allowedPorts'].split(',')]
        if any(p < 1 or p > 65535 for p in ports) or (parsed.port or (443 if parsed.scheme == 'https' else 80)) not in ports:
            raise ValueError('draft_port_outside_scope')
        if datetime.fromisoformat(value['windowEnd']) <= datetime.fromisoformat(value['windowStart']):
            raise ValueError('draft_time_invalid')
        if not 1 <= int(value['concurrency']) <= 20 or not 1 <= int(value['requestLimit']) <= 100000:
            raise ValueError('draft_limits_invalid')
        methods = [m.strip().upper() for m in value['allowedMethods'].split(',')]
        if any(m not in ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE') for m in methods):
            raise ValueError('draft_methods_invalid')
        identity = 'dashboard-' + uuid.uuid4().hex
        target = self._inside(self.targets / identity)
        target.mkdir(parents=True, exist_ok=False)
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        result = dict(valid=True, id=identity, draft=value, normalizedUrl=value['targetUrl'],
                      scopeDigestSuffix='scope-' + digest, networkContact='none',
                      message='草稿已保存到项目目录，尚未确认授权', savedPath=target.relative_to(self.root).as_posix())
        candidate = dict(target_id=identity, allowed_hosts=hosts, allowed_ports=ports,
                         confirmed=False, allow_network_contact=False, draft=value)
        # Each save creates a new immutable revision; never overwrite a confirmed scope.
        for name, data in [('scope_candidate.yaml', candidate), ('draft.json', result)]:
            temporary = target / (name + '.tmp')
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(target / name))
        return result

    def list_drafts(self):
        if not self.targets.exists(): return []
        self._inside(self.targets)
        files = sorted(self.targets.glob('dashboard-*/draft.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        results = []
        for path in files[:100]:
            path = self._inside(path, self.targets)
            if path.stat().st_size > 65536: continue
            item = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(item, dict) and isinstance(item.get('draft'), dict): results.append(item)
        return results

    def review_targets(self, relative='.'):
        selected = self._inside(self.targets / relative, self.targets)
        self._inside(selected)
        if not self.targets.exists(): return []
        results = []
        for entry in inspect_review_targets(selected, self.targets)[:100]:
            result = dict(name=entry.relative_name, status=entry.status, actionable=entry.actionable,
                          networkContact='none')
            if entry.actionable:
                review = review_target_selection(self.root, entry.scope_path, entry.plan_path)
                result['review'] = {
                    'status': review['status'], 'reason': safe_text(review['reason'], 500),
                    'targetCount': review.get('target_count', 0), 'network_contact': False}
            results.append(result)
        return results

    def artifacts(self):
        reports, findings, warnings = [], [], []
        report_path = self.root / 'reports'
        if report_path.is_symlink():
            return dict(reports=[], findings=[], warnings=['报告目录是符号链接，已拒绝读取'])
        report_root = self._inside(report_path)
        if report_root.exists():
            files = []
            # Reports are grouped by run/lab in subdirectories.  Walk them
            # without following links so a nested report can be previewed
            # without broadening the project-local trust boundary.
            for directory, names, filenames in os.walk(report_root, topdown=True, followlinks=False):
                current = Path(directory)
                names[:] = [name for name in names if not (current / name).is_symlink()
                            and (current / name).resolve().parent == current.resolve()]
                for filename in filenames:
                    path = current / filename
                    if path.suffix.lower() in ('.md', '.txt', '.json', '.html', '.log', '.xml'):
                        try:
                            if path.is_symlink():
                                raise ValueError('report_symlink_not_allowed')
                            self._inside(path, report_root)
                            files.append((path.stat().st_mtime, path))
                        except (OSError, ValueError):
                            warnings.append('部分报告无法读取或路径不在允许范围')
            files.sort(key=lambda item: item[0], reverse=True)
            for _, path in files[:30]:
                try:
                    if path.is_symlink():
                        raise ValueError('report_symlink_not_allowed')
                    path = self._inside(path, report_root)
                    size = path.stat().st_size
                    with path.open('r', encoding='utf-8-sig', errors='replace') as stream:
                        content = stream.read(65536)
                    if size > 65536: content += '\n[预览已截断，请在本地查看完整报告]'
                    relative = path.relative_to(self.root).as_posix()
                    reports.append(dict(id=relative, name=safe_text(path.name, 200), relativePath=relative,
                                        sizeBytes=size, content=safe_text(content), redacted=True))
                except (OSError, ValueError): warnings.append('部分报告无法读取或路径不在允许范围')
        db = self._inside(self.root / 'data' / 'src_auto.sqlite3')
        if db.exists():
            connection = None
            try:
                connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)
                connection.row_factory = sqlite3.Row
                for row in connection.execute('SELECT id,title,severity,evidence,run_id FROM findings ORDER BY id DESC LIMIT 100'):
                    severity = row['severity'] if row['severity'] in ('high', 'medium', 'low', 'info') else 'info'
                    findings.append(dict(id=str(row['id']), title=safe_text(row['title'], 300), severity=severity,
                                         source='历史运行 ' + safe_text(row['run_id'], 100), state='待人工复核',
                                         summary='从本地结果数据库读取，不代表本次靶场启动发现的漏洞',
                                         evidence=safe_text(row['evidence'], 2000), prerequisites=[], impact='需人工复核'))
            except sqlite3.Error: warnings.append('结果数据库暂时不可读，请稍后刷新')
            finally:
                if connection is not None: connection.close()
        return dict(reports=reports, findings=findings, warnings=warnings)

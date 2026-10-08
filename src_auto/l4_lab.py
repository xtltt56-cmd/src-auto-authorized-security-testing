"""Operator-started synthetic L4 lab: memory-only data, no app cloning/reset.

Finite GET routes contain a two-row SQL boolean lesson and an inert HTML marker.
There is deliberately no script, event handler, stored payload or command input.
"""
import hashlib
import html
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agent_runner import process_identity, project_path
from .business_preparation import BusinessPreparation, ROLES
from .local_targets import LocalTargetLibrary
from .local_application_workflow import listener_identity

CONTROL_PATHS = tuple('/l4/{}/{}/{}'.format(kind, variant, probe)
    for kind, probes in (('sqli', ('baseline', 'true', 'false')), ('xss', ('marker',)))
    for variant in ('vulnerable', 'protected') for probe in probes)
OBJECT_PATHS = ('/l4/objects/object-1', '/l4/objects/object-2')


def registered_fixture(root, origin, identity):
    folder = project_path(root, 'data', 'l4-fixtures')
    if not folder.exists(): return False
    for path in list(folder.glob('*.json'))[:50]:
        try:
            project_path(root, 'data', 'l4-fixtures', path.name)
            row = json.loads(path.read_text(encoding='utf-8'))
            if (row.get('schema') == 1 and row.get('origin') == origin and row.get('identity') == identity
                    and type(row.get('pid')) is int and process_identity(row['pid']) == row.get('processIdentity')):
                return True
        except (ValueError, OSError, TypeError): continue
    return False


class L4SyntheticLab:
    def __init__(self, root, port=0):
        self.root, self.received, self.wrong_object, self.redirect = root, [], False, False
        self.tokens = {role: secrets.token_hex(24) for role in ROLES[:-1]}
        self.secret_markers = list(self.tokens.values()) + ['L4_SYNTHETIC_PRIVATE_BODY']
        lab = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                # Tests collect only route/role, never the supplied secret.
                role = next((key for key, token in lab.tokens.items()
                             if self.headers.get('Authorization') == 'Bearer ' + token), 'anonymous')
                lab.received.append([self.path, role])
                status, content, mime = 200, b'', 'application/json'
                if self.path in OBJECT_PATHS:
                    if lab.redirect:
                        self.send_response(302); self.send_header('Location', '/outside'); self.send_header('Content-Length', '0'); self.end_headers(); return
                    key = self.path.rsplit('/', 1)[-1]
                    allowed = role in ('account-a', 'administrator') or (key == 'object-1' and role == 'account-b')
                    status = 200 if allowed else 403
                    value = {'id': 'wrong' if lab.wrong_object else key, 'payload': 'L4_SYNTHETIC_PRIVATE_BODY'} if allowed else {'error': 'forbidden'}
                    content = json.dumps(value).encode('utf-8')
                elif self.path in CONTROL_PATHS:
                    _, _, kind, variant, probe = self.path.split('/')
                    if kind == 'sqli':
                        value = {'baseline': '1', 'true': "1' AND '1'='1", 'false': "1' AND '1'='2"}[probe]
                        db = sqlite3.connect(':memory:')
                        try:
                            db.execute('CREATE TABLE sample (id TEXT PRIMARY KEY)')
                            db.execute("INSERT INTO sample VALUES ('1')")
                            db.execute('PRAGMA query_only=ON')
                            # Deliberately unsafe EDUCATIONAL local positive control.
                            rows = db.execute("SELECT id FROM sample WHERE id='" + value + "'").fetchall() if variant == 'vulnerable' else db.execute('SELECT id FROM sample WHERE id=?', (value,)).fetchall()
                            content = json.dumps({'rows': [x[0] for x in rows]}).encode('utf-8')
                        finally: db.close()
                    else:
                        marker = '<x-src-auto-marker></x-src-auto-marker>'
                        content = ('<html><body>' + (marker if variant == 'vulnerable' else html.escape(marker)) + '</body></html>').encode('utf-8')
                        mime = 'text/html'
                else:
                    status, content = 404, b'{}'
                self.send_response(status); self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)
            def log_message(self, *args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.origin = 'http://127.0.0.1:{}'.format(self.server.server_port)
        self.registry_path = project_path(root, 'data', 'l4-fixtures', secrets.token_hex(16) + '.json')
        self.thread = None

    def register(self):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(dict(schema=1, origin=self.origin, identity=listener_identity(self.origin),
            pid=os.getpid(), processIdentity=process_identity(os.getpid()))), encoding='utf-8')

    def start(self):
        self.register()
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.1), daemon=True)
        self.thread.start()

    def provision(self):
        target = LocalTargetLibrary(self.root).save(dict(name='L4 隔离合成业务靶场', kind='custom_lab', origin=self.origin,
            paths=list(OBJECT_PATHS + CONTROL_PATHS), excluded=['/reset', '/trade'], method='GET', profile='readonly-baseline-v1'))
        prep, sessions = BusinessPreparation(self.root), {}
        prefix = 'l4-' + secrets.token_hex(4) + '-'
        for role in ROLES[:-1]:
            name = prefix + role
            prep.save_session(dict(targetId=target['id'], targetRevision=target['revision'], name=name, role=role,
                headers={'Authorization': 'Bearer ' + self.tokens[role]}, confirmTestAccount=True,
                expiresAt=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()))
            sessions[role] = name
        row = prep.save(dict(targetId=target['id'], targetRevision=target['revision'], sessions=sessions,
            isolation=dict(dataLabel='memory-only-synthetic-sqlite', storageLabel='no-persistent-business-files',
                resetNote='关闭本前台靶场进程即可清空合成数据库；平台不会执行重置', confirmIsolatedData=True,
                confirmTestAccounts=True, confirmNoProductionSecrets=True),
            cases=[dict(id='object-' + str(i), name='合成对象 {} · {}'.format(i, '越权正例' if i == 1 else '防护对照'),
                path=OBJECT_PATHS[i-1], owner='account-a', expected={r: r in ('account-a', 'administrator') for r in ROLES}) for i in (1, 2)]))
        return target, row

    def close(self):
        if self.thread:
            self.server.shutdown(); self.thread.join(3)
        self.server.server_close()
        if self.registry_path.exists(): self.registry_path.unlink()

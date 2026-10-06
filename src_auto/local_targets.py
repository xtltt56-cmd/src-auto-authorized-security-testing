"""Local target drafts, never execution grants. No listener/network probing."""
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dashboard_workspace import safe_text
from .scope import ScopeGuard, ScopePolicy


class LocalTargetLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _connect(self):
        path = self.root / 'data/src_auto.sqlite3'
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), timeout=15)
        db.execute('CREATE TABLE IF NOT EXISTS local_target_drafts (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
        return db

    def list(self):
        db = self._connect()
        try:
            return [json.loads(x[0]) for x in db.execute('SELECT document FROM local_target_drafts ORDER BY id LIMIT 200')]
        finally:
            db.close()

    def save(self, document):
        required = {'name', 'kind', 'origin', 'paths', 'excluded', 'method', 'profile'}
        if not isinstance(document, dict) or not required <= set(document) or set(document) - required - {'id'}:
            raise ValueError('invalid_local_target')
        name = document['name']
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or safe_text(name, 256) != name or any(ord(x) < 32 for x in name):
            raise ValueError('invalid_local_target')
        if document['kind'] not in ('custom_lab', 'owned_app'):
            raise ValueError('invalid_local_target')
        key = document.get('id') or 'custom-' + uuid.uuid4().hex
        if not isinstance(key, str) or not re.fullmatch(r'custom-[a-f0-9]{32}', key):
            raise ValueError('invalid_local_target')
        now = datetime.now(timezone.utc)
        scope = ScopePolicy.from_mapping(dict(schema_version=2, target_type='local_web', target_id=key,
            origin=document['origin'], allowed_paths=document['paths'], excluded_paths=document['excluded'],
            allowed_methods=[document['method']], profile_id=document['profile'], confirmed=True,
            automation_allowed=True, allow_network_contact=True, authorization_note='draft validation only',
            window_start=(now - timedelta(minutes=1)).isoformat(), window_end=(now + timedelta(minutes=30)).isoformat(),
            limits=dict(concurrency=1, request_limit=100, task_timeout_seconds=300, request_timeout_seconds=5,
                        response_limit_bytes=65536, output_limit_bytes=1048576)))
        for path in scope.local_web.allowed_paths:
            if not ScopeGuard(scope).decide(scope.local_web.origin + path, method=document['method']).allowed:
                raise ValueError('invalid_local_target')
        row = dict(id=key, name=name.strip(), kind=document['kind'], origin=scope.local_web.origin,
                   paths=list(scope.local_web.allowed_paths), excluded=list(scope.local_web.excluded_paths),
                   method=document['method'], profile=document['profile'], confirmed=False, allowCloud=False)
        row['revision'] = hashlib.sha256(json.dumps(row, sort_keys=True).encode('utf-8')).hexdigest()
        db = self._connect()
        try:
            if not document.get('id') and db.execute('SELECT COUNT(*) FROM local_target_drafts').fetchone()[0] >= 200:
                raise ValueError('local_target_limit')
            if document.get('id') and not db.execute('SELECT 1 FROM local_target_drafts WHERE id=?', (key,)).fetchone():
                raise ValueError('local_target_not_found')
            with db:
                db.execute('INSERT OR REPLACE INTO local_target_drafts VALUES (?,?)', (key, json.dumps(row, ensure_ascii=False)))
            return row
        finally:
            db.close()

    def duplicate(self, key):
        row = next((x for x in self.list() if x['id'] == key), None)
        if not row:
            raise ValueError('local_target_not_found')
        return self.save({k: (row[k][:75] + ' 副本' if k == 'name' else row[k])
                          for k in ('name', 'kind', 'origin', 'paths', 'excluded', 'method', 'profile')})

    def delete(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'custom-[a-f0-9]{32}', key):
            raise ValueError('invalid_local_target')
        db = self._connect()
        try:
            with db:
                if not db.execute('DELETE FROM local_target_drafts WHERE id=?', (key,)).rowcount:
                    raise ValueError('local_target_not_found')
            return {'deleted': True}
        finally:
            db.close()

"""L4-A preparation only: declarations, bound sessions and explicit permissions.

No HTTP, model, process, app copy/reset, execution authorization or auto-resume.
Isolation is declared by the operator, not proved by storing a draft.
"""
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .agent_runner import project_path
from .dashboard_workspace import safe_text
from .local_scope import aware_timestamp, safe_local_path
from .local_targets import LocalTargetLibrary
from .session_vault import SessionProfile, SessionVault, SessionVaultError, bound_origin

ROLES = ('account-a', 'account-b', 'administrator', 'anonymous')
ERRORS = {
    'preparation_invalid': '请核对隔离声明、精确对象路由和四种角色的预期权限',
    'preparation_missing': '业务验证草稿不存在，请重新保存',
    'preparation_limit': '业务验证草稿数量已达上限',
    'target_missing': '先在本机应用审查保存一个本地目标草稿',
    'target_changed': '目标范围已经改变，请重新载入并核对业务规格',
    'session_invalid': '仅接受隔离测试账号、有效期及 Authorization / Cookie 凭据',
    'session_expired': '会话已经过期，请重新填写隔离测试会话',
    'session_target_mismatch': '会话与目标、入口或角色不匹配',
    'session_binding_required': '旧会话没有目标绑定，不能用于业务验证',
    'session_profile_unavailable': '会话无法解密或已经删除，请重新填写',
    'session_profile_invalid': '会话内容或绑定信息无效，请重新填写',
}


def utcnow():
    return datetime.now(timezone.utc)


def _text(value, maximum=120):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError('preparation_invalid')
    if any(ord(c) < 32 for c in value) or safe_text(value, maximum + 1) != value:
        raise ValueError('preparation_invalid')
    return value.strip()


class BusinessPreparation:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.targets = LocalTargetLibrary(self.root)

    def _connect(self):
        path = project_path(self.root, 'data', 'src_auto.sqlite3')
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), timeout=15)
        db.execute('CREATE TABLE IF NOT EXISTS business_preparations (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
        return db

    def _target(self, key, revision=None):
        target = next((x for x in self.targets.list() if x['id'] == key), None)
        if not target:
            raise ValueError('target_missing')
        if revision is not None and revision != target['revision']:
            raise ValueError('target_changed')
        return target

    def _vault(self):
        return SessionVault(self.root)

    def _rows(self):
        db = self._connect()
        try:
            return [json.loads(row[0]) for row in db.execute('SELECT document FROM business_preparations ORDER BY id LIMIT 200')]
        finally:
            db.close()

    def snapshot(self):
        return dict(targets=self.targets.list(), preparations=self._rows(),
                    sessions=[x for x in self._vault().list_profiles() if x.get('bound')], executionAvailable=False)

    def save_session(self, value):
        fields = {'targetId', 'targetRevision', 'name', 'role', 'headers', 'expiresAt', 'confirmTestAccount'}
        if not isinstance(value, dict) or set(value) != fields or value['confirmTestAccount'] is not True:
            raise ValueError('session_invalid')
        target = self._target(value['targetId'], value['targetRevision'])
        if (value['role'] not in ROLES[:-1] or not isinstance(value['headers'], dict)
                or not isinstance(value['name'], str) or not SessionVault._NAME.fullmatch(value['name'])):
            raise ValueError('session_invalid')
        try:
            expiry = aware_timestamp(value['expiresAt'], 'expiresAt')
            if not utcnow() < expiry or (expiry - utcnow()).total_seconds() > 86400 * 7:
                raise ValueError('session_expired')
            profile = SessionProfile(value['name'], value['role'], value['headers'], target['id'], target['origin'], expiry.isoformat())
            vault = self._vault()
            # A reused name cannot overwrite another target's or legacy session.
            if vault._path(profile.name).exists():
                previous = vault.load(profile.name)
                if (previous.target_id, previous.origin, previous.role) != (target['id'], target['origin'], profile.role):
                    raise ValueError('session_target_mismatch')
            vault.save(profile)
        except SessionVaultError as exc:
            raise ValueError(str(exc) if str(exc) in ERRORS else 'session_invalid') from None
        return {'saved': True, 'name': profile.name, 'targetId': target['id'], 'role': profile.role}

    def delete_session(self, value):
        if not isinstance(value, dict) or set(value) != {'name', 'targetId'}:
            raise ValueError('session_invalid')
        vault = self._vault()
        profile = vault.load(value['name'])
        if not profile.target_id or profile.target_id != value['targetId']:
            raise ValueError('session_target_mismatch')
        return {'deleted': vault.delete(value['name'])}

    def save(self, value):
        fields = {'targetId', 'targetRevision', 'isolation', 'cases', 'sessions'}
        if not isinstance(value, dict) or not fields <= set(value) or set(value) - fields - {'id'}:
            raise ValueError('preparation_invalid')
        target = self._target(value['targetId'], value['targetRevision'])
        isolation = value['isolation']
        required = {'dataLabel', 'storageLabel', 'resetNote', 'confirmIsolatedData', 'confirmTestAccounts', 'confirmNoProductionSecrets'}
        if not isinstance(isolation, dict) or not required <= set(isolation) or set(isolation) - required - {'productionOrigin'}:
            raise ValueError('preparation_invalid')
        if any(isolation[key] is not True for key in required if key.startswith('confirm')):
            raise ValueError('preparation_invalid')
        clean_isolation = {key: _text(isolation[key], 240) if not key.startswith('confirm') else True for key in required}
        production = isolation.get('productionOrigin', '')
        if production:
            try:
                production = bound_origin(production)
            except ValueError:
                raise ValueError('preparation_invalid') from None
            if production == target['origin']:
                raise ValueError('preparation_invalid')
            clean_isolation['productionOrigin'] = production
        elif target['kind'] == 'owned_app':
            raise ValueError('preparation_invalid')
        cases = value['cases']
        if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
            raise ValueError('preparation_invalid')
        clean_cases, ids = [], set()
        for case in cases:
            if not isinstance(case, dict) or set(case) != {'id', 'name', 'path', 'owner', 'expected'}:
                raise ValueError('preparation_invalid')
            key = case['id']
            if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}', key) or key in ids:
                raise ValueError('preparation_invalid')
            ids.add(key)
            path = safe_local_path(case['path'])
            if path not in target['paths'] or any(path == x or path.startswith(x.rstrip('/') + '/') for x in target['excluded']):
                raise ValueError('preparation_invalid')
            expected = case['expected']
            if case['owner'] not in ROLES[:-1] + ('public',) or not isinstance(expected, dict) or set(expected) != set(ROLES):
                raise ValueError('preparation_invalid')
            if any(type(x) is not bool for x in expected.values()):
                raise ValueError('preparation_invalid')
            clean_cases.append(dict(id=key, name=_text(case['name']), path=path, owner=case['owner'], expected=expected))
        sessions = value['sessions']
        if not isinstance(sessions, dict) or set(sessions) - set(ROLES[:-1]):
            raise ValueError('preparation_invalid')
        revisions = {}
        vault = self._vault()
        for role, name in sessions.items():
            vault.load_for_target(name, target['id'], target['origin'], role, utcnow())
            revisions[role] = hashlib.sha256(vault._path(name).read_bytes()).hexdigest()
        row = dict(targetId=target['id'], targetRevision=target['revision'], isolation=clean_isolation,
                   cases=clean_cases, sessions=sessions, sessionRevisions=revisions, state='draft',
                   executionAuthorized=False, isolationVerified=False)
        row['revision'] = hashlib.sha256(json.dumps(row, sort_keys=True).encode('utf-8')).hexdigest()
        key = value.get('id') or 'business-' + uuid.uuid4().hex
        if not isinstance(key, str) or not re.fullmatch(r'business-[a-f0-9]{32}', key):
            raise ValueError('preparation_invalid')
        db = self._connect()
        try:
            if value.get('id') and not db.execute('SELECT 1 FROM business_preparations WHERE id=?', (key,)).fetchone():
                raise ValueError('preparation_missing')
            row['id'] = key
            with db:
                if not value.get('id') and db.execute('SELECT COUNT(*) FROM business_preparations').fetchone()[0] >= 200:
                    raise ValueError('preparation_limit')
                db.execute('INSERT OR REPLACE INTO business_preparations VALUES (?,?)', (key, json.dumps(row, ensure_ascii=False)))
        finally:
            db.close()
        return row

    def preview(self, value):
        if not isinstance(value, dict) or set(value) != {'id'}:
            raise ValueError('preparation_invalid')
        row = next((x for x in self._rows() if x['id'] == value['id']), None)
        if row is None:
            raise ValueError('preparation_missing')
        blockers = []
        try:
            target = self._target(row['targetId'], row['targetRevision'])
        except ValueError as exc:
            blockers.append(str(exc))
            target = None
        if target:
            vault = self._vault()
            for role in ROLES[:-1]:
                name = row['sessions'].get(role)
                if not name:
                    blockers.append('session_required:' + role)
                    continue
                try:
                    vault.load_for_target(name, target['id'], target['origin'], role, utcnow())
                    revision = hashlib.sha256(vault._path(name).read_bytes()).hexdigest()
                    if row['sessionRevisions'].get(role) != revision:
                        blockers.append('session_changed:' + role)
                except (ValueError, OSError) as exc:
                    code = str(exc) if str(exc) in ERRORS else 'session_profile_unavailable'
                    blockers.append(code + ':' + role)
        return dict(id=row['id'], revision=row['revision'], blockers=blockers, readyForNextStage=not blockers,
                    executionAvailable=False, executionAuthorized=False, isolationVerified=False,
                    networkRequests=0, modelCalls=0, cases=len(row['cases']),
                    dataPolicy='仅核对操作员声明和加密会话；不访问目标，不运行重置，不授予执行权限。')

    def delete(self, value):
        if not isinstance(value, dict) or set(value) != {'id'}:
            raise ValueError('preparation_invalid')
        db = self._connect()
        try:
            with db:
                if not db.execute('DELETE FROM business_preparations WHERE id=?', (value['id'],)).rowcount:
                    raise ValueError('preparation_missing')
        finally:
            db.close()
        return {'deleted': True}

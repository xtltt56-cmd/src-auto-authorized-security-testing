import { useEffect, useState } from 'react'
import type { TaskRepository } from '../lib/taskRepository'
import type { BusinessCase, BusinessIsolation, BusinessPreparationRow, BusinessPreparationSnapshot, BusinessPreparationPreview, BusinessRole, LocalTarget } from '../lib/types'
import { BusinessExecutionPanel } from './BusinessExecutionPanel'

const roles: BusinessRole[] = ['account-a', 'account-b', 'administrator', 'anonymous']
const roleName: Record<BusinessRole, string> = { 'account-a': '测试账号 A', 'account-b': '测试账号 B', administrator: '测试管理员', anonymous: '匿名用户' }
const emptyIsolation = (): BusinessIsolation => ({ dataLabel: '', storageLabel: '', resetNote: '', confirmIsolatedData: false, confirmTestAccounts: false, confirmNoProductionSecrets: false })
const newCase = (number: number, target?: LocalTarget): BusinessCase => ({ id: `object-${number}`, name: '', path: target?.paths[0] ?? '', owner: 'account-a', expected: { 'account-a': false, 'account-b': false, administrator: false, anonymous: false } })
const expiresSoon = () => { const value = new Date(Date.now() + 30 * 60000); return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
const blockerText = (code: string) => {
  const [reason, role] = code.split(':')
  const labels: Record<string, string> = { target_missing: '目标已删除', target_changed: '目标范围已改变，请重新载入', session_required: '尚未绑定会话', session_expired: '会话已过期', session_changed: '会话已更新，需重新核对并保存草稿', session_target_mismatch: '会话目标或角色不匹配', session_profile_unavailable: '会话已删除或不能解密', session_profile_invalid: '会话绑定信息无效', session_binding_required: '旧会话没有目标绑定' }
  return `${labels[reason] ?? '准备资料需要重新核对'}${role in roleName ? ` · ${roleName[role as BusinessRole]}` : ''}`
}

type Perform = (operation: () => Promise<void>, failure?: string) => Promise<void>

export function BusinessPreparationPage({ repository }: { repository: TaskRepository }) {
  const [snapshot, setSnapshot] = useState<BusinessPreparationSnapshot | null>(null)
  const [targetId, setTargetId] = useState('')
  const [loaded, setLoaded] = useState<BusinessPreparationRow | null>(null)
  const [preview, setPreview] = useState<BusinessPreparationPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let active = true
    void repository.getBusinessPreparation?.().then(value => { if (active) setSnapshot(value) }).catch(() => { if (active) setNotice('准备库未连接，请重新启动新版控制台。') })
    return () => { active = false }
  }, [repository])
  const refresh = async () => { if (!repository.getBusinessPreparation) throw new Error('unavailable'); setSnapshot(await repository.getBusinessPreparation()) }
  const perform: Perform = async (operation, failure = '操作未完成，请核对目标范围、隔离声明和有效会话。') => {
    setBusy(true); setNotice('')
    try { await operation() } catch { setNotice(failure) } finally { setBusy(false) }
  }
  const target = snapshot?.targets.find(row => row.id === targetId)
  return <div className="agent-page business-preparation-page">
    <div className="page-heading"><div><h3>业务验证准备</h3><p>1 选择隔离目标 → 2 保存测试会话 → 3 填写预期权限 → 4 离线核对</p></div></div>
    <section className="surface-panel agent-form">
      <p className="agent-hint">L4-A 只做准备：保存和离线核对不会启动应用、复制生产数据、运行重置命令、访问目标或调用 AI。隔离声明是人工说明，并非系统已经证明隔离。下方 L4-B / L4-C 另行生成审批、人工确认后才执行。</p>
      <label className="form-field">隔离目标<select value={targetId} disabled={busy || !snapshot} onChange={e => { setTargetId(e.target.value); setLoaded(null); setPreview(null); setNotice('') }}><option value="">请选择已保存的本地目标</option>{snapshot?.targets.map(row => <option key={row.id} value={row.id}>{row.name} · {row.origin}</option>)}</select></label>
      {!snapshot?.targets.length ? <p className="agent-hint">先在左侧「本机应用审查」保存自定义本地目标，再回到这里。请使用单独端口、合成数据库和隔离文件目录，不选择生产实例。</p> : null}
    </section>
    <PreparationForm key={`${targetId}:${target?.revision}:${loaded?.id ?? 'new'}`} target={target} loaded={loaded} sessions={snapshot?.sessions ?? []} repository={repository} busy={busy} perform={perform} refresh={refresh} onSaved={row => { setLoaded(row); setPreview(null); setNotice('业务草稿已保存；没有授予执行权限。') }} />
    {notice ? <div className="inline-notice" role="status">{notice}</div> : null}
    <section className="surface-panel agent-form"><h4>已保存的业务草稿</h4><p className="agent-hint">载入后必须重新勾选隔离声明。核对只是检查资料和会话，不会发送请求。</p>
      {snapshot?.preparations.map(row => <div className="business-draft-row" key={row.id}><div><strong>{snapshot.targets.find(x => x.id === row.targetId)?.name ?? '目标已删除'}</strong><p>{snapshot.targets.find(x => x.id === row.targetId)?.origin ?? '入口不可用'} · {row.cases.length} 个对象 · 未授予执行权限</p><p>草稿 {row.id}</p></div><div className="inline-actions">
        <button className="action-button" disabled={busy} onClick={() => { setTargetId(row.targetId); setLoaded(row); setPreview(null); setNotice('已载入草稿；请重新核对隔离声明和测试会话。') }}>载入草稿</button>
        <button className="action-button" disabled={busy || !repository.previewBusinessPreparation} onClick={() => void perform(async () => { setPreview(null); setPreview(await repository.previewBusinessPreparation!({ id: row.id })) })}>离线核对</button>
        <button className="action-button" disabled={busy || !repository.deleteBusinessPreparation} onClick={() => { if (window.confirm('只删除此业务草稿？不会删除目标或测试会话。')) void perform(async () => { await repository.deleteBusinessPreparation!({ id: row.id }); setLoaded(null); setPreview(null); await refresh() }) }}>删除草稿</button>
      </div></div>)}{!snapshot?.preparations.length ? <p>尚无业务草稿。</p> : null}
      {loaded ? <button className="action-button" disabled={busy} onClick={() => { setLoaded(null); setPreview(null) }}>新建业务草稿</button> : null}
      {preview ? <div className="local-approval" aria-label="离线核对结果"><h4>{preview.readyForNextStage ? '准备资料齐全 · 尚未执行验证' : '准备资料尚不齐全'}</h4><ul>{preview.blockers.map((reason, i) => <li key={i}>{blockerText(reason)}</li>)}</ul><p>目标请求 {preview.networkRequests} 次 · 模型调用 {preview.modelCalls} 次 · 对象 {preview.cases} 个</p><p>隔离未自动证明；执行权限未授予。请在下方另行审批，资料齐全不代表发现漏洞或目标安全。</p></div> : null}
    </section>
    <BusinessExecutionPanel key={`${targetId}:${loaded?.id}:${loaded?.revision}`} repository={repository} preparation={loaded} />
  </div>
}

function PreparationForm({ target, loaded, sessions, repository, busy, perform, refresh, onSaved }: {
  target?: LocalTarget; loaded: BusinessPreparationRow | null; sessions: BusinessPreparationSnapshot['sessions']; repository: TaskRepository;
  busy: boolean; perform: Perform; refresh: () => Promise<void>; onSaved: (row: BusinessPreparationRow) => void;
}) {
  const [isolation, setIsolation] = useState<BusinessIsolation>(() => loaded ? { ...loaded.isolation, confirmIsolatedData: false, confirmTestAccounts: false, confirmNoProductionSecrets: false } : emptyIsolation())
  const [cases, setCases] = useState<BusinessCase[]>(() => loaded?.cases ?? [newCase(1, target)])
  const [nextCase, setNextCase] = useState(() => Math.max(1, ...(loaded?.cases.map(row => Number(row.id.replace('object-', ''))).filter(Number.isFinite) ?? [])) + 1)
  const [bindings, setBindings] = useState(loaded?.sessions ?? {})
  const [role, setRole] = useState<'account-a' | 'account-b' | 'administrator'>('account-a')
  const [name, setName] = useState('')
  const [header, setHeader] = useState('Authorization')
  const [secret, setSecret] = useState('')
  const [expiresAt, setExpiresAt] = useState(expiresSoon)
  const [timeAtOpen] = useState(() => Date.now())
  const [confirmed, setConfirmed] = useState(false)
  const boundSessions = sessions.filter(row => row.targetId === target?.id && row.origin === target?.origin)
  const valid = Boolean(target && isolation.dataLabel.trim() && isolation.storageLabel.trim() && isolation.resetNote.trim()
    && isolation.confirmIsolatedData && isolation.confirmTestAccounts && isolation.confirmNoProductionSecrets
    && (target.kind !== 'owned_app' || (isolation.productionOrigin && isolation.productionOrigin !== target.origin))
    && cases.length && cases.every(row => row.name.trim() && /^[a-z0-9][a-z0-9_-]{0,39}$/.test(row.id) && target.paths.includes(row.path)) && new Set(cases.map(x => x.id)).size === cases.length)
  // Form guidance only; the server checks the current time again on save/use.
  const expiry = Date.parse(expiresAt)
  const sessionReady = Boolean(target && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(name) && secret.trim() && confirmed && Number.isFinite(expiry) && expiry > timeAtOpen && expiry <= timeAtOpen + 7 * 86400000)
  const updateCase = (index: number, patch: Partial<BusinessCase>) => setCases(rows => rows.map((row, i) => i === index ? { ...row, ...patch } : row))
  return <>
    <section className="surface-panel agent-form"><h4>隔离环境说明</h4><fieldset className="business-fieldset" disabled={busy}><div className="agent-fields local-app-fields">
      <label className="form-field">合成数据库标识<input value={isolation.dataLabel} maxLength={240} autoComplete="off" onChange={e => setIsolation({ ...isolation, dataLabel: e.target.value })} placeholder="例如：test-db-20261008（不要填写密码）" /></label>
      <label className="form-field">隔离文件目录标识<input value={isolation.storageLabel} maxLength={240} autoComplete="off" onChange={e => setIsolation({ ...isolation, storageLabel: e.target.value })} placeholder="例如：synthetic-upload-dir（仅说明，不读取目录）" /></label>
      {target?.kind === 'owned_app' ? <label className="form-field">生产实例回环入口（仅用于区分）<input value={isolation.productionOrigin ?? ''} onChange={e => setIsolation({ ...isolation, productionOrigin: e.target.value })} placeholder="http://127.0.0.1:另一端口" /></label> : null}
      <label className="form-field">人工重置说明<input value={isolation.resetNote} maxLength={240} autoComplete="off" onChange={e => setIsolation({ ...isolation, resetNote: e.target.value })} placeholder="只写说明；平台不会运行任何命令" /></label>
    </div>
    <label className="network-consent"><input type="checkbox" checked={isolation.confirmIsolatedData} onChange={e => setIsolation({ ...isolation, confirmIsolatedData: e.target.checked })} />确认数据与生产隔离，仅使用合成数据和独立存储。</label>
    <label className="network-consent"><input type="checkbox" checked={isolation.confirmTestAccounts} onChange={e => setIsolation({ ...isolation, confirmTestAccounts: e.target.checked })} />确认仅使用独立测试账号，不复用生产账号。</label>
    <label className="network-consent"><input type="checkbox" checked={isolation.confirmNoProductionSecrets} onChange={e => setIsolation({ ...isolation, confirmNoProductionSecrets: e.target.checked })} />确认环境与说明中没有生产密钥、交易凭据或个人数据。</label>
    </fieldset></section>
    <section className="surface-panel agent-form"><h4>目标绑定的测试会话</h4><p className="agent-hint">不会自动登录或续期。凭据由当前 Windows 用户 DPAPI 加密，绑定目标、入口、角色和有效期。仅在内存中暂存输入；保存尝试后立即清空；不发给云端 AI。</p>
      <fieldset className="business-fieldset" disabled={busy}><div className="agent-fields local-app-fields">
        <label className="form-field">测试角色<select value={role} onChange={e => { setRole(e.target.value as typeof role); setSecret(''); setConfirmed(false) }}>{roles.slice(0, 3).map(x => <option key={x} value={x}>{roleName[x]}</option>)}</select></label>
        <label className="form-field">会话名称<input value={name} autoComplete="off" maxLength={64} onChange={e => setName(e.target.value)} placeholder="小写字母、数字、连字符，如 isolated-a" /></label>
        <label className="form-field">凭据类型<select value={header} onChange={e => { setHeader(e.target.value); setSecret(''); setConfirmed(false) }}><option>Authorization</option><option>Cookie</option></select></label>
        <label className="form-field">会话凭据（不回显）<input type="password" value={secret} autoComplete="new-password" maxLength={8192} onChange={e => setSecret(e.target.value)} placeholder={header === 'Authorization' ? 'Bearer 后接隔离测试令牌' : 'sid=隔离测试会话'} /></label>
        <label className="form-field">会话有效至<input type="datetime-local" value={expiresAt} onChange={e => setExpiresAt(e.target.value)} /></label>
      </div><label className="network-consent"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />确认仅使用该目标的隔离测试账号；同意加密保存，最长有效期 7 天。</label>
      <button className="action-button" disabled={!sessionReady || busy || !repository.saveBusinessSession} onClick={() => {
        const credential = secret; setSecret(''); setConfirmed(false)
        void perform(async () => { await repository.saveBusinessSession!({ targetId: target!.id, targetRevision: target!.revision, name, role, headers: { [header]: credential }, expiresAt: new Date(expiresAt).toISOString(), confirmTestAccount: true }); await refresh() }, '会话未保存：请核对隔离目标、名称、凭据格式和有效期；没有显示凭据或异常原文。')
      }}>加密保存会话</button></fieldset>
      <div className="agent-fields local-app-fields">{roles.slice(0, 3).map(x => <label className="form-field" key={x}>{roleName[x]}的已存会话<select disabled={busy} value={bindings[x as keyof typeof bindings] ?? ''} onChange={e => setBindings(current => { const value = { ...current }; if (e.target.value) value[x as keyof typeof value] = e.target.value; else delete value[x as keyof typeof value]; return value })}><option value="">尚未绑定</option>{boundSessions.filter(row => row.role === x && !row.expired).map(row => <option key={row.name} value={row.name}>{row.name} · {new Date(row.expiresAt).toLocaleString('zh-CN')}</option>)}</select></label>)}</div>
      {boundSessions.map(row => <div className="business-session-row" key={row.name}><span>{row.name} · {roleName[row.role as BusinessRole]} · {row.expired ? '已过期' : '已加密保存'}</span><button className="action-button" disabled={busy || !repository.deleteBusinessSession} onClick={() => { if (window.confirm(`只删除加密测试会话 ${row.name}？`)) void perform(async () => { await repository.deleteBusinessSession!({ name: row.name, targetId: target!.id }); setBindings({}); await refresh() }) }}>删除会话</button></div>)}
    </section>
    <section className="surface-panel agent-form"><h4>对象的预期权限</h4><p className="agent-hint">只选择目标已批准的精确路由。勾选表示该角色预期可以读取；不勾选表示预期应拒绝。这里是人工业务规格，不是检测结果。匿名用户始终不绑定凭据。</p>
      <fieldset className="business-fieldset" disabled={busy}>{cases.map((row, i) => <div className="business-case" key={i}><div className="agent-fields local-app-fields">
        <label className="form-field">对象 {i + 1} 标识（JSON 顶层 id）<input value={row.id} maxLength={40} onChange={e => updateCase(i, { id: e.target.value })} placeholder="如 object-1；小写字母、数字、连字符" /></label>
        <label className="form-field">对象 {i + 1} 名称<input value={row.name} autoComplete="off" maxLength={120} onChange={e => updateCase(i, { name: e.target.value })} placeholder="如：测试账号 A 的合成订单" /></label>
        <label className="form-field">对象 {i + 1} 路由<select value={row.path} onChange={e => updateCase(i, { path: e.target.value })}><option value="">请选择批准路由</option>{target?.paths.map(path => <option key={path}>{path}</option>)}</select></label>
        <label className="form-field">对象 {i + 1} 所属角色<select value={row.owner} onChange={e => updateCase(i, { owner: e.target.value as BusinessCase['owner'] })}>{roles.slice(0, 3).map(x => <option key={x} value={x}>{roleName[x]}</option>)}<option value="public">公开对象</option></select></label>
      </div><div className="business-permissions">{roles.map(x => <label key={x}><input type="checkbox" checked={row.expected[x]} onChange={e => updateCase(i, { expected: { ...row.expected, [x]: e.target.checked } })} />对象 {i + 1} · {roleName[x]}预期允许读取</label>)}</div><button className="action-button" disabled={cases.length === 1 || busy} onClick={() => setCases(rows => rows.filter((_, index) => index !== i))}>移除对象 {i + 1}</button></div>)}</fieldset>
      <div className="inline-actions"><button className="action-button" disabled={cases.length >= 20 || !target || busy} onClick={() => { setCases(rows => [...rows, newCase(nextCase, target)]); setNextCase(nextCase + 1) }}>增加对象（最多 20 个）</button>
      <button className="action-button" data-variant="primary" disabled={!valid || busy || !repository.saveBusinessPreparation} onClick={() => void perform(async () => { const row = await repository.saveBusinessPreparation!({ ...(loaded ? { id: loaded.id } : {}), targetId: target!.id, targetRevision: target!.revision, isolation, cases, sessions: bindings }); await refresh(); onSaved(row) })}>保存业务验证草稿</button></div>
    </section>
  </>
}

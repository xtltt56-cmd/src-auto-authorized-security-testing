import { useEffect, useState } from 'react'
import { FileText, Monitor, Square } from 'lucide-react'
import type { TaskRepository } from '../lib/taskRepository'
import type { AgentSnapshot, LocalApplicationApproval, LocalApplicationDraft, LocalTarget } from '../lib/types'

const localTime = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
const lines = (text: string) => text.split(/\r?\n/).map(x => x.trim()).filter(Boolean)
const emptyForm = () => ({ origin: '', paths: '/\n/api/health', excluded: '/api/trade\n/api/orders\n/api/reset\n/api/control', method: 'GET', start: localTime(new Date(Date.now() - 60000)), end: localTime(new Date(Date.now() + 1800000)), requests: '10', seconds: '300' })
const states: Record<string, string> = { queued: '已排队', running: '执行中', cancelling: '正在停止', completed: '检查结束 · 待人工复核', 'needs-human': '部分检查 · 需要人工处理', paused: '已暂停 · 需重新审批', interrupted: '已中断 · 未自动续跑', cancelled: '已取消', failed: '失败' }
const reasons: Record<string, string> = { model_deciding: '模型正在选择下一条批准路由', tool_executing: '正在执行批准的只读请求', observation_saved: '实际观察已保存', readonly_recipes_completed: '全部批准的只读配方已执行', finish: '模型完成覆盖检查', local_web_coverage_incomplete: '模型结束提议没有覆盖全部批准路由', resource_limit: '资源达到限制，未继续执行', operator_stop: '人工停止', model_unavailable: '模型调用失败，未自动切换', path_excluded: '跳转进入排除路由，已阻止', application_identity_changed: '目标监听实例改变，已停止' }
const errors: Record<string, string> = { application_identity_unavailable: '未找到可核验的监听实例，请先启动本机服务', application_identity_changed: '应用监听实例已变化，需要重新审批', invalid_local_application_request: '入口、路由、时间窗或额度无效', local_approval_expired: '审批已失效，请重新核对', approval_already_used: '该审批已经提交，不能重复执行', remote_ai_disabled_for_session: '本次启动禁止云端 AI', agent_operation_conflict: '已有任务执行中', agent_disabled: '本次受控 Agent 尚未启用', local_agent_route_limit: 'Agent 首版最多批准 6 条路由', path_excluded: '允许路由与排除规则冲突', local_application_setup_failed: '任务文件准备失败，未访问目标' }

export function LocalApplicationPage({ repository, onOpenReport }: { repository: TaskRepository; onOpenReport: (id: string) => void }) {
  const [form, setForm] = useState(emptyForm)
  const [targetId, setTargetId] = useState(() => `owned-web-${crypto.randomUUID().slice(0, 8)}`)
  const [library, setLibrary] = useState<LocalTarget[]>([])
  const [savedId, setSavedId] = useState<string | undefined>()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'custom_lab' | 'owned_app'>('custom_lab')
  const [profile, setProfile] = useState('readonly-baseline-v1')
  const [mode, setMode] = useState<'standard' | 'agent'>('standard')
  const [provider, setProvider] = useState<'deepseek' | 'local'>('deepseek')
  const [authorized, setAuthorized] = useState(false)
  const [cloudConsent, setCloudConsent] = useState(false)
  const [confirmedStart, setConfirmedStart] = useState(false)
  const [approval, setApproval] = useState<LocalApplicationApproval | null>(null)
  const [data, setData] = useState<AgentSnapshot | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const invalidate = () => { setApproval(null); setConfirmedStart(false) }
  const edit = (key: keyof typeof form, value: string) => { setForm(current => ({ ...current, [key]: value })); invalidate() }
  const loadTarget = (row: LocalTarget) => {
    setSavedId(row.id); setTargetId(row.id); setName(row.name); setKind(row.kind); setProfile(row.profile)
    setForm(current => ({ ...current, origin: row.origin, paths: row.paths.join('\n'), excluded: row.excluded.join('\n'), method: row.method, start: localTime(new Date(Date.now() - 60000)), end: localTime(new Date(Date.now() + 1800000)) }))
    invalidate(); setAuthorized(false); setCloudConsent(false); setMode('standard')
  }
  useEffect(() => {
    let active = true
    if (repository.listLocalTargets) void repository.listLocalTargets().then(x => { if (active) setLibrary(x.targets) }).catch(() => { if (active) setMessage('本机目标草稿库读取失败；没有自动运行目标。') })
    return () => { active = false }
  }, [repository])
  useEffect(() => {
    let active = true, refreshing = false
    const refresh = async () => {
      if (!active || refreshing) return
      refreshing = true
      try {
        if (!repository.getAgent) throw new Error('执行服务尚未支持本机应用审查')
        const next = await repository.getAgent()
        if (active) {
          setData(next)
          setSelectedId(current => current ?? next.runs.find(x => x.targetType === 'local_web')?.id ?? null)
        }
      } catch { if (active) { setData(null); setMessage('无法读取执行服务，任务状态未知；请重新启动新版控制台。') } }
      finally { refreshing = false }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [repository])
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setMessage('')
    try { await operation() }
    catch (error) { const code = error instanceof Error ? error.message : ''; const specific: Record<string, string> = { outside_test_window: '当前不在批准时间窗内，请调整时间后重新审批', passive_scanner_unavailable: 'Docker 或固定 ZAP 工具未准备好，请运行受控安装脚本，或选择 L2', scanner_configuration_changed: '固定工具配置改变，请重新审批' }; setMessage(`操作未完成：${specific[code] ?? errors[code] ?? '执行服务或配置不可用'}${code ? `（${code}）` : ''}。请检查入口、路由、时间窗与开关。`) }
    finally { setBusy(false) }
  }
  const cloudReady = Boolean(data?.remoteSessionEnabled && data.cloudAgentAvailable && cloudConsent)
  const ready = Boolean(data && authorized && form.origin && !busy && !data.activeId && repository.previewLocalApplication && (mode === 'standard' || (data.enabled && (provider === 'local' || cloudReady))))
  const preview = () => perform(async () => {
    invalidate()
    const scope: LocalApplicationDraft['scope'] = { schema_version: 2, target_type: 'local_web', target_id: targetId,
      origin: form.origin.trim(), confirmed: authorized, automation_allowed: authorized, allow_network_contact: authorized,
      allowed_paths: lines(form.paths), excluded_paths: lines(form.excluded), allowed_methods: [form.method],
      window_start: new Date(form.start).toISOString(), window_end: new Date(form.end).toISOString(),
      authorization_note: '界面操作员明确确认：自有本机 Web 应用，列出的路由无业务写入副作用，允许自动化只读检查。', profile_id: profile,
      limits: { concurrency: 1, request_limit: Number(form.requests), task_timeout_seconds: Number(form.seconds), request_timeout_seconds: 5, response_limit_bytes: 65536, output_limit_bytes: 1048576 } }
    const result = await repository.previewLocalApplication!({ scope, mode, provider: mode === 'standard' ? 'none' : provider, allowCloud: mode === 'agent' && provider === 'deepseek' && cloudConsent })
    setApproval(result)
  })
  const start = () => perform(async () => {
    if (!approval || !confirmedStart || !repository.startLocalApplication) return
    const result = await repository.startLocalApplication({ approvalId: approval.approvalId, confirmStart: true })
    setSelectedId(result.id); invalidate(); setAuthorized(false); setCloudConsent(false)
    setMessage('任务已提交至真实执行器，请在下方查看实际请求、观察与报告。关闭页面不会自动取消任务。')
  })
  const runs = data?.runs.filter(x => x.targetType === 'local_web') ?? []
  const selected = runs.find(x => x.id === selectedId)
  return <div className="agent-page local-app-page">
    <div className="page-heading"><div><h3><Monitor size={24} aria-hidden="true" /> 审查一个自有本机服务</h3><p>1. 明确只读范围　→　2. 核对审批快照　→　3. 启动检查并查看证据</p></div></div>
    <section className="surface-panel agent-form" aria-label="自定义本地目标库">
      <h4>自定义本地目标库</h4><p>只保存草稿；载入后重新授权、核对时间窗和应用实例。不会执行启动命令，也不会自动发起请求。</p>
      <div className="agent-fields local-app-fields"><label>目标名称<input value={name} maxLength={80} onChange={e => setName(e.target.value)} /></label><label>用途<select value={kind} onChange={e => setKind(e.target.value as typeof kind)}><option value="custom_lab">自己的本地靶场</option><option value="owned_app">自有本机 Web 应用</option></select></label></div>
      <div className="inline-actions"><button className="action-button" disabled={busy || !name.trim() || !form.origin || !repository.saveLocalTarget} onClick={() => void perform(async () => { const row = await repository.saveLocalTarget!({ id: savedId, name, kind, origin: form.origin.trim(), paths: lines(form.paths), excluded: lines(form.excluded), method: form.method, profile }); setSavedId(row.id); setTargetId(row.id); invalidate(); setLibrary((await repository.listLocalTargets!()).targets); setMessage('目标草稿已保存；执行授权与云端同意不会保存。') })}>{savedId ? '保存草稿修改' : '保存为新目标'}</button><button className="action-button" disabled={busy} onClick={() => { setSavedId(undefined); setName(''); setForm(emptyForm()); setKind('custom_lab'); setProfile('readonly-baseline-v1'); setMode('standard'); setMessage(''); setTargetId(`owned-web-${crypto.randomUUID().slice(0, 8)}`); setAuthorized(false); setCloudConsent(false); invalidate() }}>新建空白草稿</button></div>
      {library.map(row => <div className="inline-actions" key={row.id}><strong>{row.name}</strong><code>{row.origin}</code><button className="action-button" disabled={busy} onClick={() => loadTarget(row)}>载入 {row.name}</button><button className="action-button" disabled={busy || !repository.duplicateLocalTarget} onClick={() => void perform(async () => { await repository.duplicateLocalTarget!(row.id); setLibrary((await repository.listLocalTargets!()).targets) })}>复制 {row.name}</button><button className="action-button" disabled={busy || !repository.deleteLocalTarget} onClick={() => void perform(async () => { if (!window.confirm(`删除草稿“${row.name}”？不会删除应用、报告或任务。`)) return; await repository.deleteLocalTarget!(row.id); setLibrary((await repository.listLocalTargets!()).targets); if (savedId === row.id) { setSavedId(undefined); invalidate() } })}>删除 {row.name}</button></div>)}
    </section>
    <section className="surface-panel agent-form" aria-label="本机应用范围">
      <label className="form-field">检测配方<select value={profile} onChange={e => { setProfile(e.target.value); invalidate() }}><option value="readonly-baseline-v1">L2 只读基线 · 无扫描器</option><option value="bounded-passive-v1">L3 批准范围内链接分析 + 断网 ZAP 响应头检查</option></select></label>
      <p className="agent-hint">先自行启动目标应用。仅支持精确回环 IP 与端口；不是任意桌面程序扫描器。GET 也可能有副作用，请勿加入交易、撤单、重置、账户或持仓路由。</p>
      <div className="agent-fields local-app-fields">
        <label className="local-field-wide">本机服务入口<input placeholder="http://127.0.0.1:8765" value={form.origin} onChange={e => edit('origin', e.target.value)} autoComplete="off" /></label>
        <label>允许路由（每行一条）<textarea rows={4} value={form.paths} onChange={e => edit('paths', e.target.value)} spellCheck={false} /></label>
        <label>排除路由（每行一条）<textarea rows={4} value={form.excluded} onChange={e => edit('excluded', e.target.value)} spellCheck={false} /></label>
        <label>只读方法<select value={form.method} onChange={e => edit('method', e.target.value)}><option>GET</option><option>HEAD</option></select></label>
        <label>检查方式<select value={mode} onChange={e => { setMode(e.target.value as typeof mode); invalidate(); setCloudConsent(false) }}><option value="standard">标准只读基线（不调用 AI）</option><option value="agent">受控 Agent（逐路由真实反馈）</option></select></label>
        <label>开始时间（本机时区）<input type="datetime-local" value={form.start} onChange={e => edit('start', e.target.value)} /></label>
        <label>结束时间（本机时区）<input type="datetime-local" value={form.end} onChange={e => edit('end', e.target.value)} /></label>
        <label>总请求上限（含跳转）<input type="number" min={1} max={1000} value={form.requests} onChange={e => edit('requests', e.target.value)} /></label>
        <label>任务时长上限（秒）<input type="number" min={1} max={900} value={form.seconds} onChange={e => edit('seconds', e.target.value)} /></label>
      </div>
      <p className="agent-hint">允许路径必须逐条精确列出，不接受通配符、查询参数或编码路径。排除路径及其子路径优先。单并发；每个响应最多读取 64 KiB；不保存正文与 Cookie。{profile === 'bounded-passive-v1' ? 'L3 仅在内存解析 HTML 链接，记录已经批准的路径及阻止数量，不扩大范围；ZAP 只分析脱敏响应头，不启用正文或主动攻击规则。' : 'L2 不分析首页链接。'}</p>
      {mode === 'agent' ? <div className="local-agent-options">
        <label><input type="checkbox" checked={data?.enabled ?? false} disabled={busy || !data || !repository.enableAgent} onChange={e => { const enabled = e.target.checked; invalidate(); void perform(async () => { await repository.enableAgent!(enabled); setData(current => current ? { ...current, enabled } : null) }) }} /> 启用本次受控 Agent</label>
        <label className="form-field">决策模型<select value={provider} onChange={e => { setProvider(e.target.value as typeof provider); setCloudConsent(false); invalidate() }}><option value="deepseek">DeepSeek 云端（使用已保存的官方 API 配置）</option><option value="local">Qwen3.5-9B 本地模型</option></select></label>
        <p className="agent-hint">首版 Agent 最多批准 6 条路由。模型只能选路由编号，不能新增地址、命令或载荷；每次调用前核对额度与资源，不自动切换模型。</p>
        {provider === 'deepseek' ? <>{!data?.remoteSessionEnabled ? <p className="agent-hint">本次启动禁止云端 AI；请重新启动并明确选择启用，页面不能解除硬门。</p> : null}<label className="network-consent"><input type="checkbox" checked={cloudConsent} disabled={!data?.remoteSessionEnabled || !data.cloudAgentAvailable} onChange={e => { setCloudConsent(e.target.checked); invalidate() }} /> 同意本任务发送批准路径及脱敏响应元数据给 DeepSeek，可能产生费用；不发送原始正文、Cookie 或业务数据。</label></> : null}
      </div> : null}
      <label className="network-consent"><input type="checkbox" checked={authorized} onChange={e => { setAuthorized(e.target.checked); invalidate() }} /> 确认拥有本机应用的测试授权，以上路由无业务副作用，允许在指定时间窗内自动化只读检查。</label>
      <div className="inline-actions"><button className="action-button" data-variant="primary" disabled={!ready} onClick={() => void preview()}>核对审批摘要</button><span>此步不访问目标，不调用模型；仅核对监听实例及范围。</span></div>
      {approval ? <div className="local-approval" aria-label="审批摘要">
        <h4>审批快照 · 尚未发送目标请求</h4><p>{approval.origin} · {approval.requests.length} 条批准路由 · {approval.mode === 'standard' ? '标准只读' : 'Agent'}</p>
        <ul>{approval.requests.map(x => <li key={`${x.method}:${x.path}`}><code>{x.method} {x.path}</code></li>)}</ul>
        <details><summary>查看范围与应用实例摘要</summary><p>范围：{approval.scopeDigest}</p><p>计划：{approval.planDigest}</p><p>应用实例：{approval.applicationIdentity}</p><p>有效至：{approval.expiresAt}</p></details>
        <p className="agent-hint">{approval.dataPolicy ?? '仅保存与发送批准的响应元数据；不会确认漏洞或提交补天。'} 修改任一输入后必须重新审批。</p>
        <label className="network-consent"><input type="checkbox" checked={confirmedStart} onChange={e => setConfirmedStart(e.target.checked)} /> 确认按以上快照开始；标准模式不调用 AI，Agent 模式仅使用本次选定模型。</label>
        <button className="action-button" data-variant="primary" disabled={!ready || !confirmedStart || !repository.startLocalApplication} onClick={() => void start()}>开始本机审查</button>
      </div> : null}
    </section>
    {message ? <div className="inline-notice" role="status">{message}</div> : null}
    <div className="agent-workspace">
      <section className="surface-panel agent-history" aria-label="本机审查任务"><h4>任务与报告</h4>{runs.length ? runs.map(x => <button key={x.id} className="agent-history-row" aria-pressed={x.id === selectedId} onClick={() => setSelectedId(x.id)}><strong>{x.origin ?? x.labId}</strong><span>{states[x.state] ?? x.state}</span><small>{x.createdAt} · {x.provider === 'none' ? '无 AI' : x.provider}</small></button>) : <p>尚无本机审查记录；打开页面不会自动运行。</p>}</section>
      <section className="surface-panel agent-detail" aria-label="本机审查详情">
        {selected ? <><div className="agent-detail-header"><div><h4>{states[selected.state] ?? selected.state}</h4><p>{reasons[selected.reason] ?? selected.reason}</p></div><div className="inline-actions">{selected.id === data?.ownedActiveId ? <button className="action-button" data-variant="danger" disabled={busy || selected.state === 'cancelling'} onClick={() => void perform(async () => { await repository.cancelAgent!(selected.id); setMessage('已请求停止；在途云端调用返回或超时后，不会再发起下一条检查。') })}><Square size={15} />停止本机审查</button> : null}{selected.reportId ? <button className="action-button" onClick={() => onOpenReport(selected.reportId)}><FileText size={15} />查看完整报告</button> : null}</div></div>
          <dl className="agent-usage"><div><dt>已观察路由</dt><dd>{selected.observations.filter(x => x.action === 'inspect_local_route').length}</dd></div><div><dt>实际请求</dt><dd>{selected.requests}</dd></div><div><dt>模型调用</dt><dd>{selected.modelCalls}</dd></div><div><dt>Token{selected.usageEstimated ? '（含估算）' : ''}</dt><dd>{selected.tokens}</dd></div><div><dt>功能异常待复核</dt><dd>{selected.candidates}</dd></div></dl>
          {selected.passive ? <section className="local-approval" aria-label="L3 扫描结果"><h4>断网 ZAP 配置建议</h4><p>扫描器发起目标请求 {selected.passive.scanner_target_requests} 次；以下均不是已确认漏洞。</p><ul>{selected.passive.findings.map((x, i) => <li key={i}>{x.path} · {x.rule_id} · {x.title}</li>)}</ul><p>发现的已批准路径：{selected.passive.coverage?.discovered_approved_paths.join('、') || '无'}；阻止链接 {selected.passive.coverage?.blocked_link_count ?? 0} 个。</p></section> : null}
          <p className="agent-hint">耗时 {selected.elapsedSeconds} 秒 · {selected.id}。响应头缺失只计为配置建议；零候选不代表系统完全安全。中断或实例变化不自动续跑，请重新审批。</p>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>证据</th><th>实际检查</th><th>HTTP 状态</th><th>观察口径</th></tr></thead><tbody>{selected.observations.map(x => <tr key={x.id}><td>{x.id}</td><td><code>{x.action === 'analyze_passive_capture' ? '断网 ZAP · 脱敏响应头' : `${x.method} ${x.path}`}</code></td><td>{x.action === 'analyze_passive_capture' ? '无网络请求' : x.status_code ?? '未知'}</td><td>{x.candidate ? '功能异常 · 未确认漏洞' : x.action === 'analyze_passive_capture' ? '配置建议 · 未确认漏洞' : '只读观察'}</td></tr>)}</tbody></table></div>
          <ol className="agent-trace">{selected.trace.map((x, i) => <li key={i}><strong>{x.decision?.action === 'inspect_local_route' ? '检查批准路由' : x.decision?.action === 'finish' ? '结束提议' : '受控动作'} · {x.decision?.reference} · {x.result}</strong><p>{x.decision?.reason ?? x.reason}</p><small>模型简述不是事实裁决；{x.observationId ? `实际证据：${x.observationId}` : '没有新增观察'}</small></li>)}</ol>
        </> : <p>选择一个任务，查看真实请求、执行轨迹、覆盖与关联报告。这里不显示模拟进度百分比。</p>}
      </section>
    </div>
  </div>
}

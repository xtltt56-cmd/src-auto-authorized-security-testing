import { useEffect, useState } from 'react'
import type { TaskRepository } from '../lib/taskRepository'
import type { AgentSnapshot, BusinessExecutionApproval, BusinessPreparationRow, ReportFile } from '../lib/types'
import { ReportViewer } from '../components/ReportViewer'

const timeInput = (offset: number) => { const d = new Date(Date.now()+offset); return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16) }
const states: Record<string, string> = { queued: '排队中', running: '真实执行中', cancelling: '正在停止', cancelled: '已停止', completed: '已完成', failed: '失败', paused: '已暂停', interrupted: '已中断', 'needs-human': '需人工复核' }
const actions: Record<string, string> = { compare_business_object: '四角色对象权限对照', validate_business_controls: '固定输入正负对照', finish: '结束提议', request_human_review: '请求人工复核' }
const reasons: Record<string, string> = { business_recipes_completed: '全部固定配方已执行并留证', finish: '模型已引用全部必要观察', business_coverage_incomplete: '证据覆盖不全', business_object_baseline_invalid: '对象基线或对照不成立', business_context_changed: '规格、目标或会话已变化', operator_stop: '人工停止', cancelled: '已停止', resource_limit: '资源超过限制', model_unavailable: '模型调用未完成', tool_executing: '真实工具执行中', model_deciding: '等待模型决策' }

export function BusinessExecutionPanel({ repository, preparation }: { repository: TaskRepository; preparation: BusinessPreparationRow | null }) {
  const [data, setData] = useState<AgentSnapshot | null>(null)
  const [mode, setMode] = useState<'standard' | 'agent'>('standard')
  const [provider, setProvider] = useState<'deepseek' | 'local'>('deepseek')
  const [authorized, setAuthorized] = useState(false)
  const [cloud, setCloud] = useState(false)
  const [controls, setControls] = useState(false)
  const [start, setStart] = useState(() => timeInput(-60000))
  const [end, setEnd] = useState(() => timeInput(600000))
  const [approval, setApproval] = useState<BusinessExecutionApproval | null>(null)
  const [confirmStart, setConfirmStart] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [report, setReport] = useState<ReportFile | null>(null)
  useEffect(() => {
    let alive = true, pending = false
    const refresh = async () => {
      if (pending || !alive) return
      pending = true
      try { if (!repository.getAgent) return; const value = await repository.getAgent(); if (alive) setData(value) }
      catch { if (alive) { setData(null); setNotice('任务状态未知，无法启动；请重新连接新版执行服务。') } }
      finally { pending = false }
    }
    void refresh(); const timer = window.setInterval(() => void refresh(), 2000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [repository])
  const invalidate = () => { setApproval(null); setConfirmStart(false) }
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setNotice('')
    try { await operation() }
    catch (error) {
      const code = error instanceof Error ? error.message : ''
      const hints: Record<string, string> = { business_preparation_incomplete: '先补齐三种有效的目标绑定会话并重新保存规格', business_context_changed: '目标、规格或会话已经变化，请重新保存并审批', controlled_fixture_required: '固定输入对照仅支持由平台脚本启动并登记的 L4 合成靶场', outside_test_window: '请选择当前起算、最长 15 分钟的结束时间', application_identity_changed: '目标进程已改变，请重新审批', remote_ai_disabled_for_session: '本次启动未授权云端 AI', agent_operation_conflict: '先停止其他任务', business_object_baseline_invalid: '对象所属角色必须预期可读；公开对象至少有一种允许角色' }
      setNotice(hints[code] ?? '操作未完成；请核对已保存规格、有效会话、隔离授权与任务服务。没有显示异常原文。')
    } finally { setBusy(false) }
  }
  const cloudReady = Boolean(data?.remoteSessionEnabled && data.cloudAgentAvailable)
  const ready = Boolean(preparation && data && authorized && !busy && !data.activeId && repository.previewBusiness &&
    (mode === 'standard' || (data.enabled && (provider === 'local' || (cloudReady && cloud)))))
  const runs = data?.runs.filter(row => row.targetType === 'business_local') ?? []
  const selected = runs.find(row => row.id === selectedId) ?? runs[0]
  return <>
    <section className="surface-panel agent-form" aria-label="业务验证执行授权"><h4>L4-B / L4-C · 真实业务验证</h4>
      <p className="agent-hint">仅执行上方载入或刚保存的业务草稿版本。未保存的编辑不会参与任务。四角色只读对照需要 JSON 顶层 id 与对象标识完全一致；其他结构会显示证据不足。固定输入对照仅用于平台自带 L4 合成靶场，HTML 反射不等于已证明 XSS 执行。</p>
      <p className="agent-hint">首次练习：在项目目录运行 START_L4_LAB.ps1，保留其前台窗口；回到这里载入「L4 隔离合成业务靶场」草稿。脚本只建立内存合成数据和加密测试会话，不启动检测，也不调用 AI。</p>
      <p>{preparation ? `当前规格：${preparation.id} · ${preparation.cases.length} 个对象` : '先保存或载入一个业务草稿，再进行独立执行审批。'}</p>
      <div className="agent-fields local-app-fields">
        <label className="form-field">业务验证方式<select disabled={busy} value={mode} onChange={e => { setMode(e.target.value as typeof mode); setCloud(false); invalidate() }}><option value="standard">标准固定配方 · 不调用 AI</option><option value="agent">Agent 真实反馈决策</option></select></label>
        <label className="form-field">业务测试开始时间<input type="datetime-local" value={start} onChange={e => { setStart(e.target.value); invalidate() }} /></label>
        <label className="form-field">业务测试结束时间（最长 15 分钟）<input type="datetime-local" value={end} onChange={e => { setEnd(e.target.value); invalidate() }} /></label>
        {mode === 'agent' ? <label className="form-field">业务决策模型<select value={provider} onChange={e => { setProvider(e.target.value as typeof provider); setCloud(false); invalidate() }}><option value="deepseek">DeepSeek · 使用已保存的配置与密钥</option><option value="local">本地模型 · 不自动切换云端</option></select></label> : null}
      </div>
      <label className="network-consent"><input type="checkbox" checked={controls} onChange={e => { setControls(e.target.checked); invalidate() }} />加入固定合成 SQLi / 惰性 HTML 反射正负对照（非任意网站载荷）</label>
      <label className="network-consent"><input type="checkbox" checked={authorized} onChange={e => { setAuthorized(e.target.checked); invalidate() }} />本次仅访问已保存规格中的隔离测试实例、合成账号和无副作用精确路由；允许自动化只读对照。</label>
      {mode === 'agent' ? <><button className="action-button" disabled={busy || !data || !repository.enableAgent || Boolean(data.activeId)} onClick={() => void perform(async () => { await repository.enableAgent!(!data!.enabled); setData(await repository.getAgent!()); invalidate() })}>{data?.enabled ? '关闭本次 Agent' : '启用本次 Agent'}</button><label className="network-consent"><input type="checkbox" checked={cloud} disabled={provider !== 'deepseek' || !cloudReady || busy} onChange={e => { setCloud(e.target.checked); invalidate() }} />本次调用 DeepSeek，仅发送程序生成的脱敏观察，不发送凭据、对象正文或源码。</label></> : null}
      {!data?.remoteSessionEnabled ? <p className="agent-hint">本次启动未授权云端；保存 API 密钥不会解除硬门。标准配方仍可使用。</p> : null}
      <button className="action-button" disabled={!ready} onClick={() => void perform(async () => { invalidate(); setApproval(await repository.previewBusiness!({ id: preparation!.id, revision: preparation!.revision, confirmIsolation: true, windowStart: new Date(start).toISOString(), windowEnd: new Date(end).toISOString(), mode, provider: mode === 'standard' ? 'none' : provider, allowCloud: mode === 'agent' && provider === 'deepseek' && cloud, controls })) })}>生成业务执行审批</button>
      {approval ? <div className="local-approval"><h4>审批摘要 · 尚未执行</h4><p>{approval.origin} · 对象 {approval.objectCount} 个 · 预计最多 {approval.requestCount} 次目标请求 · {approval.provider === 'none' ? '无 AI' : approval.provider}</p><p>有效至 {new Date(approval.expiresAt).toLocaleString('zh-CN')}；绑定当前目标进程、规格与会话版本。不会追随跳转、自动登录或续跑。</p><label className="network-consent"><input type="checkbox" checked={confirmStart} onChange={e => setConfirmStart(e.target.checked)} />确认上述执行审批，立即启动本次验证；我负责隔离与授权。</label><button className="action-button" data-variant="primary" disabled={busy || !confirmStart || !data || Boolean(data.activeId) || !repository.startBusiness} onClick={() => void perform(async () => { const result = await repository.startBusiness!({ approvalId: approval.approvalId, confirmStart: true }); setSelectedId(result.id); invalidate(); setAuthorized(false); setCloud(false); setNotice('真实业务任务已提交，下面展示实际请求、模型调用、观察与报告；不显示模拟进度。'); setData(await repository.getAgent!()) })}>启动本次业务验证</button></div> : null}
      {notice ? <div className="inline-notice" role="status">{notice}</div> : null}
    </section>
    <section className="surface-panel agent-history" aria-label="业务任务历史"><h4>业务任务与证据</h4>{runs.map(row => <button key={row.id} className="agent-history-row" onClick={() => { setSelectedId(row.id); setReport(null) }}><strong>{row.origin}</strong><span>{states[row.state] ?? row.state}</span><small>{row.createdAt} · {row.provider === 'none' ? '无 AI' : row.provider}</small></button>)}
      {selected ? <><h4>{states[selected.state] ?? selected.state} · {reasons[selected.reason] ?? selected.reason}</h4><p>真实请求 {selected.requests} · 模型调用 {selected.modelCalls} · Token {selected.tokens}{selected.usageEstimated ? '（含估算）' : ''} · 候选 {selected.candidates} · 耗时 {selected.elapsedSeconds}s</p><p>候选不是已确认漏洞，完成不代表整个应用安全；最终复核与提交均由人工负责。</p><div className="inline-actions">{selected.id === data?.ownedActiveId ? <button className="action-button" disabled={busy || !repository.cancelAgent} onClick={() => void perform(async () => { await repository.cancelAgent!(selected.id); setNotice('已请求停止；在途云端调用返回或超时后不会继续检测。') })}>停止业务验证</button> : null}{selected.reportId ? <button className="action-button" disabled={busy} onClick={() => void perform(async () => { setReport(await repository.downloadReport(selected.reportId)) })}>查看业务完整报告</button> : null}</div><ol className="agent-trace">{selected.trace.map((item, i) => <li key={i}><strong>{actions[item.decision?.action ?? ''] ?? item.decision?.action} · {item.decision?.reference} · {item.result === 'ok' ? '已执行' : item.result === 'executing' ? '执行中' : '未完成'}</strong><p>{item.decision?.reason ?? item.reason}</p><small>{item.observationId ? `真实观察 ${item.observationId}` : '没有新增观察'}</small></li>)}</ol><ul>{selected.observations.map(x => <li key={x.id}>{x.id} · {x.summary} · {x.candidate ? '待复核候选' : '对照观察'}</li>)}</ul></> : <p>尚无实际业务任务；打开页面不会启动扫描。</p>}
    </section>
    {selected ? <section className="surface-panel agent-detail business-evidence" aria-label="四角色对象证据"><h4>四角色对象证据</h4>{selected.observations.filter(x => x.statuses).map(x => <div key={x.id}><p><strong>{x.reference}</strong> · {x.path} · {x.baselineValid ? '对象基线有效' : '对象基线不足，不能判定漏洞'}</p><div className="table-scroll"><table className="data-table"><thead><tr><th>测试角色</th><th>预期权限</th><th>实际 HTTP</th><th>相同对象证据</th><th>结果</th></tr></thead><tbody>{Object.entries(x.statuses ?? {}).map(([role, status]) => <tr key={role}><td data-label="测试角色">{{ 'account-a': '测试账号 A', 'account-b': '测试账号 B', administrator: '管理员', anonymous: '匿名' }[role] ?? role}</td><td data-label="预期权限">{x.expected?.[role] ? '允许' : '应拒绝'}</td><td data-label="实际 HTTP">{status}</td><td data-label="相同对象证据">{x.equivalent?.[role] ? '标识及内容摘要一致' : '没有相同对象证据'}</td><td data-label="结果">{x.equivalent?.[role] && !x.expected?.[role] ? '权限异常候选 · 待复核' : x.expected?.[role] && !x.equivalent?.[role] ? '预期可读但证据不足' : '对照观察'}</td></tr>)}</tbody></table></div></div>)}</section> : null}
    {report ? <ReportViewer report={report} onClose={() => setReport(null)} onDownload={x => repository.downloadReport(x.id)} /> : null}
  </>
}

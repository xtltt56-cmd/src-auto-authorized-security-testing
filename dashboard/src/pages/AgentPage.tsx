import { useCallback, useEffect, useState } from 'react'
import { Bot, ShieldCheck, Square, FileText } from 'lucide-react'
import type { TaskRepository } from '../lib/taskRepository'
import type { AgentRun, AgentSnapshot, AgentStart, DashboardSnapshot, Finding } from '../lib/types'

const states: Record<string, string> = { queued: '已排队', running: '执行中', cancelling: '正在停止', completed: '已结束 · 待人工复核', 'needs-human': '需要人工处理', paused: '已暂停', interrupted: '上次执行中断', failed: '执行失败', cancelled: '已取消' }
const actions: Record<string, string> = { inspect_headers: '响应头检查', discover_surface: '有限表面发现', inspect_api_schema: '读取 API 规范', compare_object_authorization: '对象授权对比', review_candidate: '读取脱敏候选', finish: '结束任务', request_human_review: '请求人工复核' }
const reasons: Record<string, string> = { model_deciding: '模型正在选择下一步', tool_executing: '执行只读工具', observation_saved: '观察已保存', finish: '模型结束任务', model_unavailable: '模型未能完成请求；不会自动切换云端', operator_stop: '人工停止', budget_limit: '动作或模型调用达到上限', duplicate_action: '阻止重复动作，等待人工处理', insufficient_evidence: '证据不足', invalid_proposal: '模型格式或动作不合法', service_interrupted: '服务中断，未自动续跑', request_human_review: '模型请求人工处理', resource_limit: '资源达到软限制', time_limit: '达到时长上限', token_reservation_limit: '剩余额度不足以启动下一次模型调用', inflight_action_uncertain: '在途动作结果未知，禁止自动重放', permission_check_incomplete: '结束提议未引用对象授权检查证据', candidate_review_incomplete: '结束提议未引用关联候选的复核证据', tool_failed: '只读工具未完成', execution_failed: '执行失败，请核对本地报告', format_repair: '正在进行唯一一次格式修正', request_limit: '达到 HTTP 请求上限', disk_free_low: '磁盘可用空间不足', scope_blocked: '请求被范围门控阻止' }

export function AgentPage({ repository, snapshot, onOpenReport }: { repository: TaskRepository; snapshot: DashboardSnapshot; onOpenReport: (id: string) => void }) {
  const [data, setData] = useState<AgentSnapshot | null>(null)
  const [labId, setLabId] = useState('business-api')
  const [mode, setMode] = useState<AgentStart['mode']>('api-permissions')
  const [provider, setProvider] = useState('local')
  const [candidateId, setCandidateId] = useState('')
  const [steps, setSteps] = useState(8)
  const [allowCloud, setAllowCloud] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [candidates, setCandidates] = useState<Finding[]>(snapshot.findings)
  useEffect(() => {
    if (mode !== 'candidate-review') return
    let active = true
    void repository.getArtifacts().then(value => { if (active) setCandidates(value.findings) }).catch(() => {
      if (active) { setCandidates([]); setMessage('暂时无法读取已有候选，可先执行入口观察，或到“候选与报告”核对数据库。') }
    })
    return () => { active = false }
  }, [repository, mode])
  const refresh = useCallback(async () => {
    if (!repository.getAgent) throw new Error('agent_unavailable')
    const next = await repository.getAgent()
    setData(next)
    setSelectedId(current => current ?? next.activeId ?? next.runs[0]?.id ?? null)
  }, [repository])
  useEffect(() => {
    let active = true
    let loading = false
    const tick = async () => {
      if (!active || loading || !repository.getAgent) return
      loading = true
      try {
        const next = await repository.getAgent()
        if (active) {
          setData(next)
          setSelectedId(current => current ?? next.activeId ?? next.runs[0]?.id ?? null)
        }
      } catch {
        if (active) { setData(null); setMessage('Agent 执行服务不可用；当前任务状态未知，请重启新版控制台后核对。') }
      } finally { loading = false }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [repository])
  const selected = data?.runs.find(x => x.id === selectedId)
  const lab = snapshot.labs.find(x => x.id === labId)
  const matchingCandidates = candidates.filter(f => {
    if (!f.url || !lab?.openUrl) return false
    try { return new URL(f.url).origin === new URL(lab.openUrl).origin }
    catch { return false }
  })
  const resumeReady = snapshot.labs.find(x => x.id === selected?.labId)?.health === 'healthy'
  const ready = snapshot.labs.find(x => x.id === labId)?.health === 'healthy'
  const cloud = provider !== 'local'
  const perform = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true); setMessage('')
    try { await operation(); await refresh(); setMessage(success) }
    catch (error) { setMessage(`操作未完成：${error instanceof Error ? error.message : '执行服务不可用'}。请检查靶场、模型与授权开关。`) }
    finally { setBusy(false) }
  }
  const start = async (resume?: AgentRun) => {
    if (!repository.startAgent) return
    const value: AgentStart = { labId: resume?.labId ?? labId, mode: resume?.mode ?? mode, provider: resume?.provider ?? provider, allowCloud }
    if (resume) { value.resumeId = resume.id; if (resume.candidateId) value.candidateId = resume.candidateId }
    else { value.limits = { max_steps: steps }; if (candidateId && mode === 'candidate-review') value.candidateId = candidateId }
    await perform(async () => {
      const result = await repository.startAgent!(value)
      setSelectedId(result.id)
    }, '任务已提交。每一步会读取真实工具反馈，不会自动确认漏洞或提交补天。')
    setAllowCloud(false)
  }
  return <div className="agent-page">
    <div className="page-heading"><div><h3><Bot size={24} aria-hidden="true" /> 受控 Agent</h3><p>模型选动作 → 程序检查范围与额度 → 真实只读检查 → 反馈与留证。仅限本地靶场。</p></div></div>
    <section className="surface-panel agent-form" aria-label="Agent 任务设置">
      <div className="agent-enable"><label><input type="checkbox" checked={data?.enabled ?? false} disabled={busy || !data} onChange={e => { const enabled = e.target.checked; void perform(() => repository.enableAgent!(enabled), enabled ? '本次已启用受控 Agent，尚未启动任何任务。' : 'Agent 已关闭；若有执行任务，将在安全检查点停止。') }} /> 启用本次受控 Agent</label><span>重启后默认关闭，原有标准检测不受影响。</span></div>
      <div className="agent-fields">
        <label>任务模式<select value={mode} onChange={e => { const next = e.target.value as AgentStart['mode']; setMode(next); setCandidateId(''); if (next === 'api-permissions') setLabId('business-api') }}><option value="api-permissions">API 权限检查（合成账号与对象）</option><option value="candidate-review">候选复核 / 入口观察</option></select></label>
        <label>本地靶场<select value={labId} onChange={e => { setLabId(e.target.value); setCandidateId('') }}>{snapshot.labs.map(lab => <option key={lab.id} value={lab.id} disabled={mode === 'api-permissions' && lab.id !== 'business-api'}>{lab.name} · {lab.health === 'healthy' ? '已就绪' : '未就绪'}</option>)}</select></label>
        <label>决策模型<select value={provider} onChange={e => { setProvider(e.target.value); setAllowCloud(false) }}><option value="local">Ollama（已配置本地模型）</option><option value="deepseek" disabled={!data?.remoteSessionEnabled || !data.cloudAgentAvailable}>DeepSeek（云端）</option><option value="zhipu" disabled={!data?.remoteSessionEnabled || !data.cloudAgentAvailable}>智谱 GLM（云端）</option><option value="openrouter" disabled={!data?.remoteSessionEnabled || !data.cloudAgentAvailable}>OpenRouter（云端）</option></select></label>
        <label>最多执行动作<select value={steps} onChange={e => setSteps(Number(e.target.value))}><option value={2}>2 步 · 轻量观察</option><option value={4}>4 步 · 有限复核</option><option value={8}>8 步 · 标准上限</option></select></label>
        {mode === 'candidate-review' ? <label>关联已有候选（可选，必须属于所选靶场）<select value={candidateId} onChange={e => setCandidateId(e.target.value)}><option value="">不关联，先观察靶场入口</option>{matchingCandidates.map(f => <option key={f.id} value={f.id}>{f.title}</option>)}</select></label> : null}
      </div>
      <p className="agent-hint">先在“本地靶场”启动对应环境。每任务最多 30 次 HTTP 请求、12 次模型调用、15 分钟、20,000 Token；单并发。账号与对象由靶场固定，不允许输入任意命令。</p>
      {!data?.remoteSessionEnabled ? <p className="agent-hint">本次启动禁止云端 AI；本地模型不会失败后自动转用付费 API。</p> : null}
      {!data?.cloudAgentAvailable ? <p className="agent-hint">云端 Agent 尚未完成费用治理与真实调用验收，本阶段保持关闭；原系统设置的人工连接测试不受影响。</p> : null}
      {cloud ? <label className="network-consent"><input type="checkbox" checked={allowCloud} onChange={e => setAllowCloud(e.target.checked)} /> 同意本任务向所选云端模型发送脱敏观察，可能产生费用（以服务商账单为准）</label> : null}
      <div className="inline-actions"><button className="action-button" data-variant="primary" disabled={busy || !data?.enabled || !ready || Boolean(data.activeId) || (cloud && (!data.remoteSessionEnabled || !allowCloud))} onClick={() => void start()}>开始受控任务</button><span>{!ready ? '靶场未就绪，无法启动' : data?.activeId ? '已有任务执行，禁止并行启动' : '启动前不会调用模型或探测目标'}</span></div>
    </section>
    {message ? <div className="inline-notice" role="status"><ShieldCheck size={16} aria-hidden="true" />{message}</div> : null}
    <div className="agent-workspace">
      <section className="surface-panel agent-history" aria-label="Agent 历史任务"><h4>任务与复核队列</h4>{data?.runs.length ? data.runs.map(run => <button key={run.id} className="agent-history-row" aria-pressed={run.id === selectedId} onClick={() => setSelectedId(run.id)}><strong>{run.labId}</strong><span>{states[run.state] ?? run.state}</span><small>{run.createdAt} · {run.provider}</small></button>) : <p>还没有任务。启用后人工启动，执行记录会保存在 D 盘。</p>}</section>
      <section className="surface-panel agent-detail" aria-label="Agent 任务详情">
        {selected ? <><div className="agent-detail-header"><div><h4>{states[selected.state] ?? selected.state}</h4><p>{reasons[selected.reason] ?? selected.reason}</p></div><div className="inline-actions">{selected.id === data?.ownedActiveId ? <button className="action-button" data-variant="danger" disabled={busy || selected.state === 'cancelling'} onClick={() => void perform(() => repository.cancelAgent!(selected.id), '已请求停止；在途模型调用有超时上限，返回后不再执行下一动作。')}><Square size={15} />停止任务</button> : null}{['paused', 'interrupted'].includes(selected.state) ? <button className="action-button" disabled={busy || !resumeReady || !data?.enabled || Boolean(data.activeId) || (selected.provider !== 'local' && (!allowCloud || provider !== selected.provider || !data.remoteSessionEnabled))} onClick={() => void start(selected)}>人工续接</button> : null}{selected.reportId ? <button className="action-button" onClick={() => onOpenReport(selected.reportId)}><FileText size={15} />查看完整报告</button> : null}</div></div>
          <dl className="agent-usage"><div><dt>实际动作</dt><dd>{selected.steps}</dd></div><div><dt>HTTP 请求</dt><dd>{selected.requests}</dd></div><div><dt>模型调用</dt><dd>{selected.modelCalls}</dd></div><div><dt>Token{selected.usageEstimated ? '（含估算）' : ''}</dt><dd>{selected.tokens}</dd></div><div><dt>待复核候选</dt><dd>{selected.candidates}</dd></div></dl>
          <p className="agent-hint">用时 {Math.round(selected.elapsedSeconds)} 秒 · {selected.id} · 每个候选均未确认，不自动提交。</p>
          {selected.resourceCheck?.known && typeof selected.resourceCheck.memory_gb === 'number' ? <p className="agent-hint">资源采样：整机已用内存 {selected.resourceCheck.memory_gb.toFixed(2)} GB{typeof selected.resourceCheck.max_memory_gb === 'number' ? ` / 上限 ${selected.resourceCheck.max_memory_gb} GB` : ''}；CPU {selected.resourceCheck.cpu_percent?.toFixed(1) ?? '未知'}%。释放资源后可人工续接；更换模型或配置后请创建新任务。</p> : null}
          <p className="agent-hint">模型简述不是事实裁决；检测结论以工具观察与人工复核为准。</p>
          <ol className="agent-trace">{selected.trace.map(step => <li key={step.index}><strong>{step.index}. {actions[step.decision?.action ?? ''] ?? '格式校验'} · {step.result === 'ok' ? '完成' : step.result === 'executing' ? '执行中' : step.result === 'rejected' ? '已拒绝' : '失败/未完成'}</strong><p>{step.decision?.reason ?? step.reason}</p>{step.decision ? <small>对象 {step.decision.reference} · 输入证据 {step.decision.evidence.join('、') || '无（初始观察）'} · 输出证据 {step.observationId || '未产生'}</small> : null}{step.observationId ? <p>{selected.observations.find(x => x.id === step.observationId)?.summary}</p> : null}</li>)}</ol>
        </> : <><h4>执行轨迹</h4><p>启动或选择一个历史任务，查看动作、短理由、工具反馈和用量。这里不展示模型的内部推理过程。</p></>}
      </section>
    </div>
  </div>
}

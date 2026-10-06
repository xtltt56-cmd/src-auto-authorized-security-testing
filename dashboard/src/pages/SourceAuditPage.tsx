import { useEffect, useState } from 'react'
import { FileCode2, FileText, Square } from 'lucide-react'
import type { TaskRepository } from '../lib/taskRepository'
import type { AgentSnapshot, SourceAuditApproval } from '../lib/types'

const errorText: Record<string, string> = {
  source_authorization_required: '需要独立目录授权与临时快照同意', source_directory_invalid: '请输入存在的本地目录绝对路径',
  source_directory_too_broad: '不能直接审查整个磁盘或个人主目录，请选择具体项目', source_changed_after_approval: '文件已改变，请重新核对快照',
  source_link_not_allowed: '目录中存在符号链接或目录联接，不允许跨目录读取', source_no_supported_files: '没有可审查的 UTF-8 Python / JS / TS 文件',
  source_total_limit: '项目超过 2000 个文件或 20 MiB 总额度，请选择较小子目录', source_file_limit: '单文件超过 1 MiB 上限',
  source_scanner_unavailable: '固定源码工具不完整，请运行安装脚本', passive_scanner_unavailable: 'Docker 或固定镜像未准备好，请运行安装脚本',
  agent_operation_conflict: '已有任务执行中', source_approval_expired: '快照审批已过期', resource_limit: '资源达到限制', cancelled: 'STOP 已请求停止',
  source_configuration_changed: '工具或规则已变化，请重新核对快照', source_parser_errors: '部分文件未完成分析，不能视为无风险',
}
const stateText: Record<string, string> = { queued: '已排队', running: '执行中', completed: '检查结束 · 待人工复核', 'needs-human': '未完整完成 · 需要人工处理', cancelled: '已停止', cancelling: '正在停止', failed: '失败', interrupted: '已中断 · 不自动续跑' }

export function SourceAuditPage({ repository, onOpenReport }: { repository: TaskRepository; onOpenReport: (id: string) => void }) {
  const [directory, setDirectory] = useState('')
  const [python, setPython] = useState(true)
  const [javascript, setJavascript] = useState(true)
  const [readConsent, setReadConsent] = useState(false)
  const [snapshotConsent, setSnapshotConsent] = useState(false)
  const [confirmStart, setConfirmStart] = useState(false)
  const [approval, setApproval] = useState<SourceAuditApproval | null>(null)
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const invalidate = () => { setApproval(null); setConfirmStart(false) }
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setNotice('')
    try { await operation() }
    catch (error) { const code = error instanceof Error ? error.message : ''; setNotice(`操作未完成：${errorText[code] ?? '执行器不可用或配置无效'}（${code}）`) }
    finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true, refreshing = false
    const refresh = async () => {
      if (!active || refreshing) return
      refreshing = true
      try {
        if (!repository.getAgent) throw new Error('unavailable')
        const next = await repository.getAgent()
        if (active) { setSnapshot(next); setSelectedId(current => current ?? next.runs.find(x => x.targetType === 'source_audit')?.id ?? null) }
      } catch { if (active) { setSnapshot(null); setNotice('无法读取真实任务状态，请重新启动新版控制台。') } }
      finally { refreshing = false }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [repository])
  const languages = [...(python ? ['python'] : []), ...(javascript ? ['javascript'] : [])]
  const ready = Boolean(snapshot && !snapshot.activeId && !busy && directory.trim() && languages.length && readConsent && snapshotConsent && repository.previewSourceAudit)
  const runs = snapshot?.runs.filter(x => x.targetType === 'source_audit') ?? []
  const selected = runs.find(x => x.id === selectedId)
  return <div className="agent-page source-audit-page">
    <div className="page-heading"><div><h3><FileCode2 size={24} /> 源码安全审查</h3><p>独立目录授权 → 核对文件快照 → 断网静态检查 → 人工复核</p></div></div>
    <section className="surface-panel agent-form" aria-label="源码审查范围">
      <p className="agent-hint">这是独立于网站范围的文件授权。不运行源码、启动脚本、构建、项目依赖安装或 Git 钩子；不调用云端模型，不上传代码。</p>
      <label className="form-field">源码目录绝对路径<input placeholder="D:\你的项目\src" value={directory} autoComplete="off" onChange={e => { setDirectory(e.target.value); setReadConsent(false); setSnapshotConsent(false); invalidate() }} /></label>
      <div className="inline-actions"><label><input type="checkbox" checked={python} onChange={e => { setPython(e.target.checked); invalidate() }} /> Python · Bandit</label><label><input type="checkbox" checked={javascript} onChange={e => { setJavascript(e.target.checked); invalidate() }} /> JavaScript / TypeScript · Semgrep</label></div>
      <p className="agent-hint">首版：最多 2000 个文件、20 MiB 总内容、单文件 1 MiB、任务 300 秒。只支持 UTF-8；自动排除 .git、.env、密钥名称、依赖、运行数据、模型与构建产物，不跟随联接或符号链接。超额不会伪装成功。</p>
      <label className="network-consent"><input type="checkbox" checked={readConsent} onChange={e => { setReadConsent(e.target.checked); invalidate() }} /> 确认拥有此目录的源码审查授权；允许读取批准语言文件以计算摘要与分析。</label>
      <label className="network-consent"><input type="checkbox" checked={snapshotConsent} onChange={e => { setSnapshotConsent(e.target.checked); invalidate() }} /> 允许将批准文件临时复制到 D 盘项目任务目录，仅供断网扫描；结束后删除快照，报告不保存原始代码。</label>
      <div className="inline-actions"><button className="action-button" data-variant="primary" disabled={!ready} onClick={() => void perform(async () => { invalidate(); setApproval(await repository.previewSourceAudit!({ directory: directory.trim(), languages, confirmRead: readConsent, confirmSnapshot: snapshotConsent })) })}>核对源码快照</button><span>此步会读取批准文件生成摘要；不执行扫描、不调用 AI。</span></div>
      {approval ? <div className="local-approval"><h4>文件审批快照</h4><p>{approval.directory} · {approval.files} 个文件 · {(approval.bytes / 1024).toFixed(1)} KiB</p><details><summary>范围摘要与排除计数</summary><p>快照摘要：{approval.digest}</p><p>有效至：{approval.expiresAt}</p><pre>{JSON.stringify(approval.excluded, null, 2)}</pre></details><p>源文件或工具配置改变后，需要重新审批；不会自动续跑。</p><label className="network-consent"><input type="checkbox" checked={confirmStart} onChange={e => setConfirmStart(e.target.checked)} /> 确认按批准快照启动离线审查；所有发现仅为静态风险候选。</label><button className="action-button" data-variant="primary" disabled={!ready || !confirmStart || !repository.startSourceAudit} onClick={() => void perform(async () => { const result = await repository.startSourceAudit!({ approvalId: approval.approvalId, confirmStart: true }); setSelectedId(result.id); invalidate(); setReadConsent(false); setSnapshotConsent(false); setNotice('已交给真实静态分析器，请查看任务、证据和报告。') })}>开始源码审查</button></div> : null}
    </section>
    {notice ? <div className="inline-notice" role="status">{notice}</div> : null}
    <div className="agent-workspace">
      <section className="surface-panel agent-history"><h4>源码任务记录</h4>{runs.map(row => <button className="agent-history-row" aria-pressed={row.id === selectedId} key={row.id} onClick={() => setSelectedId(row.id)}><strong>{row.directory}</strong><span>{stateText[row.state] ?? row.state}</span><small>{row.createdAt} · 无 AI</small></button>)}{!runs.length ? <p>尚无记录；打开页面不会自动审查文件。</p> : null}</section>
      <section className="surface-panel agent-detail" aria-label="源码任务详情">{selected ? <><div className="agent-detail-header"><div><h4>{stateText[selected.state] ?? selected.state}</h4><p>{selected.reason === 'source_snapshot_and_scanner' ? '正在生成批准快照并运行断网扫描器' : selected.reason === 'source_audit_completed' ? '批准源码已真实静态分析' : selected.reason}</p></div><div className="inline-actions">{selected.id === snapshot?.ownedActiveId ? <button className="action-button" disabled={busy} onClick={() => void perform(async () => { await repository.cancelAgent!(selected.id) })}><Square size={15} />停止源码审查</button> : null}{selected.reportId ? <button className="action-button" onClick={() => onOpenReport(selected.reportId)}><FileText size={15} />查看完整源码报告</button> : null}</div></div><p>候选 {selected.candidates} 条 · 实际耗时 {selected.elapsedSeconds} 秒 · 模型调用 {selected.modelCalls} 次 · HTTP 请求 {selected.requests} 次</p><div className="table-scroll"><table className="data-table"><thead><tr><th>扫描器 / 规则</th><th>文件与行号</th><th>静态风险候选</th></tr></thead><tbody>{selected.sourceAudit?.findings.map((x, i) => <tr key={i}><td>{x.scanner} · {x.rule_id}</td><td><code>{x.path}:{x.line}</code></td><td>{x.title} · 未确认</td></tr>)}</tbody></table></div><p className="agent-hint">零候选不表示完全安全；未分析文件、语法错误和失败原因见完整报告。不会自动修改代码或提交补天。</p></> : <p>选择一个任务查看实际文件覆盖、行号与关联报告。</p>}</section>
    </div>
  </div>
}

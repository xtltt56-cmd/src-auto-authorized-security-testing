import { useEffect, useState } from 'react'
import { CheckCircle2, FileCode2, FileText, ShieldCheck, Square } from 'lucide-react'
import type { TaskRepository } from '../lib/taskRepository'
import type { AgentSnapshot, SourceAuditApproval } from '../lib/types'

const errorText: Record<string, string> = {
  source_authorization_required: '请确认目录授权和临时快照许可', source_directory_invalid: '请输入存在的本地目录绝对路径',
  source_directory_too_broad: '请选择具体项目，不能直接审查磁盘或个人主目录', source_changed_after_approval: '文件已改变，请重新核对快照',
  source_link_not_allowed: '不允许跨越符号链接或目录联接', source_no_supported_files: '没有可审查的 UTF-8 Python / JS / TS 文件',
  source_total_limit: '超过 2000 个文件或 20 MiB，请选择较小子目录', source_file_limit: '单文件超过 1 MiB',
  source_scanner_unavailable: '固定源码工具不完整，请运行安装脚本', passive_scanner_unavailable: 'Docker 或固定镜像未就绪，请在系统设置检查依赖',
  agent_operation_conflict: '已有任务执行中，请等待或停止原任务', source_approval_expired: '审批已过期，请重新核对', resource_limit: 'CPU 或内存达到限制',
  cancelled: '已收到停止请求', source_configuration_changed: '工具或模型配置已变化，请重新核对', blocked_disk: '磁盘空间不足或无法测量',
  task_timeout: '达到 300 秒限制，已停止；请缩小范围后重试', source_parser_errors: '部分文件未分析，详情见未覆盖清单',
  source_cloud_review_incomplete: '静态结果已保留；部分云端审阅未完成，需要人工复核', remote_ai_disabled_for_session: '本次启动未允许云端 AI',
  cloud_agent_not_validated: 'DeepSeek 配置或费用策略尚未就绪', manual_execution_confirmation_required: '需要单独确认本次启动',
}
const stateText: Record<string, string> = { queued: '已排队', running: '执行中', completed: '检查完成 · 待人工复核', 'needs-human': '部分完成 · 需要处理', cancelled: '已停止', cancelling: '正在停止', failed: '失败', interrupted: '已中断 · 不自动续跑' }
const exclusions: Record<string, string> = { excluded_directory: '依赖 / 产物 / 隐藏目录 / 联接', runtime_directory: '项目根层运行数据目录', excluded_file: '非批准语言或敏感文件名', bundled_javascript: '压缩第三方 JS（不做依赖 CVE 审查）', unsafe_file: '不安全的文件路径', unsupported_encoding: '不是 UTF-8 编码' }
const dispositions: Record<string, string> = { candidate: '仍为候选', manual_review: '人工审阅', needs_manual_validation: '需要人工验证', false_positive: '模型倾向误报 · 未经人工确认' }

export function SourceAuditPage({ repository, onOpenReport }: { repository: TaskRepository; onOpenReport: (id: string) => void }) {
  const [directory, setDirectory] = useState('')
  const [python, setPython] = useState(true)
  const [javascript, setJavascript] = useState(true)
  const [readConsent, setReadConsent] = useState(false)
  const [snapshotConsent, setSnapshotConsent] = useState(false)
  const [confirmStart, setConfirmStart] = useState(false)
  const [allowCloud, setAllowCloud] = useState(false)
  const [approval, setApproval] = useState<SourceAuditApproval | null>(null)
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const invalidate = () => { setApproval(null); setConfirmStart(false); setAllowCloud(false) }
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setNotice('')
    try { await operation() }
    catch (error) { const code = error instanceof Error ? error.message : ''; setNotice(`操作未完成：${errorText[code] ?? '执行器不可用，请核对依赖和配置'}（${code}）`) }
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
      } catch { if (active) { setSnapshot(null); setNotice('无法读取真实任务状态，请恢复本地执行服务。') } }
      finally { refreshing = false }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [repository])
  const languages = [...(python ? ['python'] : []), ...(javascript ? ['javascript'] : [])]
  const ready = Boolean(snapshot && !snapshot.activeId && !busy && directory.trim() && languages.length && readConsent && snapshotConsent && repository.previewSourceAudit)
  const cloudReady = Boolean(snapshot?.remoteSessionEnabled && snapshot.cloudAgentAvailable)
  const runs = snapshot?.runs.filter(x => x.targetType === 'source_audit') ?? []
  const selected = runs.find(x => x.id === selectedId)
  const audit = selected?.sourceAudit
  const cloud = audit?.cloudReview
  const preview = async () => { invalidate(); setApproval(await repository.previewSourceAudit!({ directory: directory.trim(), languages, confirmRead: readConsent, confirmSnapshot: snapshotConsent })) }
  const start = async () => {
    if (!approval) return
    const result = await repository.startSourceAudit!({ approvalId: approval.approvalId, confirmStart: true, allowCloud: allowCloud && cloudReady })
    setSelectedId(result.id); invalidate(); setReadConsent(false); setSnapshotConsent(false)
    setNotice('已交给真实扫描器。可在下方查看任务阶段、候选与完整报告。')
    if (repository.getAgent) {
      try { setSnapshot(await repository.getAgent()) }
      catch { setSnapshot(null); setNotice('任务已提交，但状态连接暂时中断；请恢复连接后核对，不要重复启动。') }
    }
  }
  return <div className="agent-page source-audit-page">
    <div className="page-heading"><div><h3><FileCode2 size={24} /> 源码安全审查</h3><p>读取批准源码，不执行项目；从真实静态结果出发，保留人工最终确认。</p></div><span className="source-safety"><ShieldCheck size={17} /> 默认断网 · 不上传源码</span></div>
    <ol className="source-steps" aria-label="源码审查流程"><li data-active={!approval}><span>01</span>选择目录与授权</li><li data-active={Boolean(approval)}><span>02</span>核对文件 · 手动启动</li><li><span>03</span>查看结果与报告</li></ol>
    <section className="surface-panel agent-form" aria-label="源码审查范围">
      <div className="source-form-grid"><div>
        <h4>1. 选择源码</h4>
        <label className="form-field">源码目录绝对路径<input placeholder="例如 D:\量化交易\src" value={directory} autoComplete="off" disabled={busy} onChange={e => { setDirectory(e.target.value); setReadConsent(false); setSnapshotConsent(false); invalidate() }} /></label>
        <p className="agent-hint">粘贴项目的 src 目录；若要检查脚本，再单独选择 scripts。不是网站网址，也不是启动命令。</p>
        <div className="source-languages"><label><input type="checkbox" checked={python} disabled={busy} onChange={e => { setPython(e.target.checked); invalidate() }} /> Python <small>Bandit</small></label><label><input type="checkbox" checked={javascript} disabled={busy} onChange={e => { setJavascript(e.target.checked); invalidate() }} /> JavaScript / TypeScript <small>Semgrep</small></label></div>
        <label className="network-consent"><input type="checkbox" checked={readConsent} disabled={busy} onChange={e => { setReadConsent(e.target.checked); invalidate() }} /> 确认拥有此目录的源码审查授权；允许读取批准语言文件以计算摘要与分析。</label>
        <label className="network-consent"><input type="checkbox" checked={snapshotConsent} disabled={busy} onChange={e => { setSnapshotConsent(e.target.checked); invalidate() }} /> 允许将批准文件临时复制到 D 盘项目任务目录，仅供断网扫描；结束后删除快照，报告不保存原始代码。</label>
        <button className="action-button" data-variant="primary" disabled={!ready} onClick={() => void perform(preview)}>核对源码快照</button>
        <p className="agent-hint" role="status">{busy ? '正在处理请求，请稍候…' : snapshot?.activeId ? '已有任务在执行，请先等待或停止。' : '核对不会执行扫描或调用 AI。勾选两项许可后即可继续。'}</p>
      </div><aside className="source-guide"><h4><ShieldCheck size={18} /> 只读审查边界</h4><p>不运行源码、启动脚本、构建、项目依赖安装或 Git 钩子。</p><dl><div><dt>文件上限</dt><dd>2000 个 · 单文件 1 MiB</dd></div><div><dt>内容与时间</dt><dd>20 MiB · 300 秒</dd></div><div><dt>支持编码</dt><dd>UTF-8 / UTF-8 BOM</dd></div></dl><p>敏感文件名、依赖、隐藏目录、产物及 *.min.js 自动排除。业务源码中的 data / runtime 不再按名称误排除。</p><p>这里只发现静态风险候选；依赖 CVE、运行时业务逻辑和可利用性需要其他检查。</p></aside></div>
      {approval ? <div className="source-approval"><h4><CheckCircle2 size={18} /> 2. 核对范围并启动</h4><div className="source-approved-path">{approval.directory}</div><div className="source-approval-meta"><span><strong>{approval.files}</strong> 批准文件</span><span><strong>{(approval.bytes / 1024).toFixed(1)}</strong> KiB 内容</span><span><strong>{Object.values(approval.excluded).reduce((a, b) => a + b, 0)}</strong> 排除条目 / 目录</span></div>
        <div className="source-scope-details"><details><summary>批准文件清单</summary><ul>{approval.fileList?.map(path => <li key={path}><code>{path}</code></li>) ?? <li>旧版执行服务未提供清单，请升级服务。</li>}</ul></details><details><summary>排除项与原因</summary><ul>{approval.exclusions?.map((x, i) => <li key={i}><code>{x.path}</code> · {exclusions[x.reason] ?? x.reason}</li>)}</ul>{approval.exclusionsTruncated ? <p>仅列出前 500 项，目录排除包含子树。</p> : null}<p>排除计数：{JSON.stringify(approval.excluded)}</p></details><details><summary>范围摘要与有效期</summary><p>快照摘要：{approval.digest}</p><p>有效至：{approval.expiresAt}</p></details></div>
        <div className="source-cloud-option"><strong>可选：DeepSeek 摘要辅助研判</strong><label className="network-consent"><input type="checkbox" checked={allowCloud && cloudReady} disabled={!cloudReady || busy} onChange={e => { setAllowCloud(e.target.checked); setConfirmStart(false) }} /> 同意本任务将匿名规则、候选数量发给 DeepSeek，最多 4 次，可能产生费用；不发送源码、目录、文件名或密钥。</label><p>{cloudReady ? '仅给复核建议，不证明漏洞或误报；不勾选就是纯离线扫描。' : '本次启动未允许云端，或 DeepSeek 配置未就绪；保存密钥不会解除此限制。'}</p></div>
        <label className="network-consent"><input type="checkbox" checked={confirmStart} disabled={busy} onChange={e => setConfirmStart(e.target.checked)} /> 确认按批准快照启动审查；所有发现仅为静态风险候选，源码或配置改变后重新审批。</label><button className="action-button" data-variant="primary" disabled={!ready || !confirmStart || !repository.startSourceAudit} onClick={() => void perform(start)}>开始源码审查</button>
      </div> : null}
    </section>
    {notice ? <div className="inline-notice" role="status">{notice}</div> : null}
    <div className="agent-workspace">
      <section className="surface-panel agent-history"><h4>任务记录 <small>({runs.length})</small></h4>{runs.map(row => <button className="agent-history-row" aria-pressed={row.id === selectedId} key={row.id} onClick={() => setSelectedId(row.id)}><strong>{row.directory}</strong><span>{stateText[row.state] ?? row.state}</span><small>{row.createdAt} · {row.provider === 'deepseek' ? '云端摘要辅助' : '纯离线'}</small></button>)}{!runs.length ? <p className="agent-hint">尚无记录。打开页面不会自动读取源码或启动任务。</p> : null}</section>
      <section className="surface-panel agent-detail" aria-label="源码任务详情">{selected ? <><div className="agent-detail-header"><div><h4>{stateText[selected.state] ?? selected.state}</h4><p>{selected.reason === 'source_snapshot_and_scanner' ? '正在生成批准快照并运行断网扫描器' : selected.reason === 'source_cloud_review' ? '静态结果已生成，正在调用 DeepSeek 审阅匿名摘要' : selected.reason === 'source_audit_completed' ? '批准范围已完成真实静态分析' : errorText[selected.reason] ?? selected.reason}</p></div><div className="inline-actions">{selected.id === snapshot?.ownedActiveId ? <button className="action-button" disabled={busy || selected.state === 'cancelling'} onClick={() => void perform(async () => { await repository.cancelAgent!(selected.id); setNotice('已请求停止；在途云端调用结束后不会执行下一步。') })}><Square size={15} />停止源码审查</button> : null}{selected.reportId ? <button className="action-button" onClick={() => onOpenReport(selected.reportId)}><FileText size={15} />查看完整源码报告</button> : null}</div></div>
        <dl className="agent-usage"><div><dt>文件覆盖</dt><dd>{audit ? `${audit.scannedFiles ?? '?'} / ${audit.sourceFiles ?? '?'}` : ['queued', 'running', 'cancelling'].includes(selected.state) ? '分析中' : '未完成分析'}</dd></div><div><dt>风险候选</dt><dd>{selected.candidates}</dd></div><div><dt>实际耗时（秒）</dt><dd>{selected.elapsedSeconds}</dd></div><div><dt>模型调用 / 目标请求</dt><dd>{selected.modelCalls} / {selected.requests}</dd></div></dl>
        {!audit && selected.sourceProgress ? <p className="agent-hint">批准快照：{selected.sourceProgress.prepared} / {selected.sourceProgress.total} 个文件已复制；扫描器结束后显示实际分析覆盖，不使用模拟进度。</p> : null}
        {audit?.unprocessedFiles?.length ? <details className="source-warning" open><summary>未分析 {audit.unprocessedFiles.length} 个批准文件 · 不能算完整检查</summary><ul>{audit.unprocessedDetails?.map(x => <li key={x.path}><code>{x.path}</code> · {x.scanner} · {x.reason}</li>)}</ul></details> : null}
        {cloud ? <section className="source-cloud-results"><h4>DeepSeek 辅助研判</h4><p>已审阅 {cloud.reviewedCandidates} 条候选的规则摘要 · 未审阅 {cloud.unreviewedCandidates} 条 · 保守费用预留 ¥{cloud.reservedCny.toFixed(4)}{cloud.usageEstimated ? '（部分用量未知）' : ''}</p>{cloud.groups.map(group => <article key={group.rule}><strong>{group.rule} · {group.candidates} 条 · {dispositions[group.disposition] ?? group.disposition}</strong><p>{group.reason}</p><ul>{group.suggested_checks.map((check, i) => <li key={i}>{check}</li>)}</ul></article>)}{cloud.errors.map(x => <p key={x.rule} className="source-warning">{x.rule}：云端审阅未成功；静态候选和报告已保留。</p>)}</section> : null}
        <h4>静态风险候选 <small>未确认 · 不自动提交</small></h4><div className="table-scroll"><table className="data-table"><thead><tr><th>扫描器 / 规则</th><th>文件与行号</th><th>候选说明</th></tr></thead><tbody>{audit?.findings.map((x, i) => <tr key={i}><td>{x.scanner} · {x.rule_id}</td><td><code>{x.path}:{x.line}</code></td><td>{x.title}</td></tr>)}</tbody></table></div>{audit && !audit.findings.length ? <p className="agent-hint">本轮没有静态风险候选；不代表整个项目完全安全。</p> : null}<p className="agent-hint">原始源码不进入报告。所有云端意见只是建议；点击完整报告查看覆盖、排除项、规则与费用记录。</p>
      </> : <div className="source-empty"><FileCode2 size={32} /><h4>等待一次真实审查</h4><p>先选择目录并核对范围，手动启动后将在这里显示真实扫描结果。</p></div>}</section>
    </div>
  </div>
}

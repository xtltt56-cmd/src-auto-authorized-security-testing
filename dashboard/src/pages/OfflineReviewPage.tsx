import { useCallback, useEffect, useState } from 'react'
import type { TaskRepository } from '../lib/taskRepository'
import type { ReviewEntry } from '../lib/types'

const labels: Record<string, string> = { candidate_only: '草稿待确认', missing_plan: '缺少执行计划', missing_scope: '缺少范围文件', ready: '已发现范围及计划' }

export function OfflineReviewPage({ repository }: { repository: TaskRepository }) {
  const [entries, setEntries] = useState<ReviewEntry[]>([])
  const [message, setMessage] = useState('')
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(true)
  const load = useCallback(async () => {
    try { setEntries(await repository.reviewTargets()); setMessage('离线检查完成，未访问目标网站。') }
    catch { setMessage('无法读取范围，请检查本地服务和 config/targets 目录。') }
  }, [repository])
  const refresh = async () => { setBusy(true); await load(); setBusy(false) }
  // oxlint-disable-next-line react/set-state-in-effect -- loading data is an external repository synchronization.
  useEffect(() => { void load().finally(() => setBusy(false)) }, [load])
  return <section className="surface-panel panel-body">
    <h3>离线审阅范围</h3>
    <p>从 config/targets 顶层统一读取项目，无需逐级进入文件夹。候选草稿不会自动变成已确认授权。</p>
    <label>筛选项目或文件夹 <input aria-label="筛选审阅项目" value={filter} onChange={e => setFilter(e.target.value)} /></label>
    <button className="action-button" onClick={() => void refresh()} disabled={busy}>{busy ? '正在检查…' : '重新检查本地范围'}</button>
    <p role="status">{message}</p>
    {entries.length === 0 && <p>暂无范围文件。请先在“目标与授权”保存草稿。</p>}
    {entries.filter(e => e.name.toLowerCase().includes(filter.toLowerCase())).map(entry => <article className="surface-panel panel-body" key={entry.name}>
      <h4>{entry.name}</h4><p>{labels[entry.status] ?? entry.status}</p>
      {entry.review ? <><p>审阅状态：{entry.review.status}</p><p>原因：{entry.review.reason}；目标数量：{entry.review.targetCount}</p></> : <p>请人工核对范围，并准备 live_plan.yaml；当前条目不具备执行授权。</p>}
    </article>)}
  </section>
}

import { Play, RefreshCw, ShieldCheck, Square } from 'lucide-react'
import { useState } from 'react'
import type { DashboardSnapshot } from '../lib/types'
import { LabMatrix } from '../components/LabMatrix'
import type { NavKey } from '../components/AppShell'

type LabsPageProps = {
  snapshot: DashboardSnapshot
  onOpenTask: (taskId: string) => void
  onNavigate: (key: NavKey) => void
  onAction: (labId: string, action: 'start' | 'stop' | 'reset') => Promise<void>
  onBatchAction: (action: 'start' | 'stop') => Promise<void>
}

export function LabsPage({ snapshot, onOpenTask, onNavigate, onAction, onBatchAction }: LabsPageProps) {
  const [pendingLabId, setPendingLabId] = useState<string | null>(null)
  const [pendingBatch, setPendingBatch] = useState<'start' | 'stop' | null>(null)
  const [notice, setNotice] = useState('')
  const runAction = async (labId: string, action: 'start' | 'stop' | 'reset') => {
    setPendingLabId(labId)
    setNotice('')
    try { await onAction(labId, action); setNotice(`${labId} 操作已提交，状态会自动刷新。`) }
    catch { setNotice('操作未提交：本地执行服务不可用或该靶场已有操作正在进行。') }
    finally { setPendingLabId(null) }
  }
  const runBatch = async (action: 'start' | 'stop') => {
    setPendingBatch(action)
    setNotice('')
    try { await onBatchAction(action); setNotice(action === 'start' ? '启动全部操作已提交，页面会显示逐个就绪状态。' : '停止全部操作已提交。') }
    catch { setNotice('批量操作未提交：请检查本地执行服务和 Docker 状态。') }
    finally { setPendingBatch(null) }
  }
  return (
    <>
      <div className="page-heading">
        <div><h3>本地靶场</h3><p>五个固定回环服务用于准备练习环境。此页只管理容器生命周期和健康状态，不会伪装成已完成漏洞扫描。</p></div>
        <div className="inline-actions"><span className="local-only-label"><ShieldCheck size={14} aria-hidden="true" /> 只访问 127.0.0.1</span><button className="action-button" type="button" onClick={() => onNavigate('overview')}><RefreshCw size={15} aria-hidden="true" /> 返回总览</button></div>
      </div>
      <div className="lab-banner surface-panel"><div><strong>按需启动本地靶场</strong><p>启动、停止和重置只作用于固定回环容器；“已就绪”仅表示环境可访问，不代表已发现漏洞。页面每 2 秒刷新状态。</p></div><div className="inline-actions"><button className="action-button" data-variant="primary" type="button" onClick={() => void runBatch('start')} disabled={pendingBatch !== null}><Play size={16} aria-hidden="true" /> {pendingBatch === 'start' ? '正在提交…' : '启动全部靶场'}</button><button className="action-button" data-variant="danger" type="button" onClick={() => void runBatch('stop')} disabled={pendingBatch !== null}><Square size={15} aria-hidden="true" /> {pendingBatch === 'stop' ? '正在提交…' : '停止全部靶场'}</button><button className="action-button" type="button" onClick={() => onOpenTask('run-local-001')}><RefreshCw size={16} aria-hidden="true" /> 打开环境任务</button></div></div>
      {notice ? <div className="inline-notice" role="status"><ShieldCheck size={15} aria-hidden="true" /> {notice}</div> : null}
      <LabMatrix labs={snapshot.labs} onOpenLabTask={onOpenTask} onAction={runAction} pendingLabId={pendingLabId} />
    </>
  )
}

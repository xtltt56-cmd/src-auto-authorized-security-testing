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
  onDetectionAction: (labId: string, action: 'start' | 'stop') => Promise<void>
  onBatchAction: (action: 'start' | 'stop') => Promise<void>
  onStartDocker: () => Promise<void>
}

export function LabsPage({ snapshot, onOpenTask, onNavigate, onAction, onDetectionAction, onBatchAction, onStartDocker }: LabsPageProps) {
  const [pendingLabId, setPendingLabId] = useState<string | null>(null)
  const [pendingDetectionLabId, setPendingDetectionLabId] = useState<string | null>(null)
  const [pendingBatch, setPendingBatch] = useState<'start' | 'stop' | null>(null)
  const [notice, setNotice] = useState('')
  const dockerReady = snapshot.dependency?.dockerReady !== false
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
  const runDetection = async (labId: string, action: 'start' | 'stop') => {
    setPendingDetectionLabId(labId)
    setNotice('')
    try {
      await onDetectionAction(labId, action)
      setNotice(action === 'start' ? `${labId} 检测任务已提交；进度和候选会自动刷新。` : `${labId} 已请求在安全检查点停止检测。`)
    } catch {
      setNotice(action === 'start' ? '检测未启动：请确认 Docker 和靶场均已就绪，且没有其他操作正在进行。' : '停止请求未提交：当前可能没有正在运行的检测。')
    } finally {
      setPendingDetectionLabId(null)
    }
  }
  const startDocker = async () => {
    setPendingBatch('start')
    setNotice('')
    try { await onStartDocker(); setNotice('已请求启动 Docker Desktop；引擎就绪后状态会自动刷新，通常需要几十秒。') }
    catch { setNotice('无法自动启动 Docker Desktop，请从 Windows 开始菜单手动启动。') }
    finally { setPendingBatch(null) }
  }
  return (
    <>
      <div className="page-heading">
        <div><h3>本地靶场</h3><p>先启动固定回环靶场，再由人工点击“开始检测”。检测会真实访问本机端口、保存候选并生成关联报告。</p></div>
        <div className="inline-actions"><span className="local-only-label"><ShieldCheck size={14} aria-hidden="true" /> 只访问 127.0.0.1</span><button className="action-button" type="button" onClick={() => onNavigate('overview')}><RefreshCw size={15} aria-hidden="true" /> 返回总览</button></div>
      </div>
      <div className="lab-banner surface-panel"><div><strong>{dockerReady ? '启动环境后再执行检测' : 'Docker Desktop 尚未就绪'}</strong><p>{dockerReady ? '“已就绪”只表示容器可访问；只有人工点击检测按钮后，系统才会执行回环探测、表面发现、候选检查、入库和报告生成。页面每 2 秒刷新状态。' : `${snapshot.dependency?.message || '请先启动 Docker Desktop'}。这不是漏洞或扫描失败，容器引擎就绪后即可启动靶场。`}</p></div><div className="inline-actions">{!dockerReady ? <button className="action-button" data-variant="primary" type="button" onClick={() => void startDocker()} disabled={pendingBatch !== null}><Play size={16} aria-hidden="true" /> {pendingBatch ? '正在请求…' : '启动 Docker Desktop'}</button> : <><button className="action-button" data-variant="primary" type="button" onClick={() => void runBatch('start')} disabled={pendingBatch !== null}><Play size={16} aria-hidden="true" /> {pendingBatch === 'start' ? '正在提交…' : '启动全部靶场'}</button><button className="action-button" data-variant="danger" type="button" onClick={() => void runBatch('stop')} disabled={pendingBatch !== null}><Square size={15} aria-hidden="true" /> {pendingBatch === 'stop' ? '正在提交…' : '停止全部靶场'}</button></>}<button className="action-button" type="button" onClick={() => onOpenTask('run-local-001')}><RefreshCw size={16} aria-hidden="true" /> 打开环境任务</button></div></div>
      {notice ? <div className="inline-notice" role="status"><ShieldCheck size={15} aria-hidden="true" /> {notice}</div> : null}
      <LabMatrix labs={snapshot.labs} onOpenLabTask={onOpenTask} onAction={runAction} onDetectionAction={runDetection} pendingLabId={pendingLabId} pendingDetectionLabId={pendingDetectionLabId} />
    </>
  )
}

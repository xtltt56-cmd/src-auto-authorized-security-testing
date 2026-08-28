import { ArrowLeft, Clock3, HeartPulse, Play, RefreshCw, ShieldCheck, Square } from 'lucide-react'
import { useCallback, useState } from 'react'
import type { TaskRepository } from '../lib/taskRepository'
import type { LabStatus, TaskEvent, TaskSummary } from '../lib/types'
import { ActionBar } from '../components/ActionBar'
import { EventTimeline } from '../components/EventTimeline'
import { MetricStrip } from '../components/MetricStrip'
import { ProgressBar } from '../components/ProgressBar'
import { StageRail, type StageItem } from '../components/StageRail'
import { StatusBadge } from '../components/StatusBadge'

type TaskDetailPageProps = {
  task: TaskSummary
  lab?: LabStatus | null
  events: TaskEvent[]
  repository: TaskRepository
  onBack: () => void
  onOpenReport: () => void
}

const stageNames = ['策略检查', '依赖检查', '健康检查', '入口发现', '受控验证', 'API 对象对比', '候选研判', '报告生成']

const healthLabels: Record<LabStatus['health'], string> = {
  healthy: '就绪',
  starting: '启动中',
  stopped: '已停止',
  blocked: '受阻',
}

const stagesFor = (task: TaskSummary): StageItem[] => {
  const namedIndex = stageNames.indexOf(task.stage)
  const currentIndex = namedIndex >= 0 ? namedIndex : Math.min(stageNames.length - 1, Math.max(0, Math.floor(task.progress / 16)))
  return stageNames.map((label, index) => ({
    id: label,
    label,
    state: task.state === 'blocked' || task.state === 'failed' ? (index === currentIndex ? 'blocked' : index < currentIndex ? 'completed' : 'idle') : index < currentIndex || task.state === 'completed' ? 'completed' : index === currentIndex ? 'running' : 'idle',
    detail: index === currentIndex ? task.stage : undefined,
  }))
}

export function TaskDetailPage({ task: initialTask, lab = null, events: initialEvents, repository, onBack, onOpenReport }: TaskDetailPageProps) {
  const [task, setTask] = useState(initialTask)
  const [events, setEvents] = useState(initialEvents)
  const [notice, setNotice] = useState('')

  const refresh = useCallback(async (message: string) => {
    const [nextTask, nextEvents] = await Promise.all([repository.getTask(initialTask.id), repository.getEvents(initialTask.id)])
    setTask(nextTask)
    setEvents(nextEvents)
    setNotice(message)
  }, [initialTask.id, repository])

  const exportEvents = () => {
    const payload = JSON.stringify(events, null, 2)
    const blob = new Blob([payload], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${task.id}-events-redacted.json`
    link.click()
    URL.revokeObjectURL(url)
    setNotice('已导出脱敏事件文件')
  }

  const openReport = () => {
    if (lab && !lab.reportId) {
      setNotice('当前靶场尚未生成报告')
      return
    }
    onOpenReport()
  }

  const runLabAction = async (action: 'start' | 'stop' | 'reset') => {
    if (!lab) return
    try {
      if (action === 'start') await repository.startLab(lab.id)
      else if (action === 'stop') await repository.stopLab(lab.id)
      else await repository.resetLab(lab.id)
      await refresh(action === 'start' ? '靶场启动操作已提交' : action === 'stop' ? '靶场停止操作已提交' : '靶场重置操作已提交')
    } catch {
      setNotice('操作未提交：请检查本地执行服务和 Docker 状态。')
    }
  }

  const counters = [
    { label: '入口', value: task.counters.endpoints },
    { label: 'API', value: task.counters.api },
    { label: '候选', value: task.counters.candidates },
    { label: '阻止', value: task.counters.blocked },
  ]

  return (
    <>
      <div className="page-heading task-detail-heading">
        <div><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" /> 返回靶场列表</button><h3>{task.name}</h3><p>任务 ID：{task.id} · 事件和消息均已脱敏</p></div>
        <div className="task-meta"><StatusBadge state={task.state} /><span><Clock3 size={15} aria-hidden="true" /> {task.elapsedSeconds}s</span></div>
      </div>
      {notice ? <div className="inline-notice" role="status"><ShieldCheck size={15} aria-hidden="true" /> {notice}</div> : null}
      <div className="detail-overview surface-panel">
        <div className="panel-body"><div className="detail-overview-top"><ProgressBar value={task.progress} label="总体进度" /><span className="network-note"><HeartPulse size={14} aria-hidden="true" /> 网络接触：仅回环</span></div><MetricStrip items={counters} /></div>
      </div>
      <div className="task-detail-grid">
        <aside className="surface-panel stage-panel"><div className="panel-header"><div><h4>阶段轨道</h4><p>当前阶段：{task.stage}</p></div></div><div className="panel-body"><StageRail stages={stagesFor(task)} /></div></aside>
        <EventTimeline events={events} />
        <aside className="surface-panel detail-aside"><div className="panel-header"><div><h4>安全摘要</h4><p>运行策略和目标边界</p></div></div><div className="panel-body summary-list"><div><span>执行模式</span><strong>本地靶场</strong></div><div><span>{lab ? '靶场地址' : '目标地址'}</span><strong>{lab ? `127.0.0.1:${lab.port}` : '127.0.0.1'}</strong></div>{lab ? <><div><span>健康状态</span><strong>{healthLabels[lab.health]}</strong></div><div><span>数据来源</span><strong>本地夹具</strong></div></> : null}<div><span>远程 AI</span><strong>已禁用</strong></div><div><span>人工提交</span><strong>必须人工完成</strong></div></div></aside>
      </div>
      {lab ? (
        <div className="action-bar" role="toolbar" aria-label="靶场操作">
          <button className="action-button" type="button" aria-label="启动当前靶场" onClick={() => void runLabAction('start')} disabled={lab.health === 'healthy' || lab.operation === 'queued' || lab.operation === 'running'}><Play size={16} aria-hidden="true" /> 启动靶场</button>
          <button className="action-button" type="button" aria-label="停止当前靶场" data-variant="danger" onClick={() => void runLabAction('stop')} disabled={lab.health === 'stopped' || lab.operation === 'queued' || lab.operation === 'running'}><Square size={15} aria-hidden="true" /> 停止靶场</button>
          <button className="action-button" type="button" aria-label="重置当前靶场" onClick={() => void runLabAction('reset')} disabled={lab.operation === 'queued' || lab.operation === 'running'}><RefreshCw size={16} aria-hidden="true" /> 重置靶场</button>
          <span className="action-divider" aria-hidden="true" />
          <button className="action-button" type="button" onClick={openReport}>查看报告</button>
          <button className="action-button" type="button" onClick={exportEvents}>导出脱敏事件</button>
        </div>
      ) : (
        <ActionBar state={task.state} onPause={() => void repository.pauseTask(task.id).then(() => refresh('任务已在安全检查点暂停'))} onResume={() => void repository.resumeTask(task.id).then(() => refresh('任务已恢复运行'))} onCancel={() => void repository.cancelTask(task.id).then(() => refresh('任务已取消，不再追加新的检测动作'))} onOpenReport={openReport} onExport={exportEvents} />
      )}
    </>
  )
}

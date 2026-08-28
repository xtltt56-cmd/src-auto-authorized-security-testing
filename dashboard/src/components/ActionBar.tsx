import { Download, FileText, Pause, Play, Square } from 'lucide-react'
import type { TaskState } from '../lib/types'

type ActionBarProps = {
  state: TaskState
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  onOpenReport: () => void
  onExport: () => void
}

export function ActionBar({ state, onPause, onResume, onCancel, onOpenReport, onExport }: ActionBarProps) {
  const canPause = state === 'running'
  const canResume = state === 'paused'
  const canCancel = state === 'running' || state === 'paused' || state === 'queued'
  return (
    <div className="action-bar" role="toolbar" aria-label="任务操作">
      {canPause ? <button className="action-button" type="button" aria-label="暂停任务" onClick={onPause}><Pause size={16} aria-hidden="true" /> 暂停</button> : null}
      {canResume ? <button className="action-button" type="button" aria-label="继续任务" onClick={onResume}><Play size={16} aria-hidden="true" /> 继续</button> : <button className="action-button" type="button" aria-label="继续任务" disabled><Play size={16} aria-hidden="true" /> 继续</button>}
      <button className="action-button" type="button" aria-label="停止任务" data-variant="danger" onClick={onCancel} disabled={!canCancel}><Square size={15} aria-hidden="true" /> 停止</button>
      <span className="action-divider" aria-hidden="true" />
      <button className="action-button" type="button" onClick={onOpenReport}><FileText size={16} aria-hidden="true" /> 查看报告</button>
      <button className="action-button" type="button" onClick={onExport}><Download size={16} aria-hidden="true" /> 导出脱敏事件</button>
    </div>
  )
}

import { AlertCircle, CheckCircle2, Circle, Clock3, Pause, Play, ShieldAlert, XCircle } from 'lucide-react'
import type { TaskState } from '../lib/types'

type StatusBadgeState = TaskState | 'waiting' | 'starting'

type StatusBadgeProps = {
  state: StatusBadgeState
}

const labels: Record<StatusBadgeProps['state'], string> = {
  idle: '未启动',
  queued: '排队中',
  running: '运行中',
  paused: '已暂停',
  waiting: '等待人工',
  starting: '启动中',
  blocked: '已阻止',
  failed: '失败',
  completed: '已完成',
  cancelled: '已取消',
}

const icons: Record<StatusBadgeProps['state'], typeof Circle> = {
  idle: Circle,
  queued: Clock3,
  running: Play,
  paused: Pause,
  waiting: Clock3,
  starting: Play,
  blocked: ShieldAlert,
  failed: AlertCircle,
  completed: CheckCircle2,
  cancelled: XCircle,
}

export function StatusBadge({ state }: StatusBadgeProps) {
  const Icon = icons[state]
  const label = labels[state]
  return (
    <span className="status-badge" data-state={state} role="status" aria-label={`状态：${label}`}>
      <Icon size={14} strokeWidth={2.2} aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}

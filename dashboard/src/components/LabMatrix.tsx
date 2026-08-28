import { ExternalLink, HeartPulse, Play, RefreshCw, Square } from 'lucide-react'
import type { LabStatus } from '../lib/types'
import { StatusBadge } from './StatusBadge'

type LabMatrixProps = {
  labs: LabStatus[]
  onOpenLabTask: (taskId: string) => void
  onAction: (labId: string, action: 'start' | 'stop' | 'reset') => Promise<void>
  pendingLabId?: string | null
}

const healthToState = (health: LabStatus['health']) => {
  if (health === 'healthy') return 'completed' as const
  if (health === 'starting') return 'starting' as const
  if (health === 'blocked') return 'blocked' as const
  return 'idle' as const
}

export function LabMatrix({ labs, onOpenLabTask, onAction, pendingLabId = null }: LabMatrixProps) {
  return (
    <div className="surface-panel lab-matrix-panel">
      <div className="panel-header">
        <div>
          <h4>本地靶场矩阵</h4>
          <p>五个固定回环入口，只用于本地验证和练习</p>
        </div>
        <div className="matrix-actions">
          <span className="local-only-label"><HeartPulse size={14} aria-hidden="true" /> 回环模式</span>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">五个本地靶场的健康状态、阶段和候选数量</caption>
          <thead>
            <tr>
              <th scope="col">靶场</th>
              <th scope="col">健康</th>
              <th scope="col">当前阶段</th>
              <th scope="col">耗时</th>
              <th scope="col">候选</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            {labs.map((lab) => (
              <tr key={lab.id}>
                <th scope="row">
                  <button className="lab-name-button" type="button" onClick={() => onOpenLabTask(lab.taskId)}>
                    <span className="table-primary">{lab.name}</span>
                    <span className="table-secondary">127.0.0.1:{lab.port}</span>
                  </button>
                </th>
                <td data-label="健康"><StatusBadge state={healthToState(lab.health)} /></td>
                <td data-label="当前阶段">{lab.stage}</td>
                <td data-label="耗时">{lab.durationSeconds}s</td>
                <td data-label="候选"><strong>{lab.candidates}</strong></td>
                <td data-label="操作" className="lab-action-cell">
                  <div className="lab-row-actions">
                    <button className="table-link" type="button" aria-label={`查看 ${lab.name} 任务`} onClick={() => onOpenLabTask(lab.taskId)}>
                      查看任务 <ExternalLink size={14} aria-hidden="true" />
                    </button>
                    {lab.health === 'stopped' || lab.health === 'blocked' ? (
                      <button className="table-link" type="button" aria-label={`启动 ${lab.name}`} onClick={() => void onAction(lab.id, 'start')} disabled={pendingLabId === lab.id}>
                        <Play size={14} aria-hidden="true" /> {pendingLabId === lab.id ? '处理中' : '启动'}
                      </button>
                    ) : (
                      <button className="table-link table-link-danger" type="button" aria-label={`停止 ${lab.name}`} onClick={() => void onAction(lab.id, 'stop')} disabled={pendingLabId === lab.id}>
                        <Square size={13} aria-hidden="true" /> {pendingLabId === lab.id ? '处理中' : '停止'}
                      </button>
                    )}
                    <button className="table-link" type="button" aria-label={`重置 ${lab.name}`} onClick={() => void onAction(lab.id, 'reset')} disabled={pendingLabId === lab.id}>
                      <RefreshCw size={14} aria-hidden="true" /> 重置
                    </button>
                    {lab.health === 'healthy' && lab.openUrl && /^http:\/\/127\.0\.0\.1:\d+(?:\/|$)/.test(lab.openUrl) ? (
                      <a className="table-link" href={lab.openUrl} target="_blank" rel="noreferrer" aria-label={`打开 ${lab.name} 页面`}>
                        打开页面 <ExternalLink size={14} aria-hidden="true" />
                      </a>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

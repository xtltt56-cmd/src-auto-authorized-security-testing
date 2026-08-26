import { ExternalLink, HeartPulse } from 'lucide-react'
import type { LabStatus } from '../lib/types'
import { StatusBadge } from './StatusBadge'

type LabMatrixProps = {
  labs: LabStatus[]
  onOpenTask?: () => void
}

const healthToState = (health: LabStatus['health']) => {
  if (health === 'healthy') return 'completed' as const
  if (health === 'starting') return 'waiting' as const
  if (health === 'blocked') return 'blocked' as const
  return 'idle' as const
}

export function LabMatrix({ labs, onOpenTask }: LabMatrixProps) {
  return (
    <div className="surface-panel lab-matrix-panel">
      <div className="panel-header">
        <div>
          <h4>本地靶场矩阵</h4>
          <p>五个固定回环入口，只用于本地验证和练习</p>
        </div>
        <div className="matrix-actions">
          <span className="local-only-label"><HeartPulse size={14} aria-hidden="true" /> 回环模式</span>
          {onOpenTask ? <button className="table-link" type="button" onClick={onOpenTask}>打开任务详情 <ExternalLink size={14} aria-hidden="true" /></button> : null}
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
              <th scope="col"><span className="sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            {labs.map((lab) => (
              <tr key={lab.id}>
                <th scope="row">
                  <span className="table-primary">{lab.name}</span>
                  <span className="table-secondary">127.0.0.1:{lab.port}</span>
                </th>
                <td><StatusBadge state={healthToState(lab.health)} /></td>
                <td>{lab.stage}</td>
                <td>{lab.durationSeconds}s</td>
                <td><strong>{lab.candidates}</strong></td>
                <td>
                  <span className="table-secondary">本地夹具</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

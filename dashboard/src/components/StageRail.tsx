import { Check, Circle } from 'lucide-react'

export type StageItem = {
  id: string
  label: string
  state: 'completed' | 'running' | 'blocked' | 'idle'
  detail?: string
}

type StageRailProps = {
  stages: StageItem[]
}

export function StageRail({ stages }: StageRailProps) {
  return (
    <ol className="stage-rail" aria-label="任务阶段">
      {stages.map((stage) => (
        <li className="stage-item" data-state={stage.state} key={stage.id}>
          <span className="stage-dot" aria-hidden="true">
            {stage.state === 'completed' ? <Check size={15} /> : <Circle size={12} />}
          </span>
          <span>
            <strong>{stage.label}</strong>
            {stage.detail ? <small>{stage.detail}</small> : null}
          </span>
        </li>
      ))}
    </ol>
  )
}

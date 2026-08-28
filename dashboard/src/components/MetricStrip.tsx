import type { ReactNode } from 'react'

export type MetricItem = {
  label: string
  value: ReactNode
}

type MetricStripProps = {
  items: MetricItem[]
}

export function MetricStrip({ items }: MetricStripProps) {
  return (
    <div className="metric-strip" aria-label="任务计数">
      {items.map((item) => (
        <div className="metric-card" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  )
}

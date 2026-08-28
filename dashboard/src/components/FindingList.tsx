import { ChevronRight, Flag, ShieldAlert } from 'lucide-react'
import type { Finding } from '../lib/types'
import { StatusBadge } from './StatusBadge'

type FindingListProps = {
  findings: Finding[]
  selectedId: string | null
  onSelect: (finding: Finding) => void
}

const severityLabel: Record<Finding['severity'], string> = {
  high: '高',
  medium: '中',
  low: '低',
  info: '提示',
}

export function FindingList({ findings, selectedId, onSelect }: FindingListProps) {
  return (
    <section className="surface-panel finding-list-panel" aria-labelledby="finding-list-title">
      <div className="panel-header">
        <div><h4 id="finding-list-title">候选队列</h4><p>仅供人工复核，不代表可直接提交。</p></div>
        <span className="panel-count">{findings.length} 条</span>
      </div>
      <div className="finding-list">
        {findings.length === 0 ? <div className="empty-state">暂无候选记录</div> : findings.map((finding) => (
          <button className="finding-row" data-selected={selectedId === finding.id} type="button" key={finding.id} aria-label={finding.title} onClick={() => onSelect(finding)}>
            <span className="finding-row-icon" data-severity={finding.severity}><Flag size={16} aria-hidden="true" /></span>
            <span className="finding-row-copy"><strong>{finding.title}</strong><small>{finding.source}</small><span className="finding-row-meta"><span className="severity-dot" data-severity={finding.severity}>{severityLabel[finding.severity]}风险</span><StatusBadge state={finding.state === '已确认' ? 'completed' : finding.state === '已驳回' ? 'failed' : 'waiting'} /></span></span>
            <ChevronRight size={17} aria-hidden="true" />
          </button>
        ))}
      </div>
      <div className="list-footnote"><ShieldAlert size={14} aria-hidden="true" />证据已脱敏；不会自动执行破坏性验证。</div>
    </section>
  )
}

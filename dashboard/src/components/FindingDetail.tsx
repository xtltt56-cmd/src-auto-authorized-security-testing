import { ArrowLeft, CheckCircle2, FileWarning, ShieldCheck } from 'lucide-react'
import type { Finding } from '../lib/types'

type FindingDetailProps = {
  finding: Finding | null
  onBack?: () => void
}

const severityLabel: Record<Finding['severity'], string> = { high: '高风险', medium: '中风险', low: '低风险', info: '提示' }

export function FindingDetail({ finding, onBack }: FindingDetailProps) {
  if (!finding) {
    return <section className="surface-panel finding-detail empty-detail"><FileWarning size={26} aria-hidden="true" /><h4>选择一个候选</h4><p>从左侧候选队列选择记录，查看脱敏证据、前置条件和人工判断要点。</p></section>
  }

  return (
    <section className="surface-panel finding-detail" aria-labelledby="finding-detail-title">
      <div className="panel-header">
        <div><span className="eyebrow">{finding.source}</span><h4 id="finding-detail-title">候选详情</h4></div>
        {onBack ? <button className="icon-link" type="button" onClick={onBack}><ArrowLeft size={15} aria-hidden="true" /> 返回队列</button> : null}
      </div>
      <div className="finding-detail-body">
        <div className="finding-detail-title-row"><h3>{finding.title}</h3><span className="severity-pill" data-severity={finding.severity}>{severityLabel[finding.severity]}</span></div>
        <div className="finding-state-note"><ShieldCheck size={15} aria-hidden="true" /><span>当前状态：{finding.state} · 需要人工判断，系统不会自动提交。</span></div>
        <div className="detail-copy-block"><h5>摘要</h5><p>{finding.summary}</p></div>
        <div className="detail-copy-block"><h5>脱敏证据</h5><pre className="evidence-block">{finding.evidence}</pre></div>
        <div className="finding-detail-columns">
          <div className="detail-copy-block"><h5>前置条件</h5><ul>{finding.prerequisites.map((item) => <li key={item}>{item}</li>)}</ul></div>
          <div className="detail-copy-block"><h5>影响判断</h5><p>{finding.impact}</p></div>
        </div>
        <div className="detail-safe-footnote"><CheckCircle2 size={15} aria-hidden="true" />仅展示本地夹具中的候选数据；完整响应、账号、Token 和个人信息不会进入此页面。</div>
      </div>
    </section>
  )
}

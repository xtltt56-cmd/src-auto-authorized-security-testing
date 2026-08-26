import { FileText, Flag, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import type { Finding, ReportFile } from '../lib/types'
import { FindingDetail } from '../components/FindingDetail'
import { FindingList } from '../components/FindingList'
import { ReportViewer } from '../components/ReportViewer'

type FindingsPageProps = {
  findings: Finding[]
  reports: ReportFile[]
}

export function FindingsPage({ findings, reports }: FindingsPageProps) {
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const selectedFinding = findings.find((finding) => finding.id === selectedFindingId) ?? null
  const selectedReport = reports.find((report) => report.id === selectedReportId) ?? null

  return (
    <>
      <div className="page-heading">
        <div><span className="eyebrow">步骤 4 · 人工复核出口</span><h3>候选漏洞与报告</h3><p>按证据、前置条件和业务影响逐条判断；系统不会自动确认或提交补天报告。</p></div>
        <div className="page-heading-aside"><ShieldCheck size={17} aria-hidden="true" /><span>提交动作：人工完成</span></div>
      </div>
      <div className="review-safety surface-panel"><ShieldCheck size={18} aria-hidden="true" /><div><strong>这是候选，不是结论</strong><p>证据只来自本地夹具或离线审阅快照，账号、Token、完整响应和个人信息已脱敏。</p></div></div>
      <div className="finding-layout">
        <FindingList findings={findings} selectedId={selectedFindingId} onSelect={(finding) => setSelectedFindingId(finding.id)} />
        <FindingDetail finding={selectedFinding} />
      </div>
      <section className="surface-panel report-list-panel" aria-labelledby="report-list-title">
        <div className="panel-header"><div><h4 id="report-list-title">安全报告</h4><p>报告文件仅允许从项目白名单路径读取。</p></div><FileText size={20} aria-hidden="true" /></div>
        <div className="report-list">
          {reports.length === 0 ? <div className="empty-state">暂无报告文件</div> : reports.map((report) => <div className="report-row" key={report.id}><span className="report-row-icon"><Flag size={16} aria-hidden="true" /></span><span className="report-row-copy"><strong>{report.name}</strong><small>{report.relativePath} · 已脱敏</small></span><button className="action-button" type="button" onClick={() => setSelectedReportId(report.id)}>查看 {report.name}</button></div>)}
        </div>
      </section>
      {selectedReport ? <ReportViewer report={selectedReport} onClose={() => setSelectedReportId(null)} /> : null}
    </>
  )
}

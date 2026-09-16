import { FileText, Flag, ShieldCheck } from 'lucide-react'
import { useState, useEffect, useCallback } from 'react'
import type { TaskRepository } from '../lib/taskRepository'
import type { ArtifactSummary, Finding, ReportFile } from '../lib/types'
import { FindingDetail } from '../components/FindingDetail'
import { FindingList } from '../components/FindingList'
import { ReportViewer } from '../components/ReportViewer'

type FindingsPageProps = {
  findings: Finding[]
  reports: ReportFile[]
  repository?: TaskRepository
  initialSelectedReportId?: string | null
  onArtifactSummary?: (summary: ArtifactSummary) => void
}

export function FindingsPage({ findings: initialFindings, reports: initialReports, repository, initialSelectedReportId = null, onArtifactSummary }: FindingsPageProps) {
  const [data, setData] = useState({ findings: initialFindings, reports: initialReports })
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(Boolean(repository))
  const { findings, reports } = data
  const load = useCallback(async () => {
    if (!repository) return
    try {
      const result = await repository.getArtifacts()
      setData(result)
      onArtifactSummary?.({ candidateCount: result.findings.length, reportCount: result.reports.length })
      setNotice(result.warnings?.join('；') || '已读取本地历史结果；这些结果不代表本次靶场启动的扫描成绩。')
    }
    catch { setNotice('本地结果读取失败，请检查服务和报告目录。') }
  }, [onArtifactSummary, repository])
  const refresh = async () => { setBusy(true); await load(); setBusy(false) }
  // oxlint-disable-next-line react/set-state-in-effect -- loading data is an external repository synchronization.
  useEffect(() => { void load().finally(() => setBusy(false)) }, [load])
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)
  const [selectedReportId, setSelectedReportId] = useState<string | null>(initialSelectedReportId)
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
      <button className="action-button" disabled={busy} onClick={() => void refresh()}>{busy ? '正在读取…' : '刷新本地候选与报告'}</button>
      <p role="status">{notice}</p>
      <div className="report-workspace">
        <section className="surface-panel report-list-panel" aria-labelledby="report-list-title">
          <div className="panel-header"><div><h4 id="report-list-title">安全报告</h4><p>点击整行即可在右侧查看报告正文；文件只从项目白名单路径读取。</p></div><FileText size={20} aria-hidden="true" /></div>
          <div className="report-list">
            {reports.length === 0 ? <div className="empty-state">暂无报告文件</div> : reports.map((report) => (
              <button
                className="report-row"
                data-selected={selectedReportId === report.id}
                key={report.id}
                type="button"
                aria-label={`查看 ${report.name}`}
                aria-pressed={selectedReportId === report.id}
                onClick={() => setSelectedReportId(report.id)}
              >
                <span className="report-row-icon"><Flag size={16} aria-hidden="true" /></span>
                <span className="report-row-copy"><strong>{report.name}</strong><small>{report.relativePath} · 已脱敏</small></span>
                <span className="report-row-action">查看正文</span>
              </button>
            ))}
          </div>
        </section>
        <ReportViewer key={selectedReportId ?? 'no-report'} report={selectedReport} onDownload={repository ? report => repository.downloadReport(report.id) : undefined} onClose={selectedReport ? () => setSelectedReportId(null) : undefined} />
      </div>
    </>
  )
}

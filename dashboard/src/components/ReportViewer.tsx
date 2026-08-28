import { AlertTriangle, Download, FileText, ShieldCheck, X } from 'lucide-react'
import type { ReportFile } from '../lib/types'
import { isSafeReportPath } from '../lib/validation'

type ReportViewerProps = {
  report: ReportFile | null
  onClose?: () => void
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function ReportViewer({ report, onClose }: ReportViewerProps) {
  if (!report) {
    return <section className="surface-panel report-viewer empty-detail"><FileText size={26} aria-hidden="true" /><h4>选择一份报告</h4><p>报告以只读文本方式展示，脚本不会执行。</p></section>
  }

  const safePath = isSafeReportPath(report.relativePath)
  return (
    <section className="surface-panel report-viewer" aria-labelledby="report-viewer-title">
      <div className="panel-header">
        <div><span className="eyebrow">只读 · 已脱敏</span><h4 id="report-viewer-title">报告查看器</h4></div>
        {onClose ? <button className="icon-link" type="button" onClick={onClose}><X size={15} aria-hidden="true" /> 关闭</button> : null}
      </div>
      {!safePath ? <div className="report-blocked" role="alert"><AlertTriangle size={17} aria-hidden="true" /><span>报告路径不在项目白名单中，已阻止读取。</span></div> : <div className="report-viewer-body">
        <div className="report-meta"><div><strong>{report.name}</strong><span>{report.relativePath}</span></div><span>{formatBytes(report.sizeBytes)}</span></div>
        <div className="report-safety-note"><ShieldCheck size={15} aria-hidden="true" /><span><strong>脚本不会执行</strong>；仅显示由本地任务生成的脱敏文本。</span></div>
        <pre className="report-content" aria-label={`报告内容：${report.name}`}>{report.content}</pre>
        <button className="action-button" type="button" onClick={() => {
          const blob = new Blob([report.content], { type: 'text/plain;charset=utf-8' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a')
          link.href = url
          link.download = report.name
          link.click()
          URL.revokeObjectURL(url)
        }}><Download size={15} aria-hidden="true" /> 导出脱敏副本</button>
      </div>}
    </section>
  )
}

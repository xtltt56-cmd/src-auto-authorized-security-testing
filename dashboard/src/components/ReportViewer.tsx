import { AlertTriangle, Download, FileText, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import type { ReportFile } from '../lib/types'
import { isSafeReportPath } from '../lib/validation'

type ReportViewerProps = {
  report: ReportFile | null
  onClose?: () => void
  onDownload?: (report: ReportFile) => Promise<ReportFile>
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function ReportViewer({ report, onClose, onDownload }: ReportViewerProps) {
  const [downloadState, setDownloadState] = useState<'idle' | 'busy' | 'error'>('idle')
  if (!report) {
    return <section className="surface-panel report-viewer empty-detail"><FileText size={26} aria-hidden="true" /><h4>选择一份报告</h4><p>报告以只读文本方式展示，脚本不会执行。</p></section>
  }

  const safePath = isSafeReportPath(report.relativePath)
  const exportReport = async () => {
    setDownloadState('busy')
    try {
      const complete = onDownload ? await onDownload(report) : report
      const blob = new Blob([complete.content], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = complete.name
      link.click()
      URL.revokeObjectURL(url)
      setDownloadState('idle')
    } catch {
      setDownloadState('error')
    }
  }
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
        <button className="action-button" type="button" disabled={downloadState === 'busy'} onClick={() => void exportReport()}><Download size={15} aria-hidden="true" /> {downloadState === 'busy' ? '正在准备完整报告…' : report.truncated ? '下载完整脱敏报告' : '导出脱敏副本'}</button>
        {downloadState === 'error' ? <div className="report-blocked" role="alert"><AlertTriangle size={17} aria-hidden="true" /><span>完整报告导出失败，请刷新后重试。</span></div> : null}
      </div>}
    </section>
  )
}

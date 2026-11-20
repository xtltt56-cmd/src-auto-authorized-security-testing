import { render, screen } from '@testing-library/react'
import { FindingDetail } from './FindingDetail'
import type { Finding } from '../lib/types'

const base: Finding = {
  id: '1',
  title: 'Reflected XSS',
  severity: 'high',
  source: '历史运行 run-1',
  state: '已确认',
  summary: '摘要内容',
  evidence: '证据正文XYZ',
  prerequisites: ['前置条件'],
  impact: '影响判断',
}

describe('FindingDetail enrichment', () => {
  it('renders queue status, classification and sources when present', () => {
    render(
      <FindingDetail
        finding={{
          ...base,
          queueStatus: 'submission_ready',
          vulnType: 'xss',
          cwe: 'CWE-79',
          cvss: 6.1,
          confidence: 0.8,
          parameter: 'q',
          sources: [{ scanner: 'zap', templateId: '10016' }, { scanner: 'nuclei' }],
          fingerprint: 'abc123',
        }}
      />,
    )
    expect(screen.getByText(/队列状态：待提交/)).toBeVisible()
    expect(screen.getByText(/漏洞类型：xss/)).toBeVisible()
    expect(screen.getByText(/CWE：CWE-79/)).toBeVisible()
    expect(screen.getByText(/CVSS：6.1/)).toBeVisible()
    expect(screen.getByText(/参数：q/)).toBeVisible()
    expect(screen.getByText(/来源：zap\(10016\)；nuclei/)).toBeVisible()
    expect(screen.getByText(/指纹：abc123/)).toBeVisible()
  })

  it('omits the classification block for legacy findings without enrichment', () => {
    render(<FindingDetail finding={base} />)
    expect(screen.queryByText('分类与来源')).not.toBeInTheDocument()
    expect(screen.getByText('摘要内容')).toBeVisible()
    expect(screen.getByText('证据正文XYZ')).toBeVisible()
  })
})
import { isSafeReportPath, validateTargetDraft } from './validation'
import type { TargetDraft } from './types'

const validDraft: TargetDraft = {
  projectName: '示例授权项目',
  targetUrl: 'https://example.com/app',
  allowedHosts: 'example.com',
  allowedPorts: '443',
  excludedPaths: '/admin,/logout',
  windowStart: '2026-08-27T09:00',
  windowEnd: '2026-08-27T18:00',
  allowedMethods: 'GET, HEAD',
  concurrency: '1',
  requestLimit: '100',
  authorizationNote: '项目规则明确允许在此时间窗内进行低频安全测试。',
}

describe('target and report safety validation', () => {
  it('returns Chinese field errors for incomplete or unsafe drafts', () => {
    const emptyUrl = validateTargetDraft({ ...validDraft, targetUrl: '' })
    expect(emptyUrl.valid).toBe(false)
    expect(emptyUrl.errors?.targetUrl).toContain('URL')

    const invalidPort = validateTargetDraft({ ...validDraft, allowedPorts: '443,70000' })
    expect(invalidPort.valid).toBe(false)
    expect(invalidPort.errors?.allowedPorts).toContain('端口')

    const reversedWindow = validateTargetDraft({ ...validDraft, windowStart: '2026-08-27T18:00', windowEnd: '2026-08-27T09:00' })
    expect(reversedWindow.valid).toBe(false)
    expect(reversedWindow.errors?.windowEnd).toContain('结束时间')

    const missingAuthorization = validateTargetDraft({ ...validDraft, authorizationNote: '' })
    expect(missingAuthorization.valid).toBe(false)
    expect(missingAuthorization.errors?.authorizationNote).toContain('授权')
  })

  it('normalizes a valid draft without contacting the target', () => {
    const result = validateTargetDraft(validDraft)
    expect(result.valid).toBe(true)
    expect(result.normalizedUrl).toBe('https://example.com/app')
    expect(result.networkContact).toBe('none')
    expect(result.message).toContain('未访问目标')
    expect(result.scopeDigestSuffix).toMatch(/^scope-/)
  })

  it('allows only project-relative report paths and rejects traversal', () => {
    expect(isSafeReportPath('reports/local/juice-shop-summary.json')).toBe(true)
    expect(isSafeReportPath('validation/visual/overview.png')).toBe(true)
    expect(isSafeReportPath('../secrets.txt')).toBe(false)
    expect(isSafeReportPath('reports/local/../../secrets.txt')).toBe(false)
    expect(isSafeReportPath('C:\\Users\\Public\\report.txt')).toBe(false)
    expect(isSafeReportPath('/etc/passwd')).toBe(false)
  })
})

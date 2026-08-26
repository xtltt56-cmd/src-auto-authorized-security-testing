import type { TargetDraft, TargetDraftResult } from './types'

const allowedProtocols = new Set(['http:', 'https:'])
const allowedReportRoots = ['reports/', 'validation/']

const errorResult = (draft: TargetDraft, errors: Partial<Record<keyof TargetDraft, string>>): TargetDraftResult => ({
  valid: false,
  draft,
  normalizedUrl: '',
  scopeDigestSuffix: '',
  networkContact: 'none',
  message: '请先修正标记的中文错误；保存草稿不会访问目标。',
  errors,
})

const stableDigest = (value: string): string => {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

const csvValues = (value: string): string[] => value.split(',').map((item) => item.trim()).filter(Boolean)

const validateInteger = (value: string, label: string, min: number, max: number): string | undefined => {
  if (!/^\d+$/.test(value.trim())) return `${label}必须是数字。`
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed < min || parsed > max) return `${label}范围应为 ${min}-${max}。`
  return undefined
}

export function validateTargetDraft(draft: TargetDraft): TargetDraftResult {
  const errors: Partial<Record<keyof TargetDraft, string>> = {}
  const projectName = draft.projectName.trim()
  const targetUrl = draft.targetUrl.trim()
  const allowedHosts = csvValues(draft.allowedHosts).map((host) => host.toLowerCase())
  const allowedPorts = csvValues(draft.allowedPorts)

  if (!projectName) errors.projectName = '请填写项目名称。'

  let parsedUrl: URL | undefined
  if (!targetUrl) {
    errors.targetUrl = '请填写目标 URL。'
  } else {
    try {
      parsedUrl = new URL(targetUrl)
      if (!allowedProtocols.has(parsedUrl.protocol) || !parsedUrl.hostname) errors.targetUrl = '目标 URL 必须使用 http 或 https。'
      if (parsedUrl.username || parsedUrl.password) errors.targetUrl = '目标 URL 不得包含账号或密码。'
    } catch {
      errors.targetUrl = '目标 URL 格式无效，请检查协议和域名。'
    }
  }

  if (allowedHosts.length === 0) {
    errors.allowedHosts = '请填写至少一个允许的主机名。'
  } else if (parsedUrl && !allowedHosts.some((host) => host === parsedUrl?.hostname.toLowerCase() || (host.startsWith('*.') && parsedUrl?.hostname.toLowerCase().endsWith(host.slice(1))))) {
    errors.allowedHosts = '允许主机名必须覆盖目标 URL 的主机。'
  }

  if (allowedPorts.length === 0) {
    errors.allowedPorts = '请填写允许端口，例如 443。'
  } else {
    for (const port of allowedPorts) {
      const portError = validateInteger(port, '端口', 1, 65535)
      if (portError) {
        errors.allowedPorts = portError
        break
      }
    }
  }

  const start = Date.parse(draft.windowStart)
  const end = Date.parse(draft.windowEnd)
  if (!draft.windowStart.trim() || Number.isNaN(start)) errors.windowStart = '请填写有效的开始时间。'
  if (!draft.windowEnd.trim() || Number.isNaN(end)) errors.windowEnd = '请填写有效的结束时间。'
  if (!Number.isNaN(start) && !Number.isNaN(end) && end <= start) errors.windowEnd = '结束时间必须晚于开始时间。'

  if (!draft.allowedMethods.trim()) errors.allowedMethods = '请填写至少一种允许的方法。'
  const concurrencyError = validateInteger(draft.concurrency, '并发数', 1, 20)
  if (concurrencyError) errors.concurrency = concurrencyError
  const requestLimitError = validateInteger(draft.requestLimit, '请求上限', 1, 100000)
  if (requestLimitError) errors.requestLimit = requestLimitError
  if (!draft.authorizationNote.trim()) errors.authorizationNote = '请填写授权证明或项目规则说明。'

  if (Object.keys(errors).length > 0) return errorResult(draft, errors)

  const normalizedUrl = parsedUrl?.toString().replace(/\/$/, '') ?? targetUrl
  const digestInput = JSON.stringify({
    projectName,
    normalizedUrl,
    allowedHosts,
    allowedPorts,
    excludedPaths: csvValues(draft.excludedPaths),
    windowStart: draft.windowStart,
    windowEnd: draft.windowEnd,
    allowedMethods: csvValues(draft.allowedMethods).map((method) => method.toUpperCase()),
    concurrency: draft.concurrency.trim(),
    requestLimit: draft.requestLimit.trim(),
  })
  return {
    valid: true,
    draft: { ...draft, projectName, targetUrl: normalizedUrl, allowedHosts: allowedHosts.join(', '), allowedPorts: allowedPorts.join(', ') },
    normalizedUrl,
    scopeDigestSuffix: `scope-${stableDigest(digestInput)}`,
    networkContact: 'none',
    message: '授权草稿已通过本地校验；未访问目标。',
  }
}

export function isSafeReportPath(relativePath: string): boolean {
  if (typeof relativePath !== 'string') return false
  const trimmed = relativePath.trim()
  if (!trimmed || trimmed.includes('\0') || trimmed.includes('?') || trimmed.includes('#')) return false
  const normalized = trimmed.replaceAll('\\', '/')
  if (normalized.startsWith('/') || normalized.startsWith('//') || /^[A-Za-z]:\//.test(normalized)) return false
  let decoded = normalized
  try {
    decoded = decodeURIComponent(normalized)
  } catch {
    return false
  }
  const segments = decoded.split('/')
  if (segments.some((segment) => segment === '' || segment === '.' || segment === '..')) return false
  if (!allowedReportRoots.some((root) => decoded.toLowerCase().startsWith(root))) return false
  return segments.length >= 2 && !decoded.endsWith('/')
}

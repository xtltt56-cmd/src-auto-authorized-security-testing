export type TaskState =
  | 'idle'
  | 'queued'
  | 'running'
  | 'paused'
  | 'blocked'
  | 'failed'
  | 'completed'
  | 'cancelled'

export type TaskKind = 'local-lab' | 'offline-review' | 'authorized-draft'
export type NetworkContact = 'none' | 'loopback' | 'authorized-target'
export type EventLevel = 'info' | 'success' | 'warning' | 'danger'

export type TaskCounters = {
  endpoints: number
  api: number
  candidates: number
  blocked: number
  errors: number
}

export type TaskSummary = {
  id: string
  name: string
  kind: TaskKind
  state: TaskState
  stage: string
  progress: number
  elapsedSeconds: number
  counters: TaskCounters
  networkContact: NetworkContact
  updatedAt: string
}

export type TaskEvent = {
  id: number
  taskId: string
  time: string
  level: EventLevel
  stage: string
  message: string
  tool?: string
  redacted: true
}

export type LabStatus = {
  id: string
  taskId: string
  name: string
  port: number
  health: 'healthy' | 'starting' | 'stopped' | 'unavailable' | 'blocked'
  stage: string
  durationSeconds: number
  candidates: number
  reportId?: string
  localOnly: true
  operation?: 'idle' | 'queued' | 'running' | 'completed' | 'failed'
  openUrl?: string
  message?: string
}

export type DependencyStatus = {
  executionServiceReady: boolean
  dockerReady: boolean
  message: string
}

export type Finding = {
  id: string
  title: string
  severity: 'high' | 'medium' | 'low' | 'info'
  source: string
  state: '待人工复核' | '已确认' | '已驳回'
  summary: string
  evidence: string
  prerequisites: string[]
  impact: string
}

export type ReportFile = {
  id: string
  name: string
  relativePath: string
  sizeBytes: number
  content: string
  redacted: true
}

export type TargetDraft = {
  projectName: string
  targetUrl: string
  allowedHosts: string
  allowedPorts: string
  excludedPaths: string
  windowStart: string
  windowEnd: string
  allowedMethods: string
  concurrency: string
  requestLimit: string
  authorizationNote: string
}

export type TargetDraftResult = {
  id?: string
  savedPath?: string
  valid: boolean
  draft: TargetDraft
  normalizedUrl: string
  scopeDigestSuffix: string
  networkContact: 'none'
  message: string
  errors?: Partial<Record<keyof TargetDraft, string>>
}

export type ReviewEntry = {
  name: string
  status: string
  actionable: boolean
  review?: { status: string; reason: string; targetCount: number }
}

export type AIProviderSettings = {
  id: 'deepseek' | 'zhipu' | 'openrouter'
  displayName: string
  model: string
  officialModel: string
  keySaved: boolean
  endpointHost: string
  manualOnly?: boolean
  pricingNote?: string
}

export type AIConnectionResult = { ok: boolean; code: string }

export type DashboardSnapshot = {
  source: 'local-fixture' | 'safe-placeholder' | 'loopback'
  dependency?: DependencyStatus
  tasks: TaskSummary[]
  labs: LabStatus[]
  events: TaskEvent[]
  findings: Finding[]
  reports: ReportFile[]
}

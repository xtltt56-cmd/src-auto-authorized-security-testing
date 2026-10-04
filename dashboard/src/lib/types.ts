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
  reportId?: string | null
  lastRunId?: string | null
  localOnly: true
  operation?: 'idle' | 'queued' | 'running' | 'completed' | 'failed'
  detectionOperation?: 'idle' | 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled'
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
  url?: string
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
  truncated?: boolean
}

export type ArtifactSummary = { candidateCount: number; reportCount: number }

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
  /** Whether the Dashboard process was started with remote-AI consent. */
  sessionEnabled?: boolean
}

export type AIConnectionResult = { ok: boolean; code: string }

export type AgentStart = { labId: string; mode: 'candidate-review' | 'api-permissions'; provider: string; allowCloud: boolean; limits?: { max_steps: number }; resumeId?: string; candidateId?: string }
export type AgentRun = {
  id: string; labId: string; mode: AgentStart['mode']; provider: string; state: string; reason: string
  steps: number; requests: number; modelCalls: number; tokens: number; usageEstimated: boolean
  elapsedSeconds: number; candidates: number; reportId: string; createdAt: string; candidateId?: string
  resourceCheck?: { known?: boolean; memory_gb?: number; max_memory_gb?: number; cpu_percent?: number }
  trace: Array<{ index: number; result: string; reason?: string; observationId?: string; decision?: { action: string; reference: string; evidence: string[]; reason: string } }>
  observations: Array<{ id: string; action: string; reference: string; summary: string; candidate?: boolean }>
}
export type AgentSnapshot = { enabled: boolean; remoteSessionEnabled: boolean; cloudAgentAvailable?: boolean; activeId: string | null; ownedActiveId?: string | null; runs: AgentRun[] }

export type DashboardSnapshot = {
  source: 'local-fixture' | 'safe-placeholder' | 'loopback'
  dependency?: DependencyStatus
  tasks: TaskSummary[]
  labs: LabStatus[]
  events: TaskEvent[]
  findings: Finding[]
  reports: ReportFile[]
}

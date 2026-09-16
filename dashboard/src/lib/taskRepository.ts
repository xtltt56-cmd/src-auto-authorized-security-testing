import { fixtureSnapshot } from './fixtures'
import type { AIConnectionResult, AIProviderSettings, ArtifactSummary, DashboardSnapshot, ReportFile, TaskEvent, TaskState, TaskSummary, TargetDraft, TargetDraftResult, ReviewEntry } from './types'
import { validateTargetDraft } from './validation'

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const nowTime = (): string =>
  new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date())

const eventFor = (task: TaskSummary, id: number, level: TaskEvent['level'], stage: string, message: string): TaskEvent => ({
  id,
  taskId: task.id,
  time: nowTime(),
  level,
  stage,
  message,
  tool: 'fixture-controller',
  redacted: true,
})

export interface TaskRepository {
  supportsPause?: boolean
  listDrafts(): Promise<TargetDraftResult[]>
  saveDraft(draft: TargetDraft): Promise<TargetDraftResult>
  reviewTargets(): Promise<ReviewEntry[]>
  getArtifacts(): Promise<Pick<DashboardSnapshot, 'findings' | 'reports'> & { warnings?: string[] }>
  getArtifactSummary(): Promise<ArtifactSummary>
  downloadReport(reportId: string): Promise<ReportFile>
  getDashboardSnapshot(): Promise<DashboardSnapshot>
  getTask(taskId: string): Promise<TaskSummary>
  getEvents(taskId: string): Promise<TaskEvent[]>
  pauseTask(taskId: string): Promise<void>
  resumeTask(taskId: string): Promise<void>
  cancelTask(taskId: string): Promise<void>
  startLab(labId: string): Promise<void>
  stopLab(labId: string): Promise<void>
  resetLab(labId: string): Promise<void>
  startLabDetection(labId: string): Promise<void>
  stopLabDetection(labId: string): Promise<void>
  startAllLabs(): Promise<void>
  stopAllLabs(): Promise<void>
  startDockerDesktop(): Promise<void>
  listAIProviders(): Promise<AIProviderSettings[]>
  saveAIProvider(provider: string, value: { apiKey: string; model: string }): Promise<AIProviderSettings>
  testAIProvider(provider: string): Promise<AIConnectionResult>
}

export const createFixtureRepository = (initialSnapshot: DashboardSnapshot = fixtureSnapshot): TaskRepository => {
  const state = clone(initialSnapshot)
  const drafts: TargetDraftResult[] = []
  let nextEventId = Math.max(0, ...state.events.map((event) => event.id)) + 1
  const providers: AIProviderSettings[] = [
    { id: 'deepseek', displayName: 'DeepSeek V4.1 Flash', model: 'deepseek-flash', officialModel: 'deepseek-flash', keySaved: false, endpointHost: 'api.deepseek.com' },
    { id: 'zhipu', displayName: '智谱 GLM-5.3-Flash', model: 'glm-5.3-flash', officialModel: 'glm-5.3-flash', keySaved: false, endpointHost: 'open.bigmodel.cn' },
    { id: 'openrouter', displayName: 'OpenRouter', model: 'openrouter/free', officialModel: 'openrouter/free', keySaved: false, endpointHost: 'openrouter.ai' },
  ]

  const taskOrThrow = (taskId: string): TaskSummary => {
    const task = state.tasks.find((item) => item.id === taskId)
    if (!task) throw new Error(`TASK_NOT_FOUND:${taskId}`)
    return task
  }

  const append = (task: TaskSummary, level: TaskEvent['level'], stage: string, message: string): void => {
    state.events.push(eventFor(task, nextEventId, level, stage, message))
    nextEventId += 1
    task.updatedAt = new Date().toISOString()
  }

  const transition = (task: TaskSummary, next: TaskState, message: string): void => {
    task.state = next
    append(task, next === 'blocked' || next === 'failed' ? 'danger' : 'info', task.stage, message)
  }

  return {
    supportsPause: true,
    async listDrafts() { return clone(drafts) },
    async saveDraft(draft) {
      const result = validateTargetDraft(draft)
      if (!result.valid) throw new Error('draft_invalid')
      drafts.unshift(result)
      return result
    },
    async reviewTargets() { return [] },
    async getArtifacts() { return { findings: clone(state.findings), reports: clone(state.reports) } },
    async getArtifactSummary() { return { candidateCount: state.findings.length, reportCount: state.reports.length } },
    async downloadReport(reportId) {
      const report = state.reports.find(item => item.id === reportId)
      if (!report) throw new Error('REPORT_NOT_FOUND')
      return { ...clone(report), truncated: false }
    },
    async getDashboardSnapshot() {
      return clone(state)
    },
    async getTask(taskId) {
      return clone(taskOrThrow(taskId))
    },
    async getEvents(taskId) {
      taskOrThrow(taskId)
      return clone(state.events.filter((event) => event.taskId === taskId))
    },
    async pauseTask(taskId) {
      const task = taskOrThrow(taskId)
      if (task.state === 'running') transition(task, 'paused', '任务已在安全检查点暂停')
    },
    async resumeTask(taskId) {
      const task = taskOrThrow(taskId)
      if (task.state === 'paused') transition(task, 'running', '任务已继续执行')
    },
    async cancelTask(taskId) {
      const task = taskOrThrow(taskId)
      if (task.state === 'running' || task.state === 'paused' || task.state === 'queued') transition(task, 'cancelled', '任务已取消，不再追加新的检测动作')
    },
    async startLab(labId) {
      const lab = state.labs.find((item) => item.id === labId)
      if (!lab) throw new Error(`LAB_NOT_FOUND:${labId}`)
      const task = taskOrThrow(lab.taskId)
      lab.health = 'healthy'
      lab.stage = '靶场已就绪'
      lab.durationSeconds = Math.max(1, lab.durationSeconds)
      task.state = 'completed'
      task.stage = '靶场已就绪'
      task.progress = 100
      task.networkContact = 'loopback'
      append(task, 'success', task.stage, `${lab.name} 本地夹具已启动`)
    },
    async stopLab(labId) {
      const lab = state.labs.find((item) => item.id === labId)
      if (!lab) throw new Error(`LAB_NOT_FOUND:${labId}`)
      const task = taskOrThrow(lab.taskId)
      lab.health = 'stopped'
      lab.stage = '未启动'
      lab.durationSeconds = 0
      task.state = 'idle'
      task.stage = '未启动'
      task.progress = 0
      task.elapsedSeconds = 0
      task.networkContact = 'none'
      append(task, 'info', task.stage, `${lab.name} 本地夹具已停止`)
    },
    async resetLab(labId) {
      await this.stopLab(labId)
      await this.startLab(labId)
    },
    async startLabDetection(labId) {
      const lab = state.labs.find((item) => item.id === labId)
      if (!lab) throw new Error(`LAB_NOT_FOUND:${labId}`)
      if (lab.health !== 'healthy') throw new Error('LAB_NOT_READY')
      const task = taskOrThrow(lab.taskId)
      lab.detectionOperation = 'completed'
      lab.stage = '检测完成'
      lab.lastRunId = `fixture-${labId}`
      lab.candidates = Math.max(1, lab.candidates)
      if (!lab.reportId) {
        lab.reportId = `report-${labId}`
        state.reports.push({
          id: lab.reportId,
          name: `${labId}-detection.md`,
          relativePath: `reports/local/${labId}-detection.md`,
          sizeBytes: 120,
          content: `# ${lab.name} 本地检测\n\n真实回环检测夹具已完成；候选仍需人工复核。`,
          redacted: true,
        })
      }
      task.state = 'completed'
      task.stage = '检测完成'
      task.progress = 100
      task.counters = { ...task.counters, endpoints: Math.max(1, task.counters.endpoints), candidates: lab.candidates }
      task.networkContact = 'loopback'
      append(task, 'success', task.stage, '真实回环检测已完成；报告已关联到当前任务')
    },
    async stopLabDetection(labId) {
      const lab = state.labs.find((item) => item.id === labId)
      if (!lab) throw new Error(`LAB_NOT_FOUND:${labId}`)
      const task = taskOrThrow(lab.taskId)
      lab.detectionOperation = 'cancelled'
      task.state = 'cancelled'
      task.stage = '已取消'
      append(task, 'warning', task.stage, '检测已在安全检查点停止')
    },
    async startAllLabs() {
      for (const lab of state.labs) await this.startLab(lab.id)
    },
    async stopAllLabs() {
      for (const lab of state.labs) await this.stopLab(lab.id)
    },
    async startDockerDesktop() { return undefined },
    async listAIProviders() { return clone(providers) },
    async saveAIProvider(provider, value) {
      const item = providers.find(entry => entry.id === provider)
      if (!item) throw new Error('PROVIDER_NOT_FOUND')
      item.model = value.model
      if (value.apiKey) item.keySaved = true
      return clone(item)
    },
    async testAIProvider() { return { ok: true, code: 'reachable_model_available' } },
  }
}

export class LoopbackRepositoryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LoopbackRepositoryError'
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

const normalizeBaseUrl = (baseUrl: string): string => {
  const normalized = baseUrl.replace(/\/$/, '')
  if (normalized === '/api') return normalized
  try {
    const parsed = new URL(normalized)
    if (parsed.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(parsed.hostname) || parsed.pathname !== '/api') throw new Error('not-loopback')
    return normalized
  } catch {
    throw new LoopbackRepositoryError('LOOPBACK_BASE_URL_NOT_ALLOWED')
  }
}

export const createLoopbackRepository = (baseUrl = '/api', fetchImpl: FetchLike = fetch): TaskRepository => {
  const base = normalizeBaseUrl(baseUrl)
  let sessionPromise: Promise<string> | null = null

  const parseJson = async <T,>(response: Response): Promise<T> => {
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      throw new LoopbackRepositoryError('LOOPBACK_INVALID_RESPONSE')
    }
    if (!response.ok) {
      const code = typeof payload === 'object' && payload !== null && 'error' in payload ? String((payload as { error?: unknown }).error) : 'LOOPBACK_SERVICE_UNAVAILABLE'
      throw new LoopbackRepositoryError(code)
    }
    return payload as T
  }

  const getSession = async (): Promise<string> => {
    if (!sessionPromise) {
      sessionPromise = fetchImpl(`${base}/session`, { headers: { Accept: 'application/json' } })
        .then((response) => parseJson<{ token?: string }>(response))
        .then((payload) => {
          if (!payload.token) throw new LoopbackRepositoryError('LOOPBACK_SESSION_MISSING')
          return payload.token
        })
        .catch((error) => {
          sessionPromise = null
          if (error instanceof LoopbackRepositoryError) throw error
          throw new LoopbackRepositoryError('LOOPBACK_SERVICE_UNAVAILABLE')
        })
    }
    return sessionPromise
  }

  const request = async <T,>(path: string, init: RequestInit = {}, renewed = false): Promise<T> => {
    const token = await getSession()
    const headers = new Headers(init.headers)
    headers.set('Accept', 'application/json')
    headers.set('X-SRC-Auto-Token', token)
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    try {
      const response = await fetchImpl(`${base}${path}`, { ...init, headers })
      if (response.status === 401 && !renewed) {
        sessionPromise = null
        // The server rejects authentication before executing any action.
        return request<T>(path, init, true)
      }
      return await parseJson<T>(response)
    } catch (error) {
      if (error instanceof LoopbackRepositoryError) throw error
      throw new LoopbackRepositoryError('LOOPBACK_SERVICE_UNAVAILABLE')
    }
  }

  const action = (path: string): Promise<void> => request(path, { method: 'POST', body: '{}' }).then(() => undefined)
  return {
    async listDrafts() { return (await request<{ drafts: TargetDraftResult[] }>('/drafts')).drafts },
    saveDraft: (draft) => request<TargetDraftResult>('/drafts', { method: 'POST', body: JSON.stringify(draft) }),
    async reviewTargets() { return (await request<{ entries: ReviewEntry[] }>('/review')).entries },
    getArtifacts: () => request('/artifacts'),
    getArtifactSummary: () => request('/artifacts/summary'),
    downloadReport: (reportId) => request(`/reports/${encodeURIComponent(reportId)}`),
    async getDashboardSnapshot() {
      return request<DashboardSnapshot>('/dashboard')
    },
    async getTask(taskId) {
      const snapshot = await request<DashboardSnapshot>('/dashboard')
      const task = snapshot.tasks.find((item) => item.id === taskId)
      if (!task) throw new LoopbackRepositoryError(`TASK_NOT_FOUND:${taskId}`)
      return task
    },
    async getEvents(taskId) {
      const snapshot = await request<DashboardSnapshot>('/dashboard')
      return snapshot.events.filter((event) => event.taskId === taskId)
    },
    async pauseTask() { throw new LoopbackRepositoryError('LOCAL_TASK_PAUSE_UNSUPPORTED') },
    async resumeTask() { throw new LoopbackRepositoryError('LOCAL_TASK_RESUME_UNSUPPORTED') },
    async cancelTask(taskId) {
      const labId = taskId.replace(/^run-lab-/, '')
      if (taskId === 'run-local-001') return action('/labs/stop-all')
      return action(`/labs/${encodeURIComponent(labId)}/stop`)
    },
    startLab: (labId) => action(`/labs/${encodeURIComponent(labId)}/start`),
    stopLab: (labId) => action(`/labs/${encodeURIComponent(labId)}/stop`),
    resetLab: (labId) => action(`/labs/${encodeURIComponent(labId)}/reset`),
    startLabDetection: (labId) => action(`/labs/${encodeURIComponent(labId)}/detect`),
    stopLabDetection: (labId) => action(`/labs/${encodeURIComponent(labId)}/detect-stop`),
    startAllLabs: () => action('/labs/start-all'),
    stopAllLabs: () => action('/labs/stop-all'),
    startDockerDesktop: () => action('/dependencies/docker/start'),
    async listAIProviders() { return (await request<{ providers: AIProviderSettings[] }>('/settings/providers')).providers },
    saveAIProvider: (provider, value) => request<AIProviderSettings>(`/settings/providers/${encodeURIComponent(provider)}`, { method: 'POST', body: JSON.stringify(value) }),
    testAIProvider: (provider) => request<AIConnectionResult>(`/settings/providers/${encodeURIComponent(provider)}/test`, { method: 'POST', body: JSON.stringify({ allowNetwork: true }) }),
  }
}

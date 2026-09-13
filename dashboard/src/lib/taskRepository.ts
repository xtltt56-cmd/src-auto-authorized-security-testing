import { fixtureSnapshot } from './fixtures'
import type { DashboardSnapshot, TaskEvent, TaskState, TaskSummary, TargetDraft, TargetDraftResult, ReviewEntry } from './types'
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
  getDashboardSnapshot(): Promise<DashboardSnapshot>
  getTask(taskId: string): Promise<TaskSummary>
  getEvents(taskId: string): Promise<TaskEvent[]>
  pauseTask(taskId: string): Promise<void>
  resumeTask(taskId: string): Promise<void>
  cancelTask(taskId: string): Promise<void>
  startLab(labId: string): Promise<void>
  stopLab(labId: string): Promise<void>
  resetLab(labId: string): Promise<void>
  startAllLabs(): Promise<void>
  stopAllLabs(): Promise<void>
}

export const createFixtureRepository = (initialSnapshot: DashboardSnapshot = fixtureSnapshot): TaskRepository => {
  const state = clone(initialSnapshot)
  const drafts: TargetDraftResult[] = []
  let nextEventId = Math.max(0, ...state.events.map((event) => event.id)) + 1

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
    async startAllLabs() {
      for (const lab of state.labs) await this.startLab(lab.id)
    },
    async stopAllLabs() {
      for (const lab of state.labs) await this.stopLab(lab.id)
    },
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
    startAllLabs: () => action('/labs/start-all'),
    stopAllLabs: () => action('/labs/stop-all'),
  }
}

import { fixtureSnapshot } from './fixtures'
import type { DashboardSnapshot, TaskEvent, TaskState, TaskSummary } from './types'

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
  getDashboardSnapshot(): Promise<DashboardSnapshot>
  getTask(taskId: string): Promise<TaskSummary>
  getEvents(taskId: string): Promise<TaskEvent[]>
  pauseTask(taskId: string): Promise<void>
  resumeTask(taskId: string): Promise<void>
  cancelTask(taskId: string): Promise<void>
}

export const createFixtureRepository = (): TaskRepository => {
  const state = clone(fixtureSnapshot)
  let nextEventId = Math.max(...state.events.map((event) => event.id)) + 1

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
  }
}

export const createLoopbackRepository = (_baseUrl: string, _sessionToken: string): TaskRepository => {
  throw new Error('LOOPBACK_ADAPTER_NOT_ENABLED')
}

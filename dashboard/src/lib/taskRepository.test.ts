import { createFixtureRepository } from './taskRepository'

describe('fixture task repository', () => {
  it('returns a local-only snapshot with five labs and redacted events', async () => {
    const repository = createFixtureRepository()
    const snapshot = await repository.getDashboardSnapshot()

    expect(snapshot.tasks[0].networkContact).toBe('loopback')
    expect(snapshot.labs).toHaveLength(5)
    expect(snapshot.events.every((event) => event.redacted)).toBe(true)
    expect(snapshot.findings.length).toBeGreaterThan(0)
  })

  it('maps every local lab to an independent local-only task with events', async () => {
    const snapshot = await createFixtureRepository().getDashboardSnapshot()
    expect(snapshot.labs).toHaveLength(5)

    for (const lab of snapshot.labs) {
      expect(lab.taskId).toMatch(/^run-lab-/)
      expect(snapshot.tasks.some((task) => task.id === lab.taskId && task.kind === 'local-lab' && task.networkContact === 'loopback')).toBe(true)
      expect(snapshot.events.some((event) => event.taskId === lab.taskId && event.redacted)).toBe(true)
    }
  })

  it('pauses and cancels a task without adding post-cancel events', async () => {
    const repository = createFixtureRepository()
    await repository.pauseTask('run-local-001')
    expect((await repository.getTask('run-local-001')).state).toBe('paused')

    await repository.cancelTask('run-local-001')
    const eventCount = (await repository.getEvents('run-local-001')).length
    await repository.resumeTask('run-local-001')

    expect((await repository.getTask('run-local-001')).state).toBe('cancelled')
    expect((await repository.getEvents('run-local-001')).length).toBe(eventCount)
  })
})

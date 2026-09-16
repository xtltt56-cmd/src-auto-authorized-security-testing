import { createFixtureRepository, createLoopbackRepository } from './taskRepository'
import { safeDefaultSnapshot } from './fixtures'

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

describe('loopback task repository', () => {
  it('renews an expired session once after a backend restart', async () => {
    let current = 'old'
    let sessions = 0
    const repository = createLoopbackRepository('/api', async (url, init) => {
      if (String(url).endsWith('/session')) {
        sessions++
        return new Response(JSON.stringify({ token: current }))
      }
      const valid = new Headers(init?.headers).get('X-SRC-Auto-Token') === current
      return new Response(JSON.stringify(valid ? safeDefaultSnapshot : { error: 'invalid_session_token' }), { status: valid ? 200 : 401 })
    })
    await repository.getDashboardSnapshot()
    current = 'new'
    await repository.getDashboardSnapshot()
    expect(sessions).toBe(2)
  })
  it('acquires one local session and sends it with snapshot and actions', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input)
      requests.push({ url, init })
      if (url === '/api/session') return new Response(JSON.stringify({ token: 'local-token' }), { status: 200 })
      if (url === '/api/dashboard') return new Response(JSON.stringify({ ...safeDefaultSnapshot, source: 'loopback' }), { status: 200 })
      return new Response(JSON.stringify({ accepted: true }), { status: 202 })
    }
    const repository = createLoopbackRepository('/api', fetchImpl)

    expect((await repository.getDashboardSnapshot()).source).toBe('loopback')
    await repository.startLab('dvwa')
    await repository.resetLab('dvwa')
    await repository.stopLab('dvwa')
    await repository.startAllLabs()
    await repository.stopAllLabs()
    await repository.startLabDetection('dvwa')
    await repository.stopLabDetection('dvwa')

    expect(requests.filter((request) => request.url === '/api/session')).toHaveLength(1)
    expect(requests.map((request) => request.url)).toEqual([
      '/api/session',
      '/api/dashboard',
      '/api/labs/dvwa/start',
      '/api/labs/dvwa/reset',
      '/api/labs/dvwa/stop',
      '/api/labs/start-all',
      '/api/labs/stop-all',
      '/api/labs/dvwa/detect',
      '/api/labs/dvwa/detect-stop',
    ])
    for (const request of requests.slice(1)) {
      expect(new Headers(request.init?.headers).get('X-SRC-Auto-Token')).toBe('local-token')
    }
  })

  it('loads the artifact summary and downloads a report through encoded loopback routes', async () => {
    const requests: string[] = []
    const repository = createLoopbackRepository('/api', async (input) => {
      const url = String(input)
      requests.push(url)
      if (url === '/api/session') return new Response(JSON.stringify({ token: 'local-token' }), { status: 200 })
      if (url === '/api/artifacts/summary') return new Response(JSON.stringify({ candidateCount: 4, reportCount: 2 }), { status: 200 })
      return new Response(JSON.stringify({ id: 'reports/local/test.md', name: 'test.md', relativePath: 'reports/local/test.md', sizeBytes: 4, content: 'full', redacted: true, truncated: false }), { status: 200 })
    })

    expect(await repository.getArtifactSummary()).toEqual({ candidateCount: 4, reportCount: 2 })
    expect((await repository.downloadReport('reports/local/test.md')).content).toBe('full')
    expect(requests).toContain('/api/reports/reports%2Flocal%2Ftest.md')
  })

  it('rejects an unavailable or malformed local service', async () => {
    const repository = createLoopbackRepository('/api', async () => new Response('{}', { status: 503 }))
    await expect(repository.getDashboardSnapshot()).rejects.toThrow('LOOPBACK_SERVICE_UNAVAILABLE')
  })

  it('does not allow the repository base URL to be redirected off loopback', () => {
    expect(() => createLoopbackRepository('https://outside.example/api')).toThrow('LOOPBACK_BASE_URL_NOT_ALLOWED')
  })
})

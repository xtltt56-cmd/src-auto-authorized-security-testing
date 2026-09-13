import { expect, test } from '@playwright/test'

const localLabTasks = [
  ['Juice Shop', 'Juice Shop · 本地任务', '127.0.0.1:3000'],
  ['DVWA', 'DVWA · 本地任务', '127.0.0.1:8081'],
  ['WebGoat', 'WebGoat · 本地任务', '127.0.0.1:8082'],
  ['VAmPI', 'VAmPI · 本地任务', '127.0.0.1:8083'],
  ['Business API', 'Business API · 本地任务', '127.0.0.1:8084'],
] as const

test.beforeEach(async ({ page }) => {
  // Keep tests deterministic when the real local execution service is not running.
  // The loopback repository treats a valid response without a token as a safe
  // disconnected state, avoiding noisy browser 5xx resource errors.
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })
})

test('starts truthfully idle when the local execution service is disconnected', async ({ page }) => {
  const consoleErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.hostname !== '127.0.0.1') externalRequests.push(request.url())
  })

  await page.goto('/')
  await expect(page).toHaveTitle('SRC-Auto 安全测试控制台')
  await expect(page.getByRole('heading', { name: '安全测试控制台' })).toBeVisible()
  await expect(page.getByRole('status', { name: '数据来源状态' })).toContainText('未连接本地执行服务')
  await expect(page.getByText('运行中', { exact: true })).toHaveCount(0)
  await expect(page.getByText('未启动', { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/真实目标不会自动执行/).first()).toBeVisible()
  await page.getByRole('button', { name: '本地靶场', exact: true }).click()
  for (const lab of ['Juice Shop', 'DVWA', 'WebGoat', 'VAmPI', 'Business API']) await expect(page.getByText(lab, { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '打开环境任务' }).click()
  await expect(page.getByRole('heading', { name: '实时事件' })).toBeVisible()
  await expect(page.getByText('0s', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: '继续任务' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '停止任务' })).toBeDisabled()
  await page.getByRole('button', { name: '查看报告' }).click()
  await expect(page.getByRole('heading', { name: '候选漏洞与报告' })).toBeVisible()
  await expect(page.getByText('暂无报告文件', { exact: true })).toBeVisible()

  expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
  expect(externalRequests, externalRequests.join('\n')).toEqual([])
})

test('renders real loopback lab controls and sends only fixed actions', async ({ page }) => {
  const calls: string[] = []
  const idleSnapshot = {
    source: 'loopback',
    dependency: { executionServiceReady: true, dockerReady: true, message: 'Docker Engine 已就绪' },
    tasks: [
      {
        id: 'run-local-001', name: '本地五靶场控制', kind: 'local-lab', state: 'idle', stage: '未启动', progress: 0, elapsedSeconds: 0,
        counters: { endpoints: 0, api: 0, candidates: 0, blocked: 0, errors: 0 }, networkContact: 'none', updatedAt: '',
      },
      ...localLabTasks.map(([name], index) => ({
        id: `run-lab-${['juice-shop', 'dvwa', 'webgoat', 'vampi', 'business-api'][index]}`, name: `${name} · 本地靶场`, kind: 'local-lab', state: 'idle', stage: '未启动', progress: 0, elapsedSeconds: 0,
        counters: { endpoints: 0, api: 0, candidates: 0, blocked: 0, errors: 0 }, networkContact: 'none', updatedAt: '',
      })),
    ],
    labs: [
      ['juice-shop', 'Juice Shop', 3000], ['dvwa', 'DVWA', 8081], ['webgoat', 'WebGoat', 8082], ['vampi', 'VAmPI', 8083], ['business-api', 'Business API', 8084],
    ].map(([id, name, port], index) => ({ id, taskId: `run-lab-${['juice-shop', 'dvwa', 'webgoat', 'vampi', 'business-api'][index]}`, name, port, health: 'stopped', stage: '未启动', durationSeconds: 0, candidates: 0, localOnly: true })),
    events: [], findings: [], reports: [],
  }
  await page.unroute('**/api/session')
  await page.route('**/api/session', async (route) => { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'e2e-token' }) }) })
  await page.route('**/api/dashboard', async (route) => { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(idleSnapshot) }) })
  await page.route('**/api/labs/**', async (route) => { calls.push(new URL(route.request().url()).pathname); await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ accepted: true }) }) })

  await page.goto('/')
  await page.getByRole('button', { name: '本地靶场', exact: true }).click()
  await page.getByRole('button', { name: '启动 DVWA' }).click()
  await expect(page.getByText(/dvwa 操作已提交/)).toBeVisible()
  await page.getByRole('button', { name: '重置 DVWA' }).click()
  await expect(page.getByText(/dvwa 操作已提交/)).toBeVisible()
  await page.getByRole('button', { name: '启动全部靶场' }).click()
  await expect(page.getByText('启动全部操作已提交，页面会显示逐个就绪状态。')).toBeVisible()
  expect(calls).toEqual(['/api/labs/dvwa/start', '/api/labs/dvwa/reset', '/api/labs/start-all'])
})

test('opens every local lab as its own task without external network contact', async ({ page }) => {
  const consoleErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('request', (request) => {
    if (new URL(request.url()).hostname !== '127.0.0.1') externalRequests.push(request.url())
  })

  await page.goto('/')
  await page.getByRole('button', { name: '本地靶场', exact: true }).click()
  for (const [lab, title, port] of localLabTasks) {
    const taskButton = page.getByRole('button', { name: `查看 ${lab} 任务` })
    await expect(taskButton).toBeVisible()
    await taskButton.click()
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
    await expect(page.getByText(port, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '返回靶场列表' }).click()
  }

  expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
  expect(externalRequests, externalRequests.join('\n')).toEqual([])
})

test('keeps draft input and reports a save failure when the backend is unavailable', async ({ page }) => {
  const externalRequests: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.hostname !== '127.0.0.1') externalRequests.push(request.url())
  })

  await page.goto('/')
  await page.getByRole('button', { name: '目标与授权' }).click()
  await page.getByRole('button', { name: '保存授权草稿' }).click()
  await expect(page.getByText('请填写目标 URL。', { exact: true })).toBeVisible()

  await page.getByLabel('项目名称').fill('示例授权项目')
  await page.getByLabel('目标 URL').fill('https://example.com/app')
  await page.getByLabel('允许主机名').fill('example.com')
  await page.getByLabel('允许端口').fill('443')
  await page.getByLabel('开始时间').fill('2026-08-27T09:00')
  await page.getByLabel('结束时间').fill('2026-08-27T18:00')
  await page.getByLabel('授权证明或规则说明').fill('项目规则允许在时间窗内进行低频测试。')
  await page.getByRole('button', { name: '保存授权草稿' }).click()
  await expect(page.getByRole('alert').filter({ hasText: '保存失败' })).toContainText('保存失败')
  await expect(page.getByLabel('项目名称')).toHaveValue('示例授权项目')
  await expect(page.getByText('授权草稿已保存', { exact: true })).toHaveCount(0)
  expect(externalRequests, externalRequests.join('\n')).toEqual([])
})

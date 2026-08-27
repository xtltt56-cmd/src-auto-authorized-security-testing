import { expect, test } from '@playwright/test'

const localLabTasks = [
  ['Juice Shop', 'Juice Shop · 本地任务', '127.0.0.1:3000'],
  ['DVWA', 'DVWA · 本地任务', '127.0.0.1:8081'],
  ['WebGoat', 'WebGoat · 本地任务', '127.0.0.1:8082'],
  ['VAmPI', 'VAmPI · 本地任务', '127.0.0.1:8083'],
  ['Business API', 'Business API · 本地任务', '127.0.0.1:8084'],
] as const

test('completes local task controls and opens a safe report view', async ({ page }) => {
  const consoleErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.hostname !== '127.0.0.1') externalRequests.push(request.url())
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: '安全测试控制台' })).toBeVisible()
  await expect(page.getByText(/真实目标不会自动执行/).first()).toBeVisible()
  await page.getByRole('button', { name: '本地靶场' }).click()
  for (const lab of ['Juice Shop', 'DVWA', 'WebGoat', 'VAmPI', 'Business API']) await expect(page.getByText(lab, { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '打开当前任务' }).click()
  await expect(page.getByRole('heading', { name: '实时事件' })).toBeVisible()
  await page.getByRole('button', { name: '暂停任务' }).click()
  await expect(page.getByText('已暂停', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '继续任务' }).click()
  await expect(page.getByText('运行中', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止任务' }).click()
  await expect(page.getByText('已取消', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /已处理授权夹具中的 42 个入口/ }).click()
  await expect(page.getByRole('heading', { name: '事件详情' })).toBeVisible()
  await page.getByRole('button', { name: '查看报告' }).click()
  await expect(page.getByRole('heading', { name: '候选漏洞与报告' })).toBeVisible()
  await page.getByRole('button', { name: '查看 juice-shop-summary.json' }).click()
  await expect(page.getByRole('heading', { name: '报告查看器' })).toBeVisible()
  await expect(page.getByText('脚本不会执行', { exact: true })).toBeVisible()

  expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
  expect(externalRequests, externalRequests.join('\n')).toEqual([])
})

test('opens every local lab as its own task without external network contact', async ({ page }) => {
  const consoleErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('request', (request) => {
    if (new URL(request.url()).hostname !== '127.0.0.1') externalRequests.push(request.url())
  })

  await page.goto('/')
  await page.getByRole('button', { name: '本地靶场' }).click()
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

test('validates and saves target scope without network contact', async ({ page }) => {
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
  await expect(page.getByText('授权草稿已保存', { exact: true })).toBeVisible()
  await expect(page.getByText('未访问目标', { exact: true })).toBeVisible()
  expect(externalRequests, externalRequests.join('\n')).toEqual([])
})

import { expect, test } from '@playwright/test'

const localLabNames = ['Juice Shop', 'DVWA', 'WebGoat', 'VAmPI', 'Business API'] as const

test.beforeEach(async ({ page }) => {
  await page.route('**/api/session', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })
})

test('keeps the Chinese console usable at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '安全测试控制台' })).toBeVisible()
  await expect(page.getByRole('button', { name: '本地靶场' })).toBeVisible()
  await expect(page.getByRole('main').getByText(/真实目标不会自动执行/)).toBeVisible()
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
})

test('renders every local lab task entry as a readable mobile card', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: '本地靶场' }).click()

  const matrix = page.locator('.lab-matrix-panel')
  await expect(matrix.locator('thead')).toBeHidden()
  for (const lab of localLabNames) {
    const taskButton = page.getByRole('button', { name: `查看 ${lab} 任务` })
    await taskButton.scrollIntoViewIfNeeded()
    await expect(taskButton).toBeVisible()
    expect((await taskButton.boundingBox())?.width).toBeGreaterThan(240)
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

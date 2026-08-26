import { expect, test } from '@playwright/test'

test('keeps the Chinese console usable at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '安全测试控制台' })).toBeVisible()
  await expect(page.getByRole('button', { name: '本地靶场' })).toBeVisible()
  await expect(page.getByRole('main').getByText(/真实目标不会自动执行/)).toBeVisible()
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
})

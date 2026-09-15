import fs from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { fixtureSnapshot } from '../../src/lib/fixtures'

const outputDir = path.resolve('..', 'validation', 'visual')

test('captures approved desktop and mobile console views', async ({ page }) => {
  await page.route('**/api/session', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'visual-fixture-token' }) }))
  await page.route('**/api/dashboard', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixtureSnapshot) }))
  fs.mkdirSync(outputDir, { recursive: true })
  const views = [
    { name: 'overview-1366x768', width: 1366, height: 768 },
    { name: 'overview-1920x1080', width: 1920, height: 1080 },
    { name: 'overview-390x844', width: 390, height: 844 },
  ]
  for (const view of views) {
    await page.setViewportSize({ width: view.width, height: view.height })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '安全测试控制台' })).toBeVisible()
    await page.screenshot({ path: path.join(outputDir, `${view.name}.png`), fullPage: true })
  }

  const labViews = [
    { name: 'labs-1366x900', width: 1366, height: 900 },
    { name: 'labs-390x844', width: 390, height: 844 },
  ]
  for (const view of labViews) {
    await page.setViewportSize({ width: view.width, height: view.height })
    await page.goto('/')
    await page.getByRole('button', { name: '本地靶场', exact: true }).click()
    await expect(page.getByRole('button', { name: '查看 Juice Shop 任务' })).toBeVisible()
    await page.screenshot({ path: path.join(outputDir, `${view.name}.png`), fullPage: true })
  }

  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto('/')
  await page.getByRole('button', { name: '本地靶场', exact: true }).click()
  await page.getByRole('button', { name: '查看 Juice Shop 任务' }).click()
  await expect(page.getByRole('heading', { name: 'Juice Shop · 本地任务' })).toBeVisible()
  await page.screenshot({ path: path.join(outputDir, 'juice-shop-task-1366x900.png'), fullPage: true })
})

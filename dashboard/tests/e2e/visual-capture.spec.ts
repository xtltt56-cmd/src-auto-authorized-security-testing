import fs from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'

const outputDir = path.resolve('..', 'validation', 'visual')

test('captures approved desktop and mobile console views', async ({ page }) => {
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
})

import path from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const viteEntry = path.resolve('node_modules/vite/bin/vite.js')

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/e2e-results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    locale: 'zh-CN',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  webServer: {
    command: `${JSON.stringify(process.execPath)} ${JSON.stringify(viteEntry)} --host 127.0.0.1 --port 4173`,
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
  ],
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AISettingsPage } from './AISettingsPage'

it('opens settings only on click and reports success', async () => {
  const open = vi.fn().mockResolvedValue(undefined)
  render(<AISettingsPage openSettings={open} />)
  expect(open).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '打开 OpenRouter 密钥与模型设置' }))
  expect(open).toHaveBeenCalledTimes(1)
  expect(await screen.findByRole('status')).toHaveTextContent('已请求打开')
})

it('shows useful restart instruction on unavailable local API', async () => {
  render(<AISettingsPage openSettings={async () => { throw new Error('old api') }} />)
  await userEvent.click(screen.getByRole('button', { name: '打开 OpenRouter 密钥与模型设置' }))
  expect(await screen.findByRole('status')).toHaveTextContent('重新启动')
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AISettingsPage } from './AISettingsPage'
import { createFixtureRepository } from '../lib/taskRepository'

it('saves a key inline without opening another window or echoing the key', async () => {
  const repository = createFixtureRepository()
  repository.saveAIProvider = vi.fn().mockResolvedValue({ id: 'deepseek', displayName: 'DeepSeek V4.1 Flash', model: 'deepseek-flash', officialModel: 'deepseek-flash', keySaved: true, endpointHost: 'api.deepseek.com' })
  render(<AISettingsPage repository={repository} />)
  expect(await screen.findByText(/推荐值：/)).toBeVisible()
  await userEvent.type(screen.getByLabelText('API 密钥'), 'synthetic-ui-key')
  await userEvent.click(screen.getByRole('button', { name: '保存设置' }))
  expect(repository.saveAIProvider).toHaveBeenCalledWith('deepseek', { apiKey: 'synthetic-ui-key', model: 'deepseek-flash' })
  expect(await screen.findByRole('status')).toHaveTextContent('已加密保存')
  expect(screen.getByLabelText('API 密钥')).toHaveValue('')
})

it('requires a one-time checkbox before a real connection test', async () => {
  const repository = createFixtureRepository()
  repository.listAIProviders = vi.fn().mockResolvedValue([
    { id: 'deepseek', displayName: 'DeepSeek V4.1 Flash', model: 'deepseek-flash', officialModel: 'deepseek-flash', keySaved: true, endpointHost: 'api.deepseek.com' },
  ])
  repository.testAIProvider = vi.fn().mockResolvedValue({ ok: true, code: 'reachable_model_available' })
  render(<AISettingsPage repository={repository} />)
  const testButton = await screen.findByRole('button', { name: '测试连接' })
  expect(testButton).toBeDisabled()
  await userEvent.click(screen.getByLabelText(/允许本次联网测试/))
  expect(testButton).toBeEnabled()
  await userEvent.click(testButton)
  expect(repository.testAIProvider).toHaveBeenCalledWith('deepseek')
  expect(await screen.findByRole('status')).toHaveTextContent('连接成功')
})

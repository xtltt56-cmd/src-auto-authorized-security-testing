import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AgentPage } from './AgentPage'
import { createFixtureRepository } from '../lib/taskRepository'
import { fixtureSnapshot } from '../lib/fixtures'

it('does not start inference on mount and requires manual enable', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: false, remoteSessionEnabled: false, activeId: null, runs: [] })
  repository.enableAgent = vi.fn().mockResolvedValue({ enabled: true })
  repository.startAgent = vi.fn().mockResolvedValue({ accepted: true, id: 'one' })
  render(<AgentPage repository={repository} snapshot={fixtureSnapshot} onOpenReport={() => undefined} />)
  await screen.findByRole('button', { name: '开始受控任务' })
  expect(repository.startAgent).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '开始受控任务' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /启用本次受控 Agent/ }))
  expect(repository.enableAgent).toHaveBeenCalledWith(true)
})

it('blocks cloud selection when startup gate is off', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: false, activeId: null, runs: [] })
  render(<AgentPage repository={repository} snapshot={fixtureSnapshot} onOpenReport={() => undefined} />)
  await screen.findByRole('button', { name: '开始受控任务' })
  expect(screen.getByRole('option', { name: /DeepSeek V4.1 Flash/ })).toBeDisabled()
  expect(screen.getByText(/本次启动禁止云端 AI/)).toBeVisible()
})

it('keeps the new cloud loop disabled even with session consent', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: true, cloudAgentAvailable: false, activeId: null, runs: [] })
  render(<AgentPage repository={repository} snapshot={fixtureSnapshot} onOpenReport={() => undefined} />)
  await screen.findByText(/DeepSeek Agent 配置或计价未就绪/)
  expect(screen.getByRole('option', { name: /DeepSeek V4.1 Flash/ })).toBeDisabled()
  expect(screen.getByRole('button', { name: '开始受控任务' })).toBeDisabled()
})

it('defaults to DeepSeek but requires per-task cloud consent without automatic calls', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: true, cloudAgentAvailable: true, activeId: null, runs: [] })
  repository.startAgent = vi.fn().mockResolvedValue({ accepted: true, id: 'cloud-one' })
  render(<AgentPage repository={repository} snapshot={fixtureSnapshot} onOpenReport={() => undefined} />)
  await screen.findByText(/每次调用前持久化预留预算/)
  expect(screen.getByRole('combobox', { name: '决策模型' })).toHaveValue('deepseek')
  expect(repository.startAgent).not.toHaveBeenCalled()
  const start = screen.getByRole('button', { name: '开始受控任务' })
  expect(start).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /同意本任务向所选云端模型/ }))
  expect(start).toBeEnabled()
  await userEvent.click(start)
  expect(repository.startAgent).toHaveBeenCalledWith(expect.objectContaining({ mode: 'local-assessment', provider: 'deepseek', allowCloud: true }))
  expect(screen.getByRole('checkbox', { name: /同意本任务向所选云端模型/ })).not.toBeChecked()
})

it('shows resource pause and blocks resuming an unavailable lab', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: false, activeId: null, runs: [{ id: 'limited', labId: 'business-api', mode: 'api-permissions', provider: 'local', state: 'paused', reason: 'resource_limit', steps: 0, requests: 0, modelCalls: 1, tokens: 567, elapsedSeconds: 125, candidates: 0, reportId: '', createdAt: '2026-10-04', trace: [], observations: [], resourceCheck: { known: true, memory_gb: 28.36, max_memory_gb: 20, cpu_percent: 44.83 } }] })
  render(<AgentPage repository={repository} snapshot={{ ...fixtureSnapshot, labs: fixtureSnapshot.labs.map(x => ({ ...x, health: 'unavailable' as const })) }} onOpenReport={() => undefined} />)
  await screen.findByText(/28.36 GB/)
  expect(screen.getByRole('button', { name: '人工续接' })).toBeDisabled()
  expect(screen.getByText(/模型简述不是事实裁决/)).toBeVisible()
})

it('offers only candidates in the selected local lab scope', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: false, remoteSessionEnabled: false, activeId: null, runs: [] })
  const candidate = { id: 'one', title: '同靶场候选', url: 'http://127.0.0.1:8084/orders', severity: 'high' as const, source: 'test', state: '待人工复核' as const, summary: '', evidence: '', prerequisites: [], impact: '' }
  repository.getArtifacts = vi.fn().mockResolvedValue({ reports: [], findings: [candidate, { ...candidate, id: 'other', title: '其他靶场候选', url: 'http://127.0.0.1:3000/api' }] })
  render(<AgentPage repository={repository} snapshot={{ ...fixtureSnapshot, labs: fixtureSnapshot.labs.map(x => ({ ...x, openUrl: `http://127.0.0.1:${x.port}/` })) }} onOpenReport={() => undefined} />)
  await userEvent.selectOptions(screen.getByRole('combobox', { name: '任务模式' }), 'candidate-review')
  await screen.findByRole('option', { name: '同靶场候选' })
  expect(screen.queryByRole('option', { name: '其他靶场候选' })).toBeNull()
})

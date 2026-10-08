import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { createFixtureRepository } from '../lib/taskRepository'
import { BusinessExecutionPanel } from './BusinessExecutionPanel'
import type { BusinessPreparationRow, AgentRun } from '../lib/types'

const row = { id: 'business-test', revision: 'revision', targetId: 'custom-test', targetRevision: 'target-r',
  cases: [{ id: 'object-1', name: '合成对象', path: '/objects/a', owner: 'account-a', expected: { 'account-a': true, 'account-b': false, administrator: true, anonymous: false } }],
  sessions: {}, isolation: { dataLabel: 'test', storageLabel: 'test', resetNote: 'manual', confirmIsolatedData: true, confirmTestAccounts: true, confirmNoProductionSecrets: true },
  executionAuthorized: false, isolationVerified: false } satisfies BusinessPreparationRow
afterEach(() => vi.restoreAllMocks())
const setup = (remote = false) => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: false, remoteSessionEnabled: remote, cloudAgentAvailable: remote, activeId: null, runs: [] })
  repository.previewBusiness = vi.fn().mockResolvedValue({ approvalId: 'approval', origin: 'http://127.0.0.1:8765', applicationIdentity: 'identity', requestCount: 4, objectCount: 1, controls: false, networkContact: false, modelCalls: 0, expiresAt: new Date(Date.now()+600000).toISOString(), mode: 'standard', provider: 'none' })
  repository.startBusiness = vi.fn().mockResolvedValue({ id: 'run', accepted: true })
  repository.enableAgent = vi.fn().mockResolvedValue({ enabled: true })
  render(<BusinessExecutionPanel repository={repository} preparation={row} />)
  return repository
}

it('never executes on mount or after preview; requires two separate confirmations', async () => {
  const repository = setup()
  await screen.findByText(/本次启动未授权云端/)
  expect(repository.previewBusiness).not.toHaveBeenCalled()
  expect(repository.startBusiness).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '生成业务执行审批' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /本次仅访问已保存规格/ }))
  await userEvent.click(screen.getByRole('button', { name: '生成业务执行审批' }))
  await screen.findByText(/预计最多 4 次/)
  expect(repository.previewBusiness).toHaveBeenCalledWith(expect.objectContaining({ id: row.id, revision: row.revision, confirmIsolation: true, mode: 'standard', provider: 'none', allowCloud: false, controls: false }))
  expect(repository.startBusiness).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '启动本次业务验证' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /确认上述执行审批/ }))
  await userEvent.click(screen.getByRole('button', { name: '启动本次业务验证' }))
  await screen.findByText(/真实业务任务已提交/)
  expect(repository.startBusiness).toHaveBeenCalledWith({ approvalId: 'approval', confirmStart: true })
  expect(screen.getByRole('checkbox', { name: /本次仅访问已保存规格/ })).not.toBeChecked()
})

it('changing mode clears approval and disabled cloud cannot be selected for execution', async () => {
  const repository = setup()
  await screen.findByText(/本次启动未授权云端/)
  await userEvent.click(screen.getByRole('checkbox', { name: /本次仅访问已保存规格/ }))
  await userEvent.click(screen.getByRole('button', { name: '生成业务执行审批' }))
  await screen.findByText(/预计最多 4 次/)
  await userEvent.selectOptions(screen.getByLabelText('业务验证方式'), 'agent')
  expect(screen.queryByText(/预计最多 4 次/)).toBeNull()
  expect(screen.getByRole('button', { name: '生成业务执行审批' })).toBeDisabled()
  expect(screen.getByRole('checkbox', { name: /本次调用 DeepSeek/ })).toBeDisabled()
  expect(repository.startBusiness).not.toHaveBeenCalled()
})

it('displays real role evidence, opens full report and can request cancellation', async () => {
  const repository = createFixtureRepository()
  const run = { id: 'business-run', labId: 'custom-test', targetType: 'business_local', mode: 'business-assessment', provider: 'deepseek', state: 'running', reason: 'tool_executing', origin: 'http://127.0.0.1:8765', steps: 1, requests: 4, modelCalls: 1, tokens: 123,
    usageEstimated: false, elapsedSeconds: 3, candidates: 1, reportId: 'reports/agent/business-run.md', createdAt: '2026-10-08', trace: [],
    observations: [{ id: 'o1', action: 'compare_business_object', reference: 'object-001', summary: '四角色对照', path: '/objects/a', baselineValid: true, statuses: { 'account-a': 200, 'account-b': 200, administrator: 200, anonymous: 403 },
      expected: { 'account-a': true, 'account-b': false, administrator: true, anonymous: false }, equivalent: { 'account-a': true, 'account-b': true, administrator: true, anonymous: false } }] } satisfies AgentRun
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: true, activeId: run.id, ownedActiveId: run.id, runs: [run] })
  repository.cancelAgent = vi.fn().mockResolvedValue(undefined)
  repository.downloadReport = vi.fn().mockResolvedValue({ id: run.reportId, relativePath: run.reportId, name: 'business-run.md', content: '真实业务完整证据', sizeBytes: 100, kind: 'markdown', truncated: false })
  render(<BusinessExecutionPanel repository={repository} preparation={row} />)
  await screen.findByText('权限异常候选 · 待复核')
  expect(screen.getByText('权限异常候选 · 待复核')).toHaveAttribute('data-label', '结果')
  await userEvent.click(screen.getByRole('button', { name: '查看业务完整报告' }))
  await screen.findByText('真实业务完整证据')
  expect(repository.downloadReport).toHaveBeenCalledWith(run.reportId)
  await userEvent.click(screen.getByRole('button', { name: '关闭' }))
  await userEvent.click(screen.getByRole('button', { name: '停止业务验证' }))
  await screen.findByText(/已请求停止/)
  expect(repository.cancelAgent).toHaveBeenCalledWith(run.id)
  expect(screen.getByRole('button', { name: '生成业务执行审批' })).toBeDisabled()
})

it('cloud usage requires startup gate, session enable and explicit per-task consent', async () => {
  const repository = setup(true)
  await userEvent.selectOptions(screen.getByLabelText('业务验证方式'), 'agent')
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: true, cloudAgentAvailable: true, activeId: null, runs: [] })
  await userEvent.click(screen.getByRole('button', { name: '启用本次 Agent' }))
  expect(repository.enableAgent).toHaveBeenCalledTimes(1)
  expect(repository.enableAgent).toHaveBeenCalledWith(true)
  await screen.findByRole('button', { name: '关闭本次 Agent' })
  await userEvent.click(screen.getByRole('checkbox', { name: /本次仅访问已保存规格/ }))
  expect(screen.getByRole('button', { name: '生成业务执行审批' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /本次调用 DeepSeek/ }))
  await userEvent.click(screen.getByRole('button', { name: '生成业务执行审批' }))
  await screen.findByText(/预计最多 4 次/)
  expect(repository.previewBusiness).toHaveBeenCalledWith(expect.objectContaining({ mode: 'agent', provider: 'deepseek', allowCloud: true }))
  await userEvent.selectOptions(screen.getByLabelText('业务决策模型'), 'local')
  expect(screen.getByRole('checkbox', { name: /本次调用 DeepSeek/ })).not.toBeChecked()
  expect(screen.queryByText(/预计最多 4 次/)).toBeNull()
})

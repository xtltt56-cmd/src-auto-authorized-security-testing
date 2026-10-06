import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { LocalApplicationPage } from './LocalApplicationPage'
import { createFixtureRepository } from '../lib/taskRepository'

const setup = (remote = false) => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: true, remoteSessionEnabled: remote, cloudAgentAvailable: true, activeId: null, runs: [] })
  repository.previewLocalApplication = vi.fn().mockResolvedValue({ approvalId: 'approved', origin: 'http://127.0.0.1:8765', scopeDigest: 'scope', planDigest: 'plan', applicationIdentity: 'instance', networkContact: false, modelCalls: 0, mode: 'standard', provider: 'none', expiresAt: '2099-01-01T00:00:00Z', requests: [{ path: '/', method: 'GET' }, { path: '/api/health', method: 'GET' }] })
  repository.startLocalApplication = vi.fn().mockResolvedValue({ accepted: true, id: 'actual' })
  render(<LocalApplicationPage repository={repository} onOpenReport={() => undefined} />)
  return repository
}

it('new blank draft clears target fields and all previous approvals', async () => {
  setup()
  await userEvent.type(screen.getByLabelText('本机服务入口'), 'http://127.0.0.1:8765')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认拥有本机应用/ }))
  await userEvent.click(screen.getByRole('button', { name: '核对审批摘要' }))
  await screen.findByText(/尚未发送目标请求/)
  await userEvent.click(screen.getByRole('button', { name: '新建空白草稿' }))
  expect(screen.getByLabelText('本机服务入口')).toHaveValue('')
  expect(screen.getByRole('checkbox', { name: /确认拥有本机应用/ })).not.toBeChecked()
  expect(screen.queryByRole('button', { name: '开始本机审查' })).toBeNull()
})


it('has an in-platform draft library and loading does not enable authorization', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: false, remoteSessionEnabled: false, activeId: null, runs: [] })
  repository.listLocalTargets = vi.fn().mockResolvedValue({ targets: [{ id: 'custom-synthetic', name: '合成靶场', kind: 'custom_lab', origin: 'http://127.0.0.1:8765', paths: ['/health'], excluded: ['/reset'], method: 'GET', profile: 'readonly-baseline-v1', revision: '1', confirmed: false, allowCloud: false }] })
  repository.previewLocalApplication = vi.fn()
  render(<LocalApplicationPage repository={repository} onOpenReport={() => undefined} />)
  await userEvent.click(await screen.findByRole('button', { name: '载入 合成靶场' }))
  expect(screen.getByLabelText('本机服务入口')).toHaveValue('http://127.0.0.1:8765')
  expect(screen.getByRole('checkbox', { name: /确认拥有本机应用/ })).not.toBeChecked()
  expect(repository.previewLocalApplication).not.toHaveBeenCalled()
})

it('never probes or starts on mount, and binds preview to explicit authorization', async () => {
  const repository = setup()
  await screen.findByRole('button', { name: '核对审批摘要' })
  expect(repository.previewLocalApplication).not.toHaveBeenCalled()
  expect(repository.startLocalApplication).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('本机服务入口'), 'http://127.0.0.1:8765')
  expect(screen.getByRole('button', { name: '核对审批摘要' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /确认拥有本机应用的测试授权/ }))
  await userEvent.click(screen.getByRole('button', { name: '核对审批摘要' }))
  await screen.findByText(/尚未发送目标请求/)
  expect(repository.previewLocalApplication).toHaveBeenCalledWith(expect.objectContaining({ mode: 'standard', provider: 'none', allowCloud: false, scope: expect.objectContaining({ automation_allowed: true, allowed_paths: ['/', '/api/health'], allowed_methods: ['GET'] }) }))
  expect(screen.getByRole('button', { name: '开始本机审查' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /确认按以上快照开始/ }))
  await userEvent.click(screen.getByRole('button', { name: '开始本机审查' }))
  expect(repository.startLocalApplication).toHaveBeenCalledWith({ approvalId: 'approved', confirmStart: true })
})

it('editing a field invalidates the earlier approval, and cloud has a startup hard gate', async () => {
  const repository = setup()
  await userEvent.type(screen.getByLabelText('本机服务入口'), 'http://127.0.0.1:8765')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认拥有本机应用的测试授权/ }))
  await userEvent.click(screen.getByRole('button', { name: '核对审批摘要' }))
  await screen.findByText(/尚未发送目标请求/)
  await userEvent.type(screen.getByLabelText('允许路由（每行一条）'), '\n/new')
  expect(screen.queryByRole('button', { name: '开始本机审查' })).toBeNull()
  await userEvent.selectOptions(screen.getByLabelText('检查方式'), 'agent')
  expect(screen.getByRole('button', { name: '核对审批摘要' })).toBeDisabled()
  expect(screen.getByText(/本次启动禁止云端 AI/)).toBeVisible()
  expect(repository.startLocalApplication).not.toHaveBeenCalled()
})

it('renders real persisted observations and opens the linked report', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: false, remoteSessionEnabled: false, activeId: null, runs: [{ id: 'real', labId: 'owned', targetType: 'local_web', origin: 'http://127.0.0.1:8765', mode: 'local-web-standard', provider: 'none', state: 'completed', reason: 'readonly_recipes_completed', steps: 1, requests: 1, modelCalls: 0, tokens: 0, candidates: 0, elapsedSeconds: 4.3, reportId: 'reports/local-app/real.md', createdAt: '2026-10-06', observations: [{ id: 'o1', action: 'inspect_local_route', reference: 'route-001', path: '/', method: 'GET', status_code: 200, summary: 'actual' }], trace: [] }] })
  const open = vi.fn()
  render(<LocalApplicationPage repository={repository} onOpenReport={open} />)
  await userEvent.click(await screen.findByRole('button', { name: '查看完整报告' }))
  expect(open).toHaveBeenCalledWith('reports/local-app/real.md')
  expect(screen.getByText('200')).toBeVisible()
})

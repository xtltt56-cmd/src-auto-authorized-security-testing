import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { createFixtureRepository } from '../lib/taskRepository'
import type { BusinessPreparationRow, BusinessPreparationSnapshot } from '../lib/types'
import { BusinessPreparationPage } from './BusinessPreparationPage'

const target = { id: 'custom-synthetic', name: '隔离合成目标', kind: 'custom_lab' as const, origin: 'http://127.0.0.1:8765', paths: ['/objects/a'], excluded: ['/reset'], method: 'GET', profile: 'readonly-baseline-v1', revision: 'revision', confirmed: false as const, allowCloud: false as const }
afterEach(() => vi.restoreAllMocks())
const setup = (initial?: BusinessPreparationSnapshot) => {
  const repository = createFixtureRepository()
  repository.getBusinessPreparation = vi.fn().mockResolvedValue(initial ?? { targets: [target], preparations: [], sessions: [], executionAvailable: false })
  repository.saveBusinessPreparation = vi.fn().mockImplementation(value => Promise.resolve({ ...value, id: 'prepared', revision: 'prepared-revision', executionAuthorized: false, isolationVerified: false }))
  repository.saveBusinessSession = vi.fn().mockResolvedValue({ saved: true })
  render(<BusinessPreparationPage repository={repository} />)
  return repository
}

it('preparation never starts a task and declarations must be explicit', async () => {
  const repository = setup()
  await screen.findByRole('option', { name: /隔离合成目标/ })
  expect(repository.saveBusinessPreparation).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: /开始.*验证/ })).toBeNull()
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), target.id)
  expect(screen.getByRole('button', { name: '保存业务验证草稿' })).toBeDisabled()
  expect(screen.getByText(/L4-A 只做准备/)).toBeVisible()
})

it('saves an explicit four-role permission specification, not an execution approval', async () => {
  const repository = setup()
  await screen.findByRole('option', { name: /隔离合成目标/ })
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), target.id)
  await userEvent.type(screen.getByLabelText('合成数据库标识'), 'synthetic-db')
  await userEvent.type(screen.getByLabelText('隔离文件目录标识'), 'synthetic-files')
  await userEvent.type(screen.getByLabelText('人工重置说明'), '人工清空合成数据')
  for (const text of [/确认数据与生产隔离/, /确认仅使用独立测试账号/, /确认环境与说明中没有生产密钥/]) await userEvent.click(screen.getByRole('checkbox', { name: text }))
  await userEvent.type(screen.getByLabelText('对象 1 名称'), '账号 A 的合成对象')
  await userEvent.selectOptions(screen.getByLabelText('对象 1 所属角色'), 'account-b')
  await userEvent.selectOptions(screen.getByLabelText('对象 1 所属角色'), 'account-a')
  await userEvent.selectOptions(screen.getByLabelText('对象 1 路由'), '/objects/a')
  await userEvent.click(screen.getByRole('checkbox', { name: '对象 1 · 测试账号 A预期允许读取' }))
  await userEvent.click(screen.getByRole('checkbox', { name: '对象 1 · 测试管理员预期允许读取' }))
  await userEvent.click(screen.getByRole('button', { name: /增加对象/ }))
  await userEvent.type(screen.getByLabelText('对象 2 名称'), '临时对象')
  await userEvent.click(screen.getByRole('button', { name: '移除对象 2' }))
  await userEvent.click(screen.getByRole('button', { name: '保存业务验证草稿' }))
  await screen.findByText(/业务草稿已保存/)
  expect(repository.saveBusinessPreparation).toHaveBeenCalledWith(expect.objectContaining({ targetId: target.id, targetRevision: target.revision,
    cases: [expect.objectContaining({ path: '/objects/a', owner: 'account-a', expected: { 'account-a': true, 'account-b': false, administrator: true, anonymous: false } })], sessions: {} }))
  expect(screen.getByRole('checkbox', { name: /确认数据与生产隔离/ })).not.toBeChecked()
  await userEvent.click(screen.getByRole('button', { name: '新建业务草稿' }))
  expect(screen.getByLabelText('合成数据库标识')).toHaveValue('')
})

const prepared: BusinessPreparationRow = { id: 'prepared', revision: 'old', targetId: target.id, targetRevision: target.revision,
  isolation: { dataLabel: 'synthetic-db', storageLabel: 'synthetic-dir', resetNote: '人工重置', confirmIsolatedData: true, confirmTestAccounts: true, confirmNoProductionSecrets: true },
  cases: [{ id: 'object-1', name: '合成对象', path: '/objects/a', owner: 'account-a', expected: { 'account-a': true, 'account-b': false, administrator: true, anonymous: false } }], sessions: {}, executionAuthorized: false, isolationVerified: false }

it('loading drafts does not restore declarations and preview does not claim a scan', async () => {
  const repository = setup({ targets: [target], preparations: [prepared], sessions: [], executionAvailable: false })
  repository.previewBusinessPreparation = vi.fn().mockResolvedValue({ id: 'prepared', blockers: [], readyForNextStage: true, executionAvailable: false, executionAuthorized: false, isolationVerified: false, networkRequests: 0, modelCalls: 0, cases: 1 })
  await screen.findByRole('button', { name: '载入草稿' })
  expect(document.querySelector('.business-draft-row')).toHaveTextContent(target.origin)
  expect(document.querySelector('.business-draft-row')).toHaveTextContent(prepared.id)
  await userEvent.click(screen.getByRole('button', { name: '载入草稿' }))
  expect(screen.getByLabelText('合成数据库标识')).toHaveValue('synthetic-db')
  expect(screen.getByRole('checkbox', { name: /确认数据与生产隔离/ })).not.toBeChecked()
  expect(screen.getByRole('button', { name: '保存业务验证草稿' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: '离线核对' }))
  await screen.findByText('准备资料齐全 · 尚未执行验证')
  expect(screen.queryByRole('button', { name: /开始.*验证/ })).toBeNull()
  expect(repository.previewBusinessPreparation).toHaveBeenCalledWith({ id: 'prepared' })
})

it('shows actionable blockers and permits deleting only the selected draft', async () => {
  const repository = setup({ targets: [target], preparations: [prepared], sessions: [], executionAvailable: false })
  repository.previewBusinessPreparation = vi.fn().mockResolvedValue({ id: 'prepared', blockers: ['session_required:account-a', 'session_expired:administrator', 'target_changed'], readyForNextStage: false, networkRequests: 0, modelCalls: 0, cases: 1 })
  repository.deleteBusinessPreparation = vi.fn().mockResolvedValue({ deleted: true })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  await screen.findByRole('button', { name: '离线核对' })
  await userEvent.click(screen.getByRole('button', { name: '离线核对' }))
  await screen.findByText('尚未绑定会话 · 测试账号 A')
  expect(screen.getByText('会话已过期 · 测试管理员')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '删除草稿' }))
  expect(repository.deleteBusinessPreparation).toHaveBeenCalledWith({ id: 'prepared' })
  expect(repository.deleteLocalTarget).toBeUndefined()
})

it('saves and binds sessions without retaining input, then deletes only the named session', async () => {
  const session = { name: 'isolated-b', role: 'account-b', targetId: target.id, origin: target.origin, expiresAt: '2099-01-01T00:00:00Z', expired: false, revision: 'r', bound: true as const }
  const repository = setup({ targets: [target], preparations: [], sessions: [session], executionAvailable: false })
  repository.deleteBusinessSession = vi.fn().mockResolvedValue({ deleted: true })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  await screen.findByRole('option', { name: /隔离合成目标/ })
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), target.id)
  await userEvent.selectOptions(screen.getByLabelText('测试角色'), 'account-b')
  await userEvent.selectOptions(screen.getByLabelText('凭据类型'), 'Cookie')
  await userEvent.type(screen.getByLabelText('会话名称'), 'isolated-b')
  await userEvent.type(screen.getByLabelText('会话凭据（不回显）'), 'sid=synthetic-only')
  await userEvent.clear(screen.getByLabelText('会话有效至'))
  await userEvent.type(screen.getByLabelText('会话有效至'), '2099-01-01T10:00')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认仅使用该目标的隔离测试账号/ }))
  expect(screen.getByRole('button', { name: '加密保存会话' })).toBeDisabled()
  const tomorrow = new Date(Date.now() + 86400000)
  fireEvent.change(screen.getByLabelText('会话有效至'), { target: { value: new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60000).toISOString().slice(0, 16) } })
  await userEvent.click(screen.getByRole('button', { name: '加密保存会话' }))
  expect(repository.saveBusinessSession).toHaveBeenCalledWith(expect.objectContaining({ role: 'account-b', headers: { Cookie: 'sid=synthetic-only' }, confirmTestAccount: true }))
  expect(screen.getByLabelText('会话凭据（不回显）')).toHaveValue('')
  await userEvent.selectOptions(screen.getByLabelText('测试账号 B的已存会话'), 'isolated-b')
  expect(screen.getByLabelText('测试账号 B的已存会话')).toHaveValue('isolated-b')
  await userEvent.click(screen.getByRole('button', { name: '删除会话' }))
  expect(repository.deleteBusinessSession).toHaveBeenCalledWith({ name: 'isolated-b', targetId: target.id })
})

it('an owned app must distinguish its production origin', async () => {
  setup({ targets: [{ ...target, kind: 'owned_app' }], preparations: [], sessions: [], executionAvailable: false })
  await screen.findByRole('option', { name: /隔离合成目标/ })
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), target.id)
  await userEvent.type(screen.getByLabelText('生产实例回环入口（仅用于区分）'), 'http://127.0.0.1:8766')
  expect(screen.getByRole('button', { name: '保存业务验证草稿' })).toBeDisabled()
})

it('changing target clears transient credentials and isolated declarations', async () => {
  setup()
  await screen.findByRole('option', { name: /隔离合成目标/ })
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), target.id)
  await userEvent.type(screen.getByLabelText('会话凭据（不回显）'), 'synthetic-token')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认数据与生产隔离/ }))
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), '')
  expect(screen.getByLabelText('会话凭据（不回显）')).toHaveValue('')
  expect(screen.getByRole('checkbox', { name: /确认数据与生产隔离/ })).not.toBeChecked()
  expect(localStorage.length).toBe(0)
})

it('never exposes exception bodies or a cached secret on session save failure', async () => {
  const repository = setup()
  repository.saveBusinessSession = vi.fn().mockRejectedValue(new Error('synthetic-secret-must-not-render'))
  await screen.findByRole('option', { name: /隔离合成目标/ })
  await userEvent.selectOptions(screen.getByLabelText('隔离目标'), target.id)
  await userEvent.type(screen.getByLabelText('会话名称'), 'isolated-a')
  await userEvent.type(screen.getByLabelText('会话凭据（不回显）'), 'synthetic-secret-must-not-render')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认仅使用该目标的隔离测试账号/ }))
  await userEvent.click(screen.getByRole('button', { name: '加密保存会话' }))
  await screen.findByText(/会话未保存/)
  expect(screen.getByLabelText('会话凭据（不回显）')).toHaveValue('')
  expect(screen.queryByText('synthetic-secret-must-not-render')).toBeNull()
})

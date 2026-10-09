import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { createFixtureRepository } from '../lib/taskRepository'
import { SourceAuditPage } from './SourceAuditPage'
afterEach(cleanup)

it('does not describe a cancelled terminal task as still analysing', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ activeId: null, runs: [{
    id: 'cancelled-real', targetType: 'source_audit', directory: 'D:\\Synthetic', state: 'cancelled',
    reason: 'cancel_requested', candidates: 0, modelCalls: 0, requests: 0, elapsedSeconds: 2,
  }] })
  render(<SourceAuditPage repository={repository} onOpenReport={() => undefined} />)
  expect(await screen.findByText('未完成分析')).toBeInTheDocument()
  expect(screen.queryByText('分析中')).toBeNull()
})

it('does not replay an accepted scan when the immediate status refresh fails', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn()
    .mockResolvedValueOnce({ activeId: null, remoteSessionEnabled: false, cloudAgentAvailable: false, runs: [] })
    .mockRejectedValue(new Error('disconnected'))
  repository.previewSourceAudit = vi.fn().mockResolvedValue({ approvalId: 'a', directory: 'D:\\Synthetic', files: 1, bytes: 50, excluded: {} })
  repository.startSourceAudit = vi.fn().mockResolvedValue({ accepted: true, id: 'real' })
  render(<SourceAuditPage repository={repository} onOpenReport={() => undefined} />)
  await userEvent.type(screen.getByLabelText('源码目录绝对路径'), 'D:\\Synthetic')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认拥有此目录/ }))
  await userEvent.click(screen.getByRole('checkbox', { name: /允许将批准文件临时复制/ }))
  await userEvent.click(screen.getByRole('button', { name: '核对源码快照' }))
  await userEvent.click(await screen.findByRole('checkbox', { name: /确认按批准快照/ }))
  await userEvent.click(screen.getByRole('button', { name: '开始源码审查' }))
  expect(await screen.findByText(/任务已提交，但状态连接暂时中断/)).toBeInTheDocument()
  expect(repository.startSourceAudit).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button', { name: '开始源码审查' })).toBeNull()
})

it('cloud summary review requires startup consent and remains off by default', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ activeId: null, remoteSessionEnabled: false, cloudAgentAvailable: true, runs: [] })
  repository.previewSourceAudit = vi.fn().mockResolvedValue({ approvalId: 'a', directory: 'D:\\Synthetic', files: 1, bytes: 50, excluded: {}, fileList: ['app.py'], exclusions: [{ path: 'site.min.js', reason: 'bundled_javascript' }] })
  repository.startSourceAudit = vi.fn().mockResolvedValue({ accepted: true, id: 'real' })
  render(<SourceAuditPage repository={repository} onOpenReport={() => undefined} />)
  await userEvent.type(screen.getByLabelText('源码目录绝对路径'), 'D:\\Synthetic')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认拥有此目录/ }))
  await userEvent.click(screen.getByRole('checkbox', { name: /允许将批准文件临时复制/ }))
  await userEvent.click(screen.getByRole('button', { name: '核对源码快照' }))
  expect(await screen.findByRole('checkbox', { name: /同意本任务将匿名规则/ })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /确认按批准快照/ }))
  await userEvent.click(screen.getByRole('button', { name: '开始源码审查' }))
  expect(repository.startSourceAudit).toHaveBeenCalledWith({ approvalId: 'a', confirmStart: true, allowCloud: false })
})

it('requires separate read and snapshot consent; edits invalidate approvals; mount never scans', async () => {
  const repository = createFixtureRepository()
  repository.getAgent = vi.fn().mockResolvedValue({ activeId: null, enabled: false, remoteSessionEnabled: false, runs: [] })
  repository.previewSourceAudit = vi.fn().mockResolvedValue({ approvalId: 'snapshot', digest: 'hash', directory: 'D:\\Synthetic', languages: ['python'], files: 1, bytes: 50, excluded: {}, expiresAt: '2099' })
  repository.startSourceAudit = vi.fn().mockResolvedValue({ accepted: true, id: 'actual' })
  render(<SourceAuditPage repository={repository} onOpenReport={() => undefined} />)
  expect(repository.previewSourceAudit).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('源码目录绝对路径'), 'D:\\Synthetic')
  await userEvent.click(screen.getByRole('checkbox', { name: /确认拥有此目录/ }))
  expect(screen.getByRole('button', { name: '核对源码快照' })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /允许将批准文件临时复制/ }))
  await userEvent.click(screen.getByRole('button', { name: '核对源码快照' }))
  await screen.findByText(/快照摘要：hash/)
  await userEvent.type(screen.getByLabelText('源码目录绝对路径'), '-changed')
  expect(screen.queryByRole('button', { name: '开始源码审查' })).toBeNull()
  expect(repository.startSourceAudit).not.toHaveBeenCalled()
})

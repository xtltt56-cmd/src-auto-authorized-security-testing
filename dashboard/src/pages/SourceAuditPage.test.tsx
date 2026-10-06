import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { createFixtureRepository } from '../lib/taskRepository'
import { SourceAuditPage } from './SourceAuditPage'

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

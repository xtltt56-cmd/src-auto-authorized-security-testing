import { render, screen } from '@testing-library/react'
import { waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { TaskDetailPage } from './TaskDetailPage'
import { OverviewPage } from './OverviewPage'
import { createFixtureRepository } from '../lib/taskRepository'
import { safeDefaultSnapshot } from '../lib/fixtures'

it('does not present Docker as a prerequisite for the native local-app page', async () => {
  const repository = createFixtureRepository()
  repository.getDashboardSnapshot = vi.fn().mockResolvedValue({ ...safeDefaultSnapshot, source: 'loopback', dependency: { executionServiceReady: true, dockerReady: false, message: 'not ready' } })
  repository.getAgent = vi.fn().mockResolvedValue({ enabled: false, remoteSessionEnabled: false, activeId: null, runs: [] })
  render(<App repository={repository} />)
  await screen.findByText('Docker 尚未就绪')
  await userEvent.click(screen.getByRole('button', { name: /^本机应用审查$/ }))
  await screen.findByRole('heading', { name: '审查一个自有本机服务' })
  expect(screen.queryByText('Docker 尚未就绪')).toBeNull()
})

it('updates task and events when polling delivers new props without claiming scan stages completed', () => {
  const task = safeDefaultSnapshot.tasks[1]
  const props = { task, events: [], repository: createFixtureRepository(), onBack: () => {}, onOpenReport: () => {} }
  const view = render(<TaskDetailPage {...props} />)
  view.rerender(<TaskDetailPage {...props} task={{ ...task, state: 'completed', stage: '靶场已就绪', elapsedSeconds: 39, progress: 100 }} />)
  expect(screen.getByText('39s')).toBeVisible()
  expect(screen.queryByText('报告生成', { exact: true })).not.toBeInTheDocument()
  expect(screen.queryByText('受控验证', { exact: true })).not.toBeInTheDocument()
  expect(screen.getByRole('note')).toHaveTextContent('环境就绪不表示已执行漏洞扫描')
})

it('renders an actionable empty state when the real backend has no tasks yet', () => {
  render(<OverviewPage snapshot={{ source: 'loopback', tasks: [], labs: [], events: [], findings: [], reports: [] }} onNavigate={() => {}} onOpenTask={() => {}} />)
  expect(screen.getByRole('heading', { name: '清晰、可控地开始一次安全测试' })).toBeVisible()
  expect(screen.getByText('尚无任务记录')).toBeVisible()
  expect(screen.getByRole('button', { name: /进入本地靶场/ })).toBeEnabled()
})

it('shows a connecting state before the first dashboard response instead of a false disconnect warning', async () => {
  let resolveSnapshot: ((value: typeof safeDefaultSnapshot) => void) | undefined
  const repository = createFixtureRepository()
  repository.getDashboardSnapshot = () => new Promise((resolve) => { resolveSnapshot = resolve })
  render(<App repository={repository} />)
  expect(screen.getByText('正在连接本地执行服务')).toBeVisible()
  expect(screen.queryByText('未连接本地执行服务')).not.toBeInTheDocument()
  await waitFor(() => expect(resolveSnapshot).toBeDefined())
  resolveSnapshot?.(safeDefaultSnapshot)
  await waitFor(() => expect(screen.queryByText('正在连接本地执行服务')).not.toBeInTheDocument())
})

it('shows the candidate count from the artifact source instead of lab lifecycle counters', async () => {
  const repository = createFixtureRepository()
  repository.getArtifactSummary = vi.fn().mockResolvedValue({ candidateCount: 7, reportCount: 3 })
  render(<App repository={repository} />)

  expect(await screen.findByText('历史候选记录')).toBeVisible()
  const metric = screen.getByText('历史候选记录').closest('div')
  expect(metric).toHaveTextContent('7')
})

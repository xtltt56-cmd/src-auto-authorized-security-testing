import { render, screen } from '@testing-library/react'
import { TaskDetailPage } from './TaskDetailPage'
import { OverviewPage } from './OverviewPage'
import { createFixtureRepository } from '../lib/taskRepository'
import { safeDefaultSnapshot } from '../lib/fixtures'

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

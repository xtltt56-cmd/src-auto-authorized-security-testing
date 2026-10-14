import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import type { AgentRun } from '../lib/types'
import { AgentDecisionDetails } from './AgentDecisionDetails'

const run = {
  id: 'catalog-test', labId: 'owned-local', mode: 'local-web-assessment', provider: 'deepseek', state: 'running', reason: 'observation_saved',
  steps: 1, requests: 1, modelCalls: 2, tokens: 50, usageEstimated: false, elapsedSeconds: 2, candidates: 0, reportId: '', createdAt: '2026-10-14',
  actionMenu: { catalogVersion: 'local-readonly-v5', options: { inspect_local_route: ['route-002'], request_human_review: ['entry'] },
    missing: [{ action: 'inspect_local_route', reference: 'route-002' }], completionReady: false },
  trace: [{ index: 1, result: 'rejected', reason: 'action_not_available', validation: 'rejected', source: 'model',
    decision: { action: 'analyze_passive_capture', reference: 'entry', evidence: [], reason: '合成选择错误' } },
    { index: 2, result: 'ok', validation: 'passed', source: 'model', executor: 'LocalWebActions', observationId: 'o1',
      decision: { action: 'inspect_local_route', reference: 'route-001', evidence: [], reason: '检查批准路由' } }],
  observations: [{ id: 'o1', action: 'inspect_local_route', reference: 'route-001', summary: '真实路由已检查' }],
} satisfies AgentRun

it('opens actual task menu and distinguishes a rejected proposal from real execution', async () => {
  render(<AgentDecisionDetails run={run} />)
  await userEvent.click(screen.getByText('动作菜单与执行校验'))
  expect(screen.getByText('route-002')).toBeVisible()
  expect(screen.getByText(/当前任务或阶段不支持该动作/)).toBeVisible()
  expect(screen.getByText(/本机应用执行器/)).toBeVisible()
  expect(screen.getByText('o1 · 真实路由已检查')).toBeVisible()
  expect(screen.getByText('未调用工具')).toBeVisible()
})

it('does not claim legacy history has a recorded menu', async () => {
  render(<AgentDecisionDetails run={{ ...run, actionMenu: undefined, trace: [] }} />)
  await userEvent.click(screen.getByText('动作菜单与执行校验'))
  expect(screen.getByText(/没有记录动态动作菜单/)).toBeVisible()
})

it('marks finish as a control action rather than a scanner execution', async () => {
  render(<AgentDecisionDetails run={{ ...run, trace: [{ index: 1, result: 'ok', validation: 'passed', source: 'model',
    decision: { action: 'finish', reference: 'entry', evidence: ['o1'], reason: '合成结束' } }] }} />)
  await userEvent.click(screen.getByText('动作菜单与执行校验'))
  expect(screen.getByText('控制动作 · 不调用扫描器')).toBeVisible()
})

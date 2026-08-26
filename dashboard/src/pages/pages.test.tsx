import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { createFixtureRepository } from '../lib/taskRepository'

describe('dashboard pages', () => {
  it('updates task detail through pause, resume and stop actions', async () => {
    render(<App repository={createFixtureRepository()} />)

    await userEvent.click(screen.getByRole('button', { name: '本地靶场' }))
    await userEvent.click(screen.getByRole('button', { name: '打开任务详情' }))
    await userEvent.click(screen.getByRole('button', { name: '暂停任务' }))
    expect(await screen.findByText('已暂停')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '继续任务' }))
    expect(await screen.findByText('运行中')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '停止任务' }))
    expect(await screen.findByText('已取消')).toBeVisible()
    expect(screen.getByRole('button', { name: '继续任务' })).toBeDisabled()
  })

  it('shows local-only safety notice and five lab names', async () => {
    render(<App repository={createFixtureRepository()} />)
    expect((await screen.findAllByText(/真实目标不会自动执行/))[0]).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '本地靶场' }))
    expect(screen.getByText('Juice Shop')).toBeVisible()
    expect(screen.getByText('DVWA')).toBeVisible()
    expect(screen.getByText('WebGoat')).toBeVisible()
    expect(screen.getByText('VAmPI')).toBeVisible()
    expect(screen.getByText('Business API')).toBeVisible()
  })

  it('opens a safe detail view when a timeline event is selected', async () => {
    render(<App repository={createFixtureRepository()} />)

    await userEvent.click(screen.getByRole('button', { name: '本地靶场' }))
    await userEvent.click(screen.getByRole('button', { name: '打开任务详情' }))
    await userEvent.click(screen.getByRole('button', { name: /已处理授权夹具中的 42 个入口/ }))

    expect(await screen.findByRole('heading', { name: '事件详情' })).toBeVisible()
    expect(screen.getAllByText('已处理授权夹具中的 42 个入口')[1]).toBeVisible()
  })
})

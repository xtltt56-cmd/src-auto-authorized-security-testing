import { fireEvent, render, screen } from '@testing-library/react'
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

  it('validates and saves an authorization draft locally', async () => {
    render(<App repository={createFixtureRepository()} />)
    await userEvent.click(screen.getByRole('button', { name: '目标与授权' }))
    expect(screen.getByRole('heading', { name: '新建授权目标' })).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '保存授权草稿' }))
    expect(screen.getByText('请填写目标 URL。')).toBeVisible()

    await userEvent.type(screen.getByLabelText('项目名称'), '示例授权项目')
    await userEvent.type(screen.getByLabelText('目标 URL'), 'https://example.com/app')
    await userEvent.type(screen.getByLabelText('允许主机名'), 'example.com')
    await userEvent.type(screen.getByLabelText('允许端口'), '443')
    fireEvent.change(screen.getByLabelText('开始时间'), { target: { value: '2026-08-27T09:00' } })
    fireEvent.change(screen.getByLabelText('结束时间'), { target: { value: '2026-08-27T18:00' } })
    await userEvent.type(screen.getByLabelText('授权证明或规则说明'), '项目规则允许在时间窗内进行低频测试。')
    await userEvent.click(screen.getByRole('button', { name: '保存授权草稿' }))

    expect(await screen.findByText('授权草稿已保存')).toBeVisible()
    expect(screen.getByText('未访问目标')).toBeVisible()
  })

  it('opens finding evidence and a report as safe read-only views', async () => {
    render(<App repository={createFixtureRepository()} />)
    await userEvent.click(screen.getByRole('button', { name: '候选与报告' }))
    expect(screen.getByRole('heading', { name: '候选漏洞与报告' })).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '反射型输入点需要人工确认' }))
    expect(await screen.findByRole('heading', { name: '候选详情' })).toBeVisible()
    expect(screen.getByText(/完整响应正文未写入事件日志/)).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '查看 juice-shop-summary.json' }))
    expect(await screen.findByRole('heading', { name: '报告查看器' })).toBeVisible()
    expect(screen.getByText('脚本不会执行')).toBeVisible()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { createFixtureRepository } from '../lib/taskRepository'

const localLabExpectations = [
  { name: 'Juice Shop', port: '127.0.0.1:3000', taskName: 'Juice Shop · 本地任务' },
  { name: 'DVWA', port: '127.0.0.1:8081', taskName: 'DVWA · 本地任务' },
  { name: 'WebGoat', port: '127.0.0.1:8082', taskName: 'WebGoat · 本地任务' },
  { name: 'VAmPI', port: '127.0.0.1:8083', taskName: 'VAmPI · 本地任务' },
  { name: 'Business API', port: '127.0.0.1:8084', taskName: 'Business API · 本地任务' },
] as const

describe('dashboard pages', () => {
  it('starts in a truthful idle state when no execution service is connected', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByRole('status', { name: '数据来源状态' })).toHaveTextContent('未连接本地执行服务')
    expect(screen.queryByText('运行中')).not.toBeInTheDocument()
    expect(screen.getAllByText('未启动').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: '打开任务详情' }))
    expect(await screen.findByRole('heading', { name: '本地五靶场回归 · 第 1 轮' })).toBeVisible()
    expect(screen.getByText('0s', { exact: false })).toBeVisible()
    expect(screen.getByRole('button', { name: '继续任务' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '停止任务' })).toBeDisabled()
  })

  it('updates task detail through pause, resume and stop actions', async () => {
    render(<App repository={createFixtureRepository()} />)

    await userEvent.click(screen.getByRole('button', { name: '本地靶场' }))
    await userEvent.click(screen.getByRole('button', { name: '打开环境任务' }))
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

  it('can start, stop and reset a local lab from the visible controls', async () => {
    const user = userEvent.setup()
    render(<App repository={createFixtureRepository()} />)
    await user.click(screen.getByRole('button', { name: '本地靶场' }))

    await user.click(screen.getByRole('button', { name: '停止 DVWA' }))
    expect(await screen.findByRole('button', { name: '启动 DVWA' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: '启动 DVWA' }))
    expect(await screen.findByRole('button', { name: '停止 DVWA' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: '重置 DVWA' }))
    expect(await screen.findByText(/dvwa 操作已提交/)).toBeVisible()
  })

  it('submits a batch start and stop action from the lab banner', async () => {
    const user = userEvent.setup()
    render(<App repository={createFixtureRepository()} />)
    await user.click(screen.getByRole('button', { name: '本地靶场' }))
    await user.click(screen.getByRole('button', { name: '启动全部靶场' }))
    expect(await screen.findByText('启动全部操作已提交，页面会显示逐个就绪状态。')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '停止全部靶场' }))
    expect(await screen.findByText('停止全部操作已提交。')).toBeVisible()
  })

  it.each(localLabExpectations)('opens $name as an independent local task', async ({ name, port, taskName }) => {
    const user = userEvent.setup()
    render(<App repository={createFixtureRepository()} />)

    await user.click(screen.getByRole('button', { name: '本地靶场' }))
    await user.click(screen.getByRole('button', { name: `查看 ${name} 任务` }))

    expect(await screen.findByRole('heading', { name: taskName })).toBeVisible()
    expect(screen.getByText(port, { exact: true })).toBeVisible()
    await user.click(screen.getByRole('button', { name: '返回靶场列表' }))
    expect((await screen.findAllByRole('heading', { name: '本地靶场' })).at(0)).toBeVisible()
  })

  it('keeps a lab without a report on its own detail page', async () => {
    const user = userEvent.setup()
    render(<App repository={createFixtureRepository()} />)

    await user.click(screen.getByRole('button', { name: '本地靶场' }))
    await user.click(screen.getByRole('button', { name: '查看 VAmPI 任务' }))
    await user.click(screen.getByRole('button', { name: '查看报告' }))

    expect(await screen.findByText('当前靶场尚未生成报告')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'VAmPI · 本地任务' })).toBeVisible()
  })

  it('opens the matching task when a lab name is selected', async () => {
    const user = userEvent.setup()
    render(<App repository={createFixtureRepository()} />)

    await user.click(screen.getByRole('button', { name: '本地靶场' }))
    await user.click(screen.getByRole('button', { name: /Business API.*127\.0\.0\.1:8084/ }))

    expect(await screen.findByRole('heading', { name: 'Business API · 本地任务' })).toBeVisible()
  })

  it('opens a safe detail view when a timeline event is selected', async () => {
    render(<App repository={createFixtureRepository()} />)

    await userEvent.click(screen.getByRole('button', { name: '本地靶场' }))
    await userEvent.click(screen.getByRole('button', { name: '打开环境任务' }))
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
    expect(screen.getByLabelText('报告内容：juice-shop-summary.json')).toHaveTextContent('local-fixture')
  })
})

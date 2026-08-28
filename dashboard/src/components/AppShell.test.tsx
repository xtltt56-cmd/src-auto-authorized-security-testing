import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { AppShell } from './AppShell'
import { ProgressBar } from './ProgressBar'
import { StatusBadge } from './StatusBadge'

describe('dashboard shell primitives', () => {
  it('renders clickable Chinese navigation and selected state', async () => {
    const onNavigate = vi.fn()
    render(
      <AppShell activeKey="overview" onNavigate={onNavigate}>
        <p>内容区域</p>
      </AppShell>,
    )

    await userEvent.click(screen.getByRole('button', { name: '本地靶场' }))

    expect(onNavigate).toHaveBeenCalledWith('labs')
    expect(screen.getByRole('main')).toBeVisible()
  })

  it('announces blocked state with text and an accessible label', () => {
    render(<StatusBadge state="blocked" />)

    expect(screen.getByRole('status')).toHaveAttribute('aria-label', '状态：已阻止')
    expect(screen.getByText('已阻止')).toBeVisible()
  })

  it('exposes progress value to assistive technology', () => {
    render(<ProgressBar value={62} label="任务进度" />)

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '62')
    expect(screen.getByText('任务进度')).toBeVisible()
  })
})

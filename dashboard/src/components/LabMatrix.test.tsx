import { render, screen } from '@testing-library/react'
import { LabMatrix } from './LabMatrix'
import type { LabStatus } from '../lib/types'

const startingLab: LabStatus = {
  id: 'juice-shop',
  taskId: 'run-lab-juice-shop',
  name: 'Juice Shop',
  port: 3000,
  health: 'starting',
  stage: '正在启动',
  durationSeconds: 4,
  candidates: 0,
  localOnly: true,
  operation: 'running',
}

describe('LabMatrix', () => {
  it('labels a loopback lab that is starting accurately', () => {
    render(
      <LabMatrix
        labs={[startingLab]}
        onOpenLabTask={() => undefined}
        onAction={async () => undefined}
        onDetectionAction={async () => undefined}
      />,
    )

    expect(screen.getByRole('status', { name: '状态：启动中' })).toBeVisible()
    expect(screen.queryByRole('status', { name: '状态：等待人工' })).not.toBeInTheDocument()
  })
})

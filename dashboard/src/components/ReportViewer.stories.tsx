import type { Meta, StoryObj } from '@storybook/react-vite'
import { fixtureSnapshot } from '../lib/fixtures'
import { ReportViewer } from './ReportViewer'

const meta = {
  title: '组件/安全报告查看器',
  component: ReportViewer,
  parameters: { layout: 'centered' },
  args: { report: fixtureSnapshot.reports[0], onClose: () => undefined },
} satisfies Meta<typeof ReportViewer>

export default meta
type Story = StoryObj<typeof meta>

export const RedactedText: Story = {}
export const BlockedPath: Story = { args: { report: { ...fixtureSnapshot.reports[0], relativePath: '../secrets.txt' } } }

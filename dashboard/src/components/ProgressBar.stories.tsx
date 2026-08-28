import type { Meta, StoryObj } from '@storybook/react-vite'
import { ProgressBar } from './ProgressBar'

const meta = {
  title: '基础组件/进度条',
  component: ProgressBar,
  tags: ['autodocs'],
} satisfies Meta<typeof ProgressBar>

export default meta
type Story = StoryObj<typeof meta>

export const 进行中: Story = { args: { value: 62, label: '任务进度' } }
export const 已完成: Story = { args: { value: 100, label: '任务进度' } }
export const 尚未开始: Story = { args: { value: 0, label: '任务进度' } }

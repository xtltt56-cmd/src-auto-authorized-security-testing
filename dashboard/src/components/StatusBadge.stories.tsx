import type { Meta, StoryObj } from '@storybook/react-vite'
import { StatusBadge } from './StatusBadge'

const meta = {
  title: '基础组件/状态标签',
  component: StatusBadge,
  tags: ['autodocs'],
} satisfies Meta<typeof StatusBadge>

export default meta
type Story = StoryObj<typeof meta>

export const 运行中: Story = { args: { state: 'running' } }
export const 等待人工: Story = { args: { state: 'waiting' } }
export const 已阻止: Story = { args: { state: 'blocked' } }
export const 已完成: Story = { args: { state: 'completed' } }

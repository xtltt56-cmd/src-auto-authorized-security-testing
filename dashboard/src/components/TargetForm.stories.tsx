import type { Meta, StoryObj } from '@storybook/react-vite'
import { TargetForm } from './TargetForm'

const meta = {
  title: '组件/授权目标表单',
  component: TargetForm,
  parameters: { layout: 'centered' },
  args: { onSave: () => undefined },
} satisfies Meta<typeof TargetForm>

export default meta
type Story = StoryObj<typeof meta>

export const Empty: Story = {}
export const PreFilled: Story = {
  args: {
    initialDraft: {
      projectName: '示例授权项目',
      targetUrl: 'https://example.com/app',
      allowedHosts: 'example.com',
      allowedPorts: '443',
      excludedPaths: '/admin',
      windowStart: '2026-08-27T09:00',
      windowEnd: '2026-08-27T18:00',
      allowedMethods: 'GET, HEAD',
      concurrency: '1',
      requestLimit: '100',
      authorizationNote: '项目规则明确允许在时间窗内进行低频测试。',
    },
  },
}

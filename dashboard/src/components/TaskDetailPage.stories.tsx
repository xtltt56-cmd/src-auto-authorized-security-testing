import type { Meta, StoryObj } from '@storybook/react-vite'
import { fixtureSnapshot } from '../lib/fixtures'
import { createFixtureRepository } from '../lib/taskRepository'
import { TaskDetailPage } from '../pages/TaskDetailPage'

const repository = createFixtureRepository()
const task = fixtureSnapshot.tasks[0]

const meta = {
  title: '页面/任务详情',
  component: TaskDetailPage,
  parameters: { layout: 'fullscreen' },
  args: {
    task,
    events: fixtureSnapshot.events.filter((event) => event.taskId === task.id),
    repository,
    onBack: () => undefined,
    onOpenReport: () => undefined,
  },
} satisfies Meta<typeof TaskDetailPage>

export default meta
type Story = StoryObj<typeof meta>

export const Running: Story = {}
export const Cancelled: Story = { args: { task: { ...task, state: 'cancelled', progress: 62 } } }

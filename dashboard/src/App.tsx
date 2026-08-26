import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileSearch, LockKeyhole, Settings2 } from 'lucide-react'
import { AppShell, type NavKey } from './components/AppShell'
import { LabsPage } from './pages/LabsPage'
import { OverviewPage } from './pages/OverviewPage'
import { TaskDetailPage } from './pages/TaskDetailPage'
import { createFixtureRepository, type TaskRepository } from './lib/taskRepository'
import { fixtureSnapshot } from './lib/fixtures'
import type { DashboardSnapshot } from './lib/types'

type AppProps = { repository?: TaskRepository }

const defaultRepository = createFixtureRepository()

const pageMeta: Record<NavKey, { title: string; description: string }> = {
  overview: { title: '安全测试控制台', description: '本地优先 · 授权可控 · 人工最终确认' },
  labs: { title: '本地靶场', description: '五个固定回环入口 · 仅用于本地验证' },
  targets: { title: '目标与授权', description: '先保存草稿，再由人工确认授权范围' },
  review: { title: '离线审阅', description: '解析项目文件，不产生网络请求' },
  findings: { title: '候选与报告', description: '人工复核候选证据，不自动提交' },
  settings: { title: '系统设置', description: '模型、密钥状态、依赖和 D 盘存储' },
}

function PlaceholderPage({ kind }: { kind: 'targets' | 'review' | 'settings' }) {
  const copy = {
    targets: { icon: LockKeyhole, title: '授权目标草稿', body: '在这里填写项目、URL、Scope 和时间窗。保存草稿不会访问目标。' },
    review: { icon: FileSearch, title: '离线审阅范围', body: '选择 D 盘项目目录中的文件，解析过程不会产生网络接触。' },
    settings: { icon: Settings2, title: '系统设置', body: '远程 AI 默认关闭；密钥只显示配置状态，不显示密钥内容。' },
  }[kind]
  const Icon = copy.icon
  return <section className="surface-panel placeholder-panel"><Icon size={28} aria-hidden="true" /><h3>{copy.title}</h3><p>{copy.body}</p></section>
}

export function App({ repository = defaultRepository }: AppProps) {
  const [activeKey, setActiveKey] = useState<NavKey>('overview')
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(fixtureSnapshot)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)

  const refresh = useCallback(async () => { setSnapshot(await repository.getDashboardSnapshot()) }, [repository])
  useEffect(() => { void refresh() }, [refresh])

  const selectedTask = useMemo(() => snapshot.tasks.find((task) => task.id === selectedTaskId) ?? null, [selectedTaskId, snapshot.tasks])
  const selectedEvents = useMemo(() => snapshot.events.filter((event) => event.taskId === selectedTaskId), [selectedTaskId, snapshot.events])
  const navigate = (key: NavKey) => { setSelectedTaskId(null); setActiveKey(key) }
  const openTask = (taskId: string) => { setSelectedTaskId(taskId); setActiveKey('labs') }

  let content
  if (selectedTask) {
    content = <TaskDetailPage task={selectedTask} events={selectedEvents} repository={repository} onBack={() => setSelectedTaskId(null)} onOpenReport={() => setActiveKey('findings')} />
  } else if (activeKey === 'overview') {
    content = <OverviewPage snapshot={snapshot} onNavigate={navigate} onOpenTask={openTask} />
  } else if (activeKey === 'labs') {
    content = <LabsPage snapshot={snapshot} onOpenTask={openTask} onNavigate={navigate} />
  } else if (activeKey === 'findings') {
    content = <PlaceholderPage kind="review" />
  } else {
    content = <PlaceholderPage kind={activeKey === 'settings' ? 'settings' : activeKey === 'targets' ? 'targets' : 'review'} />
  }

  const meta = pageMeta[activeKey]
  return <AppShell activeKey={activeKey} onNavigate={navigate} pageTitle={meta.title} pageDescription={meta.description}>{content}</AppShell>
}

export default App

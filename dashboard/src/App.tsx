import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileSearch, Info, LockKeyhole, Settings2 } from 'lucide-react'
import { AppShell, type NavKey } from './components/AppShell'
import { LabsPage } from './pages/LabsPage'
import { OverviewPage } from './pages/OverviewPage'
import { TaskDetailPage } from './pages/TaskDetailPage'
import { TargetDraftPage } from './pages/TargetDraftPage'
import { FindingsPage } from './pages/FindingsPage'
import { createLoopbackRepository, type TaskRepository } from './lib/taskRepository'
import { safeDefaultSnapshot } from './lib/fixtures'
import type { DashboardSnapshot, TargetDraftResult } from './lib/types'

type AppProps = { repository?: TaskRepository }

const defaultRepository = createLoopbackRepository('/api')

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
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(safeDefaultSnapshot)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [savedTargetResult, setSavedTargetResult] = useState<TargetDraftResult | null>(null)
  const [connectionMessage, setConnectionMessage] = useState('')

  // The repository is an asynchronous external source; updating the snapshot is intentional.
  const refresh = useCallback(async () => {
    try {
      const next = await repository.getDashboardSnapshot()
      setSnapshot(next)
      setConnectionMessage(next.dependency?.message ?? '')
    } catch {
      setSnapshot(safeDefaultSnapshot)
      setConnectionMessage('本地执行服务暂不可用，已切换为安全空闲状态')
    }
  }, [repository])
  useEffect(() => {
    let active = true
    let refreshing = false
    const tick = async () => {
      if (!active || refreshing) return
      refreshing = true
      try { await refresh() } finally { refreshing = false }
    }
    void tick()
    const timer = window.setInterval(() => { void tick() }, 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [refresh])

  const selectedTask = useMemo(() => snapshot.tasks.find((task) => task.id === selectedTaskId) ?? null, [selectedTaskId, snapshot.tasks])
  const selectedLab = useMemo(() => snapshot.labs.find((lab) => lab.taskId === selectedTaskId) ?? null, [selectedTaskId, snapshot.labs])
  const selectedEvents = useMemo(() => snapshot.events.filter((event) => event.taskId === selectedTaskId), [selectedTaskId, snapshot.events])
  const navigate = (key: NavKey) => { setSelectedTaskId(null); setActiveKey(key) }
  const openTask = (taskId: string) => { setSelectedTaskId(taskId); setActiveKey('labs') }
  const runLabAction = useCallback(async (labId: string, action: 'start' | 'stop' | 'reset') => {
    if (action === 'start') await repository.startLab(labId)
    else if (action === 'stop') await repository.stopLab(labId)
    else await repository.resetLab(labId)
    await refresh()
  }, [refresh, repository])
  const runBatchAction = useCallback(async (action: 'start' | 'stop') => {
    if (action === 'start') await repository.startAllLabs()
    else await repository.stopAllLabs()
    await refresh()
  }, [refresh, repository])

  let content
  if (selectedTask) {
    content = <TaskDetailPage task={selectedTask} lab={selectedLab} events={selectedEvents} repository={repository} onBack={() => setSelectedTaskId(null)} onOpenReport={() => { setSelectedTaskId(null); setActiveKey('findings') }} />
  } else if (activeKey === 'overview') {
    content = <OverviewPage snapshot={snapshot} onNavigate={navigate} onOpenTask={openTask} />
  } else if (activeKey === 'labs') {
    content = <LabsPage snapshot={snapshot} onOpenTask={openTask} onNavigate={navigate} onAction={runLabAction} onBatchAction={runBatchAction} />
  } else if (activeKey === 'findings') {
    content = <FindingsPage findings={snapshot.findings} reports={snapshot.reports} />
  } else if (activeKey === 'targets') {
    content = <TargetDraftPage savedResult={savedTargetResult} onSaved={setSavedTargetResult} />
  } else {
    content = <PlaceholderPage kind={activeKey === 'settings' ? 'settings' : 'review'} />
  }

  const meta = pageMeta[activeKey]
  return (
    <AppShell activeKey={activeKey} onNavigate={navigate} pageTitle={meta.title} pageDescription={meta.description}>
      {snapshot.source === 'safe-placeholder' ? (
        <div className="inline-notice data-source-notice" role="status" aria-label="数据来源状态">
          <Info size={16} aria-hidden="true" />
          <span><strong>未连接本地执行服务</strong> · {connectionMessage || '当前没有真实任务在运行，页面显示安全空闲状态。'}</span>
        </div>
      ) : snapshot.source === 'loopback' && snapshot.dependency && !snapshot.dependency.dockerReady ? (
        <div className="inline-notice data-source-notice" role="status" aria-label="依赖状态">
          <Info size={16} aria-hidden="true" />
          <span><strong>Docker 尚未就绪</strong> · {snapshot.dependency.message}</span>
        </div>
      ) : null}
      {content}
    </AppShell>
  )
}

export default App

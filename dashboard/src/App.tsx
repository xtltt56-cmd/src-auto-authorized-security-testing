import { useCallback, useEffect, useMemo, useState } from 'react'
import { Info } from 'lucide-react'
import { AppShell, type NavKey } from './components/AppShell'
import { LabsPage } from './pages/LabsPage'
import { OverviewPage } from './pages/OverviewPage'
import { TaskDetailPage } from './pages/TaskDetailPage'
import { TargetDraftPage } from './pages/TargetDraftPage'
import { FindingsPage } from './pages/FindingsPage'
import { AISettingsPage } from './pages/AISettingsPage'
import { OfflineReviewPage } from './pages/OfflineReviewPage'
import { createLoopbackRepository, type TaskRepository } from './lib/taskRepository'
import { safeDefaultSnapshot } from './lib/fixtures'
import type { ArtifactSummary, DashboardSnapshot, TargetDraftResult } from './lib/types'

type AppProps = { repository?: TaskRepository }

const defaultRepository = createLoopbackRepository('/api')
const navKeys: NavKey[] = ['overview', 'labs', 'targets', 'review', 'findings', 'settings']

const initialNavKey = (): NavKey => {
  const requested = new URLSearchParams(window.location.search).get('page') as NavKey | null
  return requested && navKeys.includes(requested) ? requested : 'overview'
}

const pageMeta: Record<NavKey, { title: string; description: string }> = {
  overview: { title: '安全测试控制台', description: '本地优先 · 授权可控 · 人工最终确认' },
  labs: { title: '本地靶场', description: '五个固定回环入口 · 仅用于本地验证' },
  targets: { title: '目标与授权', description: '先保存草稿，再由人工确认授权范围' },
  review: { title: '离线审阅', description: '解析项目文件，不产生网络请求' },
  findings: { title: '候选与报告', description: '人工复核候选证据，不自动提交' },
  settings: { title: '系统设置', description: '模型、密钥状态、依赖和 D 盘存储' },
}

export function App({ repository = defaultRepository }: AppProps) {
  const [activeKey, setActiveKey] = useState<NavKey>(initialNavKey)
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(safeDefaultSnapshot)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [savedTargetResult, setSavedTargetResult] = useState<TargetDraftResult | null>(null)
  const [connectionMessage, setConnectionMessage] = useState('')
  const [artifactSummary, setArtifactSummary] = useState<ArtifactSummary>({ candidateCount: 0, reportCount: 0 })
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [initialLoading, setInitialLoading] = useState(true)

  // The repository is an asynchronous external source; updating the snapshot is intentional.
  const refresh = useCallback(async () => {
    try {
      const next = await repository.getDashboardSnapshot()
      setSnapshot(next)
      setConnectionMessage(next.dependency?.message ?? '')
    } catch {
      setSnapshot(safeDefaultSnapshot)
      setConnectionMessage('本地执行服务暂不可用，当前任务状态未知；请恢复连接后核对')
    } finally {
      setInitialLoading(false)
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
  useEffect(() => {
    let active = true
    void repository.getArtifactSummary()
      .then(summary => { if (active) setArtifactSummary(summary) })
      .catch(() => { if (active) setArtifactSummary({ candidateCount: 0, reportCount: 0 }) })
    return () => { active = false }
  }, [repository])

  const selectedTask = useMemo(() => snapshot.tasks.find((task) => task.id === selectedTaskId) ?? null, [selectedTaskId, snapshot.tasks])
  const selectedLab = useMemo(() => snapshot.labs.find((lab) => lab.taskId === selectedTaskId) ?? null, [selectedTaskId, snapshot.labs])
  const selectedEvents = useMemo(() => snapshot.events.filter((event) => event.taskId === selectedTaskId), [selectedTaskId, snapshot.events])
  const navigate = (key: NavKey) => { setSelectedTaskId(null); setSelectedReportId(null); setActiveKey(key) }
  const openTask = (taskId: string) => { setSelectedTaskId(taskId); setSelectedReportId(null); setActiveKey('labs') }
  const openTaskReport = (reportId?: string) => { setSelectedTaskId(null); setSelectedReportId(reportId ?? null); setActiveKey('findings') }
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
  const runDetectionAction = useCallback(async (labId: string, action: 'start' | 'stop') => {
    if (action === 'start') await repository.startLabDetection(labId)
    else await repository.stopLabDetection(labId)
    await refresh()
  }, [refresh, repository])
  const startDockerDesktop = useCallback(async () => {
    await repository.startDockerDesktop()
    await refresh()
  }, [refresh, repository])

  let content
  if (selectedTask) {
    content = <TaskDetailPage task={selectedTask} lab={selectedLab} events={selectedEvents} repository={repository} onRefresh={refresh} onBack={() => setSelectedTaskId(null)} onOpenReport={openTaskReport} />
  } else if (activeKey === 'overview') {
    content = <OverviewPage snapshot={snapshot} artifactSummary={artifactSummary} onNavigate={navigate} onOpenTask={openTask} />
  } else if (activeKey === 'labs') {
    content = <LabsPage snapshot={snapshot} onOpenTask={openTask} onNavigate={navigate} onAction={runLabAction} onDetectionAction={runDetectionAction} onBatchAction={runBatchAction} onStartDocker={startDockerDesktop} />
  } else if (activeKey === 'findings') {
    content = <FindingsPage findings={snapshot.findings} reports={snapshot.reports} repository={repository} initialSelectedReportId={selectedReportId} onArtifactSummary={setArtifactSummary} />
  } else if (activeKey === 'targets') {
    content = <TargetDraftPage savedResult={savedTargetResult} onSaved={setSavedTargetResult} repository={repository} />
  } else if (activeKey === 'settings') {
    content = <AISettingsPage repository={repository} />
  } else {
    content = <OfflineReviewPage repository={repository} />
  }

  const meta = pageMeta[activeKey]
  return (
    <AppShell activeKey={activeKey} onNavigate={navigate} pageTitle={meta.title} pageDescription={meta.description}>
      {initialLoading ? (
        <div className="inline-notice data-source-notice" role="status" aria-label="数据来源状态">
          <Info size={16} aria-hidden="true" />
          <span><strong>正在连接本地执行服务</strong> · 正在读取真实任务与靶场状态，请稍候。</span>
        </div>
      ) : snapshot.source === 'safe-placeholder' ? (
        <div className="inline-notice data-source-notice" role="status" aria-label="数据来源状态">
          <Info size={16} aria-hidden="true" />
          <span><strong>未连接本地执行服务</strong> · {connectionMessage || '当前任务状态未知；页面不会把失联误判为已停止。'}</span>
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

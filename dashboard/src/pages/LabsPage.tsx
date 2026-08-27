import { Play, RefreshCw, ShieldCheck } from 'lucide-react'
import type { DashboardSnapshot } from '../lib/types'
import { LabMatrix } from '../components/LabMatrix'
import type { NavKey } from '../components/AppShell'

type LabsPageProps = {
  snapshot: DashboardSnapshot
  onOpenTask: (taskId: string) => void
  onNavigate: (key: NavKey) => void
}

export function LabsPage({ snapshot, onOpenTask, onNavigate }: LabsPageProps) {
  return (
    <>
      <div className="page-heading">
        <div><h3>本地靶场</h3><p>五个固定回环服务用于练习发现、受控验证和候选研判。这里不会接触真实项目。</p></div>
        <div className="inline-actions"><span className="local-only-label"><ShieldCheck size={14} aria-hidden="true" /> 只访问 127.0.0.1</span><button className="action-button" type="button" onClick={() => onNavigate('overview')}><RefreshCw size={15} aria-hidden="true" /> 返回总览</button></div>
      </div>
      <div className="lab-banner surface-panel"><div><strong>建议先运行完整五靶场回归</strong><p>任务会依次记录健康检查、入口发现、受控验证和报告生成事件。</p></div><button className="action-button" data-variant="primary" type="button" onClick={() => onOpenTask('run-local-001')}><Play size={16} aria-hidden="true" /> 打开当前任务</button></div>
      <LabMatrix labs={snapshot.labs} onOpenLabTask={onOpenTask} />
    </>
  )
}

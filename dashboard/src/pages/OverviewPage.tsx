import { ArrowRight, FileSearch, LockKeyhole, PlayCircle, ShieldCheck, TestTube2 } from 'lucide-react'
import type { DashboardSnapshot } from '../lib/types'
import type { NavKey } from '../components/AppShell'
import { MetricStrip } from '../components/MetricStrip'
import { ProgressBar } from '../components/ProgressBar'
import { StatusBadge } from '../components/StatusBadge'

type OverviewPageProps = {
  snapshot: DashboardSnapshot
  onNavigate: (key: NavKey) => void
  onOpenTask: (taskId: string) => void
}

export function OverviewPage({ snapshot, onNavigate, onOpenTask }: OverviewPageProps) {
  const activeTask = snapshot.tasks.find((task) => task.state === 'running' || task.state === 'paused') ?? snapshot.tasks[0]
  const totalCandidates = snapshot.tasks.reduce((sum, task) => sum + task.counters.candidates, 0)
  const totalBlocked = snapshot.tasks.reduce((sum, task) => sum + task.counters.blocked, 0)
  const metrics = [
    { label: '当前任务', value: snapshot.tasks.filter((task) => task.state === 'running' || task.state === 'paused').length },
    { label: '入口总数', value: activeTask.counters.endpoints },
    { label: '候选待复核', value: totalCandidates },
    { label: '策略阻止', value: totalBlocked },
  ]

  return (
    <>
      <div className="page-heading">
        <div>
          <h3>清晰、可控地开始一次安全测试</h3>
          <p>先在本地靶场熟悉流程；真实项目只会在你确认授权范围和时间窗后进入人工复核。</p>
        </div>
        <StatusBadge state={activeTask.state} />
      </div>

      <div className="hero-safety surface-panel">
        <div className="hero-safety-icon"><ShieldCheck size={24} aria-hidden="true" /></div>
        <div>
          <strong>安全边界已启用</strong>
          <p>默认只访问本机回环靶场；真实目标不会自动执行，远程 AI 和补天提交均需要人工单独确认。</p>
        </div>
        <span className="hero-safety-mode">网络接触：仅回环</span>
      </div>

      <section className="quick-start" aria-labelledby="quick-start-title">
        <div className="section-heading">
          <div><h4 id="quick-start-title">快速开始</h4><p>从下面三步任选一项，每一步都会明确展示下一步和安全边界。</p></div>
        </div>
        <div className="quick-grid">
          <article className="quick-card">
            <span className="step-number">01</span>
            <TestTube2 size={22} aria-hidden="true" />
            <h5>练习本地靶场</h5>
            <p>启动固定的五个回环靶场，观察入口发现、候选研判和报告生成。</p>
            <button className="action-button" data-variant="primary" type="button" onClick={() => onNavigate('labs')}><PlayCircle size={16} aria-hidden="true" /> 开始本地检测 <ArrowRight size={15} aria-hidden="true" /></button>
          </article>
          <article className="quick-card">
            <span className="step-number">02</span>
            <LockKeyhole size={22} aria-hidden="true" />
            <h5>录入授权目标</h5>
            <p>填写 URL、主机、端口、排除路径和时间窗，仅保存草稿不会访问目标。</p>
            <button className="action-button" type="button" onClick={() => onNavigate('targets')}>新建授权目标 <ArrowRight size={15} aria-hidden="true" /></button>
          </article>
          <article className="quick-card">
            <span className="step-number">03</span>
            <FileSearch size={22} aria-hidden="true" />
            <h5>离线审阅范围</h5>
            <p>审阅项目目录中的源代码和计划文件，解析过程完全不产生网络请求。</p>
            <button className="action-button" type="button" onClick={() => onNavigate('review')}>打开离线审阅 <ArrowRight size={15} aria-hidden="true" /></button>
          </article>
        </div>
      </section>

      <MetricStrip items={metrics} />

      <section className="surface-panel current-task-panel" aria-labelledby="current-task-title">
        <div className="panel-header">
          <div><h4 id="current-task-title">当前任务</h4><p>任务关闭后仍可从历史记录恢复查看</p></div>
          <button className="table-link" type="button" onClick={() => onOpenTask(activeTask.id)}>打开任务详情 <ArrowRight size={15} aria-hidden="true" /></button>
        </div>
        <div className="panel-body current-task-body">
          <div><div className="task-title-row"><strong>{activeTask.name}</strong><StatusBadge state={activeTask.state} /></div><span className="table-secondary">本地五靶场 · {activeTask.stage}</span></div>
          <ProgressBar value={activeTask.progress} label="总体进度" />
          <span className="network-note"><ShieldCheck size={14} aria-hidden="true" /> 网络接触：{activeTask.networkContact === 'loopback' ? '仅回环' : '无'}</span>
        </div>
      </section>
    </>
  )
}

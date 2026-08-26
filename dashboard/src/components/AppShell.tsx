import type { ReactNode } from 'react'
import { FileSearch, Flag, Gauge, LayoutDashboard, Settings2, ShieldCheck, Target, TestTube2 } from 'lucide-react'

export type NavKey = 'overview' | 'labs' | 'targets' | 'review' | 'findings' | 'settings'

type AppShellProps = {
  activeKey: NavKey
  onNavigate: (key: NavKey) => void
  children: ReactNode
  pageTitle?: string
  pageDescription?: string
}

const navItems: Array<{ key: NavKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: 'overview', label: '总览工作台', icon: LayoutDashboard },
  { key: 'labs', label: '本地靶场', icon: TestTube2 },
  { key: 'targets', label: '目标与授权', icon: Target },
  { key: 'review', label: '离线审阅', icon: FileSearch },
  { key: 'findings', label: '候选与报告', icon: Flag },
  { key: 'settings', label: '系统设置', icon: Settings2 },
]

export function AppShell({ activeKey, onNavigate, children, pageTitle = '安全测试控制台', pageDescription = '本地优先 · 授权可控 · 人工最终确认' }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar" aria-label="主导航">
        <div className="brand-lockup">
          <h1>SRC-Auto</h1>
          <p>授权安全测试控制台</p>
        </div>
        <nav className="app-nav">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              type="button"
              key={key}
              data-active={activeKey === key}
              aria-current={activeKey === key ? 'page' : undefined}
              onClick={() => onNavigate(key)}
            >
              <Icon size={17} strokeWidth={2} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-status" aria-label="安全状态">
          <span><ShieldCheck size={14} aria-hidden="true" /> 安全边界</span>
          <strong><Gauge size={14} aria-hidden="true" /> 仅本地回环模式</strong>
          <small>真实目标不会自动执行<br />远程 AI 默认关闭</small>
        </div>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <div>
            <h2>{pageTitle}</h2>
            <p>{pageDescription}</p>
          </div>
          <span className="topbar-state"><ShieldCheck size={15} aria-hidden="true" /> 安全状态：待人工操作</span>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  )
}

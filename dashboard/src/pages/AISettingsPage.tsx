import { useState } from 'react'

async function openNativeSettings() {
  const session = await fetch('/api/session', { cache: 'no-store' })
  if (!session.ok) throw new Error('session_unavailable')
  const { token } = await session.json() as { token?: string }
  if (!token) throw new Error('session_missing')
  const response = await fetch('/api/settings/openrouter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-SRC-Auto-Token': token },
    body: '{}',
  })
  if (!response.ok) throw new Error('settings_unavailable')
}

export function AISettingsPage({ openSettings = openNativeSettings }: { openSettings?: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const open = async () => {
    setBusy(true)
    try {
      await openSettings()
      setMessage('已请求打开 Windows 设置窗口；请在窗口中粘贴密钥或选择模型。已有窗口打开时请切换到该窗口。')
    } catch {
      setMessage('无法打开设置。请关闭并重新启动 SRC-Auto 一键启动器后重试，确保本地服务已更新。')
    } finally { setBusy(false) }
  }
  return <section className="surface-panel placeholder-panel">
    <h3>OpenRouter 密钥与模型</h3>
    <p>OpenRouter 密钥可用于多个模型。模型更名或下架后，通常只需要更换模型 ID，不需要重新生成密钥。</p>
    <ol>
      <li>打开设置窗口，查看已保存的密钥状态；需要更换时再粘贴。</li>
      <li>允许本窗口联网后刷新官方模型目录，选择模型并保存。</li>
      <li>先检查密钥和模型，再按需发送一条最小测试消息。</li>
    </ol>
    <button className="action-button" type="button" data-variant="primary" disabled={busy} onClick={() => void open()}>
      {busy ? '正在打开…' : '打开 OpenRouter 密钥与模型设置'}
    </button>
    {message && <p role="status">{message}</p>}
    <p>设置会保留 Windows 加密密钥。保存不会启用后台 AI；DeepSeek 的已有配置继续保留。</p>
  </section>
}

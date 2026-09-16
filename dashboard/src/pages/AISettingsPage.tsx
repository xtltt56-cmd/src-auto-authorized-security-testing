import { CheckCircle2, Eye, EyeOff, KeyRound, RotateCcw, ShieldCheck, Wifi } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { TaskRepository } from '../lib/taskRepository'
import type { AIProviderSettings } from '../lib/types'

const connectionMessages: Record<string, string> = {
  reachable_model_available: '连接成功：密钥有效，当前模型可以调用。',
  remote_ai_disabled_for_session: '本次启动已禁用远程 AI。请关闭 Dashboard，重新启动并在启动提示中明确允许后再测试。',
  provider_key_missing: '尚未保存密钥，请先粘贴并保存。',
  empty_or_truncated_response: '服务已响应，但未返回完整文本；请检查模型权限或额度。',
  http_401: '认证失败：密钥无效或已失效。',
  http_402: '账户余额或额度不足。',
  http_403: '当前密钥没有该模型的访问权限。',
  http_404: '当前模型 API ID 不可用，请恢复推荐值后重试。',
  http_429: '请求过于频繁或额度受限，请稍后再试。',
  request_failed: '连接失败：请检查网络和服务商状态。',
}

export function AISettingsPage({ repository }: { repository: TaskRepository }) {
  const [providers, setProviders] = useState<AIProviderSettings[]>([])
  const [selectedId, setSelectedId] = useState('deepseek')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [allowTest, setAllowTest] = useState(false)
  const [busy, setBusy] = useState<'load' | 'save' | 'test' | null>('load')
  const [message, setMessage] = useState('')

  const selected = useMemo(() => providers.find(item => item.id === selectedId) ?? null, [providers, selectedId])
  const sessionRemoteAIEnabled = selected?.sessionEnabled !== false
  const hasUnsavedChanges = Boolean(apiKey) || Boolean(selected && model.trim() !== selected.model)

  useEffect(() => {
    let active = true
    void repository.listAIProviders()
      .then(items => {
        if (!active) return
        const first = items[0]
        setProviders(items)
        setSelectedId(first?.id ?? 'deepseek')
        setModel(first?.model ?? '')
      })
      .catch(() => { if (active) setMessage('无法读取本地设置，请确认 Dashboard 执行服务已经启动。') })
      .finally(() => { if (active) setBusy(null) })
    return () => { active = false }
  }, [repository])

  const selectProvider = (provider: AIProviderSettings) => {
    setSelectedId(provider.id)
    setModel(provider.model)
    setApiKey('')
    setShowKey(false)
    setAllowTest(false)
    setMessage('')
  }

  const updateProvider = (value: AIProviderSettings) => {
    setProviders(items => items.map(item => item.id === value.id ? value : item))
  }

  const save = async () => {
    if (!selected || model.trim().length < 2) { setMessage('请填写有效的模型 API ID。'); return }
    setBusy('save'); setMessage('')
    try {
      const saved = await repository.saveAIProvider(selected.id, { apiKey, model: model.trim() })
      updateProvider(saved); setApiKey(''); setModel(saved.model); setAllowTest(false)
      setMessage('设置已加密保存。保存过程没有联网，也没有启用后台调用。')
    } catch { setMessage('保存失败：请检查密钥、模型 API ID 和项目目录权限。') }
    finally { setBusy(null) }
  }

  const testConnection = async () => {
    if (!selected || !allowTest) return
    if (!sessionRemoteAIEnabled) { setMessage(connectionMessages.remote_ai_disabled_for_session); setAllowTest(false); return }
    if (hasUnsavedChanges) { setMessage('当前输入尚未保存。请先保存设置，再测试刚保存的密钥和模型。'); return }
    setBusy('test'); setMessage('')
    try {
      const result = await repository.testAIProvider(selected.id)
      setMessage(connectionMessages[result.code] ?? `连接未通过：${result.code}`)
    } catch (error) {
      const code = error instanceof Error ? error.message : ''
      setMessage(connectionMessages[code] ?? '无法执行连接测试，请检查本地服务。')
    }
    finally { setBusy(null); setAllowTest(false) }
  }

  return <>
    <div className="page-heading ai-settings-heading">
      <div><h3>云端 AI 设置</h3><p>直接在平台内保存服务商密钥。只填密钥即可使用推荐模型，也可以修改模型 API ID。</p></div>
      <div className="page-heading-aside"><ShieldCheck size={17} aria-hidden="true" /><span>密钥仅本机加密保存</span></div>
    </div>

    <section className="surface-panel ai-settings-panel" aria-busy={busy === 'load'}>
      <div className="ai-provider-selector" role="tablist" aria-label="AI 服务商">
        {providers.map(item => <button key={item.id} type="button" role="tab" aria-selected={selectedId === item.id} disabled={busy === 'save' || busy === 'test'}
          className="ai-provider-tab" onClick={() => selectProvider(item)}>
          <span>{item.displayName}</span><small>{item.model}</small>
        </button>)}
      </div>

      {selected ? <div className="ai-settings-body">
        <div className="ai-provider-summary">
          <div><span className="setting-label">当前服务商</span><strong>{selected.displayName}</strong><small>固定官方地址：{selected.endpointHost}</small></div>
          <div className={selected.keySaved ? 'key-state key-state-saved' : 'key-state'}>
            {selected.keySaved ? <CheckCircle2 size={18} aria-hidden="true" /> : <KeyRound size={18} aria-hidden="true" />}
            <span>{selected.keySaved ? '已保存加密密钥' : '尚未保存密钥'}</span>
          </div>
        </div>

        <div className="ai-settings-form">
          <label className="form-field form-field-wide"><span>API 密钥</span>
            <div className="secret-input-row">
              <input aria-label="API 密钥" type={showKey ? 'text' : 'password'} value={apiKey} autoComplete="new-password" spellCheck={false}
                placeholder={selected.keySaved ? '粘贴新密钥可覆盖；留空保留现有密钥' : '在这里直接粘贴 API 密钥'} onChange={event => setApiKey(event.target.value)} />
              <button type="button" className="icon-button" aria-label={showKey ? '隐藏密钥' : '显示密钥'} onClick={() => setShowKey(value => !value)}>
                {showKey ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
              </button>
            </div><small>输入不会写入日志；保存后明文会立即从表单清空，前端无法再次读取。</small>
          </label>

          <label className="form-field form-field-wide"><span>模型 API ID</span>
            <div className="model-input-row"><input aria-label="模型 API ID" value={model} spellCheck={false} onChange={event => setModel(event.target.value)} />
              <button type="button" className="action-button" onClick={() => setModel(selected.officialModel)}><RotateCcw size={15} aria-hidden="true" /> 恢复推荐值</button>
            </div><small>推荐值：<code>{selected.officialModel}</code>。模型更名后可以在这里更新。</small>
          </label>
        </div>

        <div className="ai-settings-actions">
          <button type="button" className="action-button" data-variant="primary" disabled={busy !== null} onClick={() => void save()}>{busy === 'save' ? '正在保存…' : '保存设置'}</button>
          <label className="network-consent"><input type="checkbox" checked={allowTest} disabled={!sessionRemoteAIEnabled} onChange={event => setAllowTest(event.target.checked)} /> {sessionRemoteAIEnabled ? '允许本次联网测试（只发送“OK”测试文本，可能少量计费）' : '本次启动已禁用远程 AI，需重新启动后才能测试'}</label>
          <button type="button" className="action-button" disabled={!allowTest || busy !== null || !selected.keySaved || hasUnsavedChanges} onClick={() => void testConnection()}><Wifi size={15} aria-hidden="true" /> {busy === 'test' ? '测试中…' : hasUnsavedChanges ? '请先保存更改' : '测试连接'}</button>
        </div>
        {hasUnsavedChanges ? <div className="inline-notice ai-settings-message" role="note">当前输入尚未保存；连接测试只会使用保存成功后的密钥和模型。</div> : null}
        {!sessionRemoteAIEnabled ? <div className="inline-notice ai-settings-message" role="note">本次启动会话的远程 AI 硬门为“禁用”。密钥仍可本地保存，但不会被解密或发送。</div> : null}
        {message ? <div className="inline-notice ai-settings-message" role="status">{message}</div> : null}
      </div> : <div className="ai-settings-empty">{busy === 'load' ? '正在读取本地加密设置…' : message || '没有可用服务商配置。'}</div>}
    </section>

    <section className="surface-panel ai-safety-note"><ShieldCheck size={20} aria-hidden="true" /><div><strong>保存不等于启用</strong><p>远程 AI 仍只用于人工触发的单条候选审阅；不会自动扫描目标、确认漏洞或提交补天。费用与模型权限以服务商账户为准。</p></div></section>
  </>
}

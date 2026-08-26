import { useId, useState, type FormEvent } from 'react'
import { ClipboardCheck, RotateCcw, Save } from 'lucide-react'
import type { TargetDraft, TargetDraftResult } from '../lib/types'
import { validateTargetDraft } from '../lib/validation'

export const blankTargetDraft: TargetDraft = {
  projectName: '',
  targetUrl: '',
  allowedHosts: '',
  allowedPorts: '',
  excludedPaths: '',
  windowStart: '',
  windowEnd: '',
  allowedMethods: 'GET, HEAD',
  concurrency: '1',
  requestLimit: '100',
  authorizationNote: '',
}

type TargetFormProps = {
  initialDraft?: TargetDraft
  onSave: (result: TargetDraftResult) => void
}

type FieldProps = {
  label: string
  field: keyof TargetDraft
  value: string
  error?: string
  description?: string
  type?: 'text' | 'url' | 'datetime-local' | 'number'
  placeholder?: string
  onChange: (value: string) => void
}

function TextField({ label, field, value, error, description, type = 'text', placeholder, onChange }: FieldProps) {
  const descriptionId = useId()
  const errorId = useId()
  const describedBy = [description ? descriptionId : '', error ? errorId : ''].filter(Boolean).join(' ') || undefined
  return (
    <div className="form-field">
      <label htmlFor={field}>{label}</label>
      <input
        id={field}
        name={field}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
      />
      {description ? <small id={descriptionId}>{description}</small> : null}
      {error ? <span id={errorId} className="field-error" role="alert">{error}</span> : null}
    </div>
  )
}

function TextAreaField({ label, field, value, error, description, placeholder, onChange }: Omit<FieldProps, 'type'>) {
  const descriptionId = useId()
  const errorId = useId()
  const describedBy = [description ? descriptionId : '', error ? errorId : ''].filter(Boolean).join(' ') || undefined
  return (
    <div className="form-field form-field-wide">
      <label htmlFor={field}>{label}</label>
      <textarea
        id={field}
        name={field}
        value={value}
        placeholder={placeholder}
        rows={3}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
      />
      {description ? <small id={descriptionId}>{description}</small> : null}
      {error ? <span id={errorId} className="field-error" role="alert">{error}</span> : null}
    </div>
  )
}

export function TargetForm({ initialDraft = blankTargetDraft, onSave }: TargetFormProps) {
  const [draft, setDraft] = useState<TargetDraft>(initialDraft)
  const [errors, setErrors] = useState<Partial<Record<keyof TargetDraft, string>>>({})

  const update = (field: keyof TargetDraft) => (value: string) => {
    setDraft((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const result = validateTargetDraft(draft)
    setErrors(result.errors ?? {})
    if (result.valid) onSave(result)
  }

  const handleReset = () => {
    setDraft(initialDraft)
    setErrors({})
  }

  return (
    <form className="target-form" noValidate onSubmit={handleSubmit}>
      <div className="form-safety-note">
        <ClipboardCheck size={18} aria-hidden="true" />
        <div><strong>先保存授权草稿，再进入人工确认</strong><p>本表单只做本地校验和配置保存，不解析 DNS、不发送请求，也不会自动启动真实目标测试。</p></div>
      </div>
      <div className="form-grid">
        <TextField label="项目名称" field="projectName" value={draft.projectName} error={errors.projectName} placeholder="例如：示例授权项目" onChange={update('projectName')} />
        <TextField label="目标 URL" field="targetUrl" type="url" value={draft.targetUrl} error={errors.targetUrl} description="仅记录协议和域名，不会访问此地址。" placeholder="https://example.com/app" onChange={update('targetUrl')} />
        <TextField label="允许主机名" field="allowedHosts" value={draft.allowedHosts} error={errors.allowedHosts} description="多个主机用英文逗号分隔，可使用 *.example.com。" placeholder="example.com" onChange={update('allowedHosts')} />
        <TextField label="允许端口" field="allowedPorts" value={draft.allowedPorts} error={errors.allowedPorts} placeholder="443" onChange={update('allowedPorts')} />
        <TextField label="开始时间" field="windowStart" type="datetime-local" value={draft.windowStart} error={errors.windowStart} onChange={update('windowStart')} />
        <TextField label="结束时间" field="windowEnd" type="datetime-local" value={draft.windowEnd} error={errors.windowEnd} onChange={update('windowEnd')} />
        <TextField label="允许方法" field="allowedMethods" value={draft.allowedMethods} error={errors.allowedMethods} placeholder="GET, HEAD" onChange={update('allowedMethods')} />
        <TextField label="并发数" field="concurrency" type="number" value={draft.concurrency} error={errors.concurrency} description="建议从 1 开始，避免影响业务。" onChange={update('concurrency')} />
        <TextField label="请求上限" field="requestLimit" type="number" value={draft.requestLimit} error={errors.requestLimit} description="整个时间窗的最大请求数量。" onChange={update('requestLimit')} />
        <TextAreaField label="排除路径" field="excludedPaths" value={draft.excludedPaths} error={errors.excludedPaths} description="多个路径用英文逗号分隔，例如 /admin,/logout。" placeholder="/admin,/logout" onChange={update('excludedPaths')} />
        <TextAreaField label="授权证明或规则说明" field="authorizationNote" value={draft.authorizationNote} error={errors.authorizationNote} description="粘贴平台规则、邮件或工单编号；提交前仍需人工确认。" placeholder="项目规则明确允许在时间窗内进行低频测试。" onChange={update('authorizationNote')} />
      </div>
      <div className="form-actions">
        <button className="action-button" type="button" onClick={handleReset}><RotateCcw size={16} aria-hidden="true" /> 清空表单</button>
        <button className="action-button" data-variant="primary" type="submit"><Save size={16} aria-hidden="true" /> 保存授权草稿</button>
      </div>
    </form>
  )
}

import { CheckCircle2, FileKey2, ShieldCheck } from 'lucide-react'
import type { TargetDraftResult } from '../lib/types'
import { TargetForm } from '../components/TargetForm'
import { useEffect, useState } from 'react'
import type { TaskRepository } from '../lib/taskRepository'

type TargetDraftPageProps = {
  savedResult: TargetDraftResult | null
  onSaved: (result: TargetDraftResult) => void
  repository: TaskRepository
}

export function TargetDraftPage({ savedResult, onSaved, repository }: TargetDraftPageProps) {
  const [drafts, setDrafts] = useState<TargetDraftResult[]>([])
  const [loadError, setLoadError] = useState('')
  useEffect(() => {
    let active = true
    void repository.listDrafts().then(items => { if (active) setDrafts(items) }).catch(() => { if (active) setLoadError('历史草稿读取失败，请检查本地服务。') })
    return () => { active = false }
  }, [repository])
  const save = async (result: TargetDraftResult) => {
    const stored = await repository.saveDraft(result.draft)
    onSaved(stored)
    setDrafts(items => [stored, ...items])
  }
  return (
    <>
      <div className="page-heading">
        <div><span className="eyebrow">步骤 2 · 先写范围，再谈测试</span><h3>新建授权目标</h3><p>把补天项目规则、允许主机、端口和时间窗写入本地配置草稿；提交前始终由你人工确认。</p></div>
        <div className="page-heading-aside"><ShieldCheck size={17} aria-hidden="true" /><span>当前网络接触：无</span></div>
      </div>
      <section className="surface-panel panel-body">
        <h4>已保存草稿</h4><p>每次保存生成独立版本，重新打开页面后可继续编辑。保存不等于授权确认。</p>
        {loadError && <p role="alert">{loadError}</p>}
        <select aria-label="选择已保存草稿" value={savedResult?.id ?? ''} onChange={event => { const item = drafts.find(d => d.id === event.target.value); if (item) onSaved(item) }}>
          <option value="">选择历史草稿</option>
          {drafts.map((item, index) => <option key={item.id ?? index} value={item.id ?? String(index)}>{item.draft.projectName} — {item.savedPath ?? '测试数据'}</option>)}
        </select>
        {savedResult?.savedPath && <p>保存位置：{savedResult.savedPath}</p>}
      </section>
      <div className="target-layout">
        <TargetForm key={savedResult?.id ?? 'new'} initialDraft={savedResult?.draft} onSave={save} />
        <aside className="target-side-column">
          <section className="surface-panel scope-guide"><div className="panel-header"><div><h4>填写提示</h4><p>用最小权限描述目标范围</p></div><FileKey2 size={20} aria-hidden="true" /></div><ol><li><strong>主机和端口</strong><span>只写平台明确允许的入口。</span></li><li><strong>时间窗</strong><span>结束时间必须晚于开始时间。</span></li><li><strong>授权证明</strong><span>记录规则、工单或邮件编号。</span></li></ol></section>
          {savedResult ? <section className="surface-panel saved-draft" role="status"><div className="saved-draft-title"><CheckCircle2 size={18} aria-hidden="true" /><strong>授权草稿已保存</strong></div><p>未访问目标</p><dl><div><dt>规范化 URL</dt><dd>{savedResult.normalizedUrl}</dd></div><div><dt>范围指纹</dt><dd>{savedResult.scopeDigestSuffix}</dd></div></dl><small>下一步仍需人工复核授权范围；不会自动启动远程任务。</small></section> : <section className="surface-panel saved-draft empty-saved"><FileKey2 size={20} aria-hidden="true" /><strong>尚未保存草稿</strong><p>填写完成后，这里会显示本地校验结果。</p></section>}
        </aside>
      </div>
    </>
  )
}

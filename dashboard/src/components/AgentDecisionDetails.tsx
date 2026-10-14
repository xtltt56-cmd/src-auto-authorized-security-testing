import type { AgentRun } from '../lib/types'

const labels: Record<string, string> = {
  inspect_headers: '检查响应头', discover_surface: '有限页面发现', inspect_api_schema: '读取 API 规范',
  compare_object_authorization: '合成对象权限对照', run_local_regression: '固定靶场验收',
  validate_controlled_inputs: '固定输入对照', compare_object_authorization_matrix: '合成权限矩阵',
  inspect_local_route: '检查批准路由', analyze_passive_capture: '断网被动分析',
  compare_business_object: '四角色对象对照', validate_business_controls: '固定合成正负对照',
  review_candidate: '读取关联候选', finish: '核对完成证据', request_human_review: '转交人工复核',
}
const reasons: Record<string, string> = {
  action_not_available: '当前任务或阶段不支持该动作', action_reference_mismatch: '动作与批准对象不匹配',
  foreign_reference: '对象不属于本任务', foreign_evidence: '引用了不存在的证据', unknown_action: '动作未定义',
  forbidden_decision_field: '建议包含禁止的参数', invalid_decision_fields: '建议格式不符合四字段协议',
  invalid_proposal: '建议校验未通过', duplicate_action: '阻止重复执行', budget_limit: '任务额度不足',
  business_coverage_incomplete: '业务证据覆盖不足', local_web_coverage_incomplete: '批准路由或被动分析证据不足',
  insufficient_evidence: '没有有效完成证据', action_catalog_invalid: '动作目录不完整，已阻止执行',
}
const executors: Record<string, string> = { LocalActions: '固定靶场执行器', LocalWebActions: '本机应用执行器', BusinessActions: '隔离业务执行器' }
const actionName = (name: string) => labels[name] ?? name

export function AgentDecisionDetails({ run }: { run: AgentRun }) {
  const menu = run.actionMenu
  return <details className="agent-contract">
    <summary>动作菜单与执行校验</summary>
    <p className="agent-hint">模型建议不等于实际执行。以下菜单是最近一轮决策的批准快照；结束后不会自动继续。这里只展示短理由，不展示内部思维或凭据。</p>
    {menu ? <>
      <p>动作协议 {menu.catalogVersion} · {menu.completionReady ? '已满足程序完成条件，仍需人工复核' : '尚不满足程序完成条件'}</p>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>可选动作</th><th>批准对象</th><th>处理方式</th></tr></thead><tbody>
        {Object.entries(menu.options).map(([name, refs]) => <tr key={name}><td>{actionName(name)}</td><td>{refs.join('、')}</td><td>{['finish', 'request_human_review'].includes(name) ? '主循环控制' : '已注册工具处理函数'}</td></tr>)}
      </tbody></table></div>
      {menu.missing.length > 0 ? <><h5>尚缺必查证据</h5><ul>{menu.missing.map(item => <li key={`${item.action}:${item.reference}`}>{actionName(item.action)} · {item.reference === '*' ? '至少一个批准对象' : item.reference}</li>)}</ul></> : <p>此快照没有列出未完成的必查项；可选动作不代表必须全部执行。</p>}
    </> : <p>此历史任务或固定流程没有记录动态动作菜单；请以原始工具观察和完整报告为准。</p>}
    <h5>建议、校验与真实工具结果</h5>
    {run.trace.length > 0 ? <ol className="agent-trace">{run.trace.map(step => {
      const control = ['finish', 'request_human_review'].includes(step.decision?.action ?? '')
      const observation = run.observations.find(item => item.id === step.observationId)
      return <li key={step.index}>
        <strong>{step.index}. {step.decision ? actionName(step.decision.action) : '格式校验'} · {step.decision?.reference ?? '未形成有效对象'}</strong>
        <p>{step.source === 'required-local-recipe' ? '程序固定配方' : step.source === 'model' ? '模型建议' : '历史执行记录'} · {step.validation === 'rejected' || step.result === 'rejected' ? '校验拒绝' : step.validation === 'passed' ? '校验通过' : '旧记录未单独标注校验'}</p>
        {step.result === 'rejected' ? <p>{reasons[step.reason ?? ''] ?? '建议已被拒绝'} · <span>未调用工具</span></p> : control ? <p>控制动作 · 不调用扫描器</p> : <p>{executors[step.executor ?? ''] ?? '实际处理方式见原始记录'} · {step.result === 'ok' ? '已取得工具结果' : step.result === 'executing' ? '正在执行' : '未完成，不能当作成功'}</p>}
        {observation ? <p>{observation.id} · {observation.summary}</p> : null}
      </li>
    })}</ol> : <p>尚无已记录的决策步骤。</p>}
  </details>
}

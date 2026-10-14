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
const modelFailures: Record<string, [string, string]> = {
  model_auth_failed: ['API 密钥或权限无效', '先到系统设置检查已保存的密钥与权限，再由你人工发起连接测试。'],
  model_key_unavailable: ['无法读取已保存的 API 密钥', '先到系统设置重新保存密钥并人工连接测试；不需要把密钥发到报告或聊天里。'],
  model_rate_limited: ['云端 API 限流', '等待服务商限制解除，再人工决定是否创建新任务或续接；不会自动增加并发。'],
  model_account_unavailable: ['云端账户暂不可用', '核对服务商账户余额与权限，再进行人工连接测试。'],
  model_endpoint_unavailable: ['模型或 API 地址不可用', '在系统设置核对官方调用 ID 和端点，保存后人工连接测试。'],
  model_transport_failed: ['云端网络请求未完成', '检查网络或已配置的代理，再人工连接测试；当前观察已保留，不自动重放工具。'],
  model_service_unavailable: ['云端服务暂不可用', '等待服务恢复后先人工连接测试，再决定是否继续任务。'],
  model_input_limit: ['决策上下文达到上限', '减少本次批准的路由或对象，再重新审批并创建任务；不会静默丢弃必查证据。'],
  model_usage_invalid: ['API 用量信息无法可靠核实', '已停止继续调用，额度保守保留；先核对连接与服务商账单。'],
  model_response_invalid: ['API 返回内容异常', '先进行人工连接测试，确认模型支持当前接口协议。'],
  model_response_too_large: ['API 返回内容超出安全上限', '异常响应未被继续读取或保留，请先进行人工连接测试。'],
}

export function AgentDecisionDetails({ run }: { run: AgentRun }) {
  const menu = run.actionMenu
  const failure = run.modelFailure
  const failureInfo = failure ? modelFailures[failure.code] ?? ['模型调用未完成', '原因无法安全细分；检查系统设置并进行人工连接测试。'] : null
  return <>
    {failure && failureInfo ? <section className="model-failure-notice" role="status" aria-label="模型失败诊断">
      <strong>{failureInfo[0]}</strong><p>{failureInfo[1]}</p>
      <p>{failure.requestMayHaveBeenSent ? '请求可能已发送，用量按保护策略估算；仅云端调用可能产生费用，不等于实际账单。' : '失败发生在发送前的校验或凭据读取阶段。'}不会自动重试或切换模型。</p>
      <a href="?page=settings">打开系统设置（不会自动调用 API）</a>
    </section> : null}
    <details className="agent-contract">
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
        <strong>{step.index}. {step.decision ? actionName(step.decision.action) : step.result === 'model-failed' ? '模型调用未完成' : '格式校验'} · {step.decision?.reference ?? '未形成有效对象'}</strong>
        <p>{step.source === 'required-local-recipe' ? '程序固定配方' : step.result === 'model-failed' ? '模型请求' : step.source === 'model' ? '模型建议' : '历史执行记录'} · {step.result === 'model-failed' ? '未进入动作校验' : step.validation === 'rejected' || step.result === 'rejected' ? '校验拒绝' : step.validation === 'passed' ? '校验通过' : '旧记录未单独标注校验'}</p>
        {step.result === 'model-failed' ? <p>{modelFailures[step.reason ?? '']?.[0] ?? '模型调用未完成'} · 未形成有效建议，未调用工具</p> : step.result === 'rejected' ? <p>{reasons[step.reason ?? ''] ?? '建议已被拒绝'} · <span>未调用工具</span></p> : control ? <p>控制动作 · 不调用扫描器</p> : <p>{executors[step.executor ?? ''] ?? '实际处理方式见原始记录'} · {step.result === 'ok' ? '已取得工具结果' : step.result === 'executing' ? '正在执行' : '未完成，不能当作成功'}</p>}
        {observation ? <p>{observation.id} · {observation.summary}</p> : null}
      </li>
    })}</ol> : <p>尚无已记录的决策步骤。</p>}
  </details></>
}

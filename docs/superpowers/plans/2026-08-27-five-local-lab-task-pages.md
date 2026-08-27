# 五个本地靶场独立任务页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让五个本地回环靶场都拥有可点击的独立入口和不串台的任务详情页，同时保留五靶场聚合任务入口与本地优先安全边界。

**Architecture:** 扩展 `LabStatus`，为每个靶场提供唯一 `taskId`，并在现有夹具仓库中补充五个 `TaskSummary` 和关联脱敏事件。`LabMatrix` 只负责呈现和发出目标任务 ID；`App` 从当前快照派生关联靶场，继续复用 `TaskDetailPage` 呈现共同的进度、阶段、事件和任务操作。移动端用同一份语义化数据将表格行样式重排为卡片，不引入新框架、后端或真实目标网络访问。

**Tech Stack:** React 19、TypeScript、Vite、Vitest、Testing Library、Playwright Chromium、现有本地 `TaskRepository`、CSS 媒体查询。

---

## 文件结构和职责

- `dashboard/src/lib/types.ts`：为靶场状态定义必填的独立任务关联字段。
- `dashboard/src/lib/fixtures.ts`：为五个靶场提供任务、事件、报告映射和本地夹具标识。
- `dashboard/src/components/LabMatrix.tsx`：在桌面表格和移动端卡片中提供每靶场的可访问任务入口。
- `dashboard/src/pages/LabsPage.tsx`：保留聚合任务入口，并把独立任务打开回调交给矩阵。
- `dashboard/src/App.tsx`：由 `selectedTaskId` 派生 `selectedLab`，不新增重复状态。
- `dashboard/src/pages/TaskDetailPage.tsx`：按可选靶场上下文显示端口、健康状态、数据来源和无报告提示。
- `dashboard/src/styles/global.css`：添加靶场入口样式和窄屏卡片布局。
- `dashboard/src/pages/pages.test.tsx`：覆盖五个入口、对应标题/端口、返回路径和报告缺失提示。
- `dashboard/tests/e2e/dashboard.spec.ts`：用真实 Chromium 循环打开五个详情页并断言零外部请求。
- `dashboard/README.md`、`USER_MANUAL.md`：说明五靶场详情入口与“夹具数据不等于真实扫描成绩”的边界。

### Task 1: 写入五个独立入口的失败集成测试

**Files:**
- Modify: `dashboard/src/pages/pages.test.tsx`

- [ ] **Step 1: 为五个入口写失败测试**

在 `dashboard pages` 测试组内添加常量并增加以下测试。先不改生产代码：

```tsx
const localLabExpectations = [
  { name: 'Juice Shop', port: '127.0.0.1:3000', taskName: 'Juice Shop · 本地任务' },
  { name: 'DVWA', port: '127.0.0.1:8081', taskName: 'DVWA · 本地任务' },
  { name: 'WebGoat', port: '127.0.0.1:8082', taskName: 'WebGoat · 本地任务' },
  { name: 'VAmPI', port: '127.0.0.1:8083', taskName: 'VAmPI · 本地任务' },
  { name: 'Business API', port: '127.0.0.1:8084', taskName: 'Business API · 本地任务' },
] as const

it.each(localLabExpectations)('opens $name as an independent local task', async ({ name, port, taskName }) => {
  const user = userEvent.setup()
  render(<App repository={createFixtureRepository()} />)

  await user.click(screen.getByRole('button', { name: '本地靶场' }))
  await user.click(screen.getByRole('button', { name: `查看 ${name} 任务` }))

  expect(await screen.findByRole('heading', { name: taskName })).toBeVisible()
  expect(screen.getByText(port, { exact: true })).toBeVisible()
  await user.click(screen.getByRole('button', { name: '返回靶场列表' }))
  expect(screen.getByRole('heading', { name: '本地靶场' })).toBeVisible()
})
```

- [ ] **Step 2: 运行测试并确认预期失败**

Run:

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto\.worktrees\storybook-visual-upgrade\dashboard'
& '..\runtime\node-v22.23.0-win-x64\npm.cmd' test -- src/pages/pages.test.tsx
```

Expected: 5 个测试因找不到“查看 <靶场> 任务”按钮失败；既有测试仍可执行，不能因为 TypeScript、测试环境或依赖错误而失败。

- [ ] **Step 3: 不在此任务中修改生产代码**

失败原因必须是独立入口尚未实现。若失败原因不符，先修正测试文字或选择器，再重新运行到正确的 RED 状态。

- [ ] **Step 4: 提交失败测试**

```powershell
git add -- dashboard/src/pages/pages.test.tsx
git commit -m 'test: require per-lab task entry points'
```

### Task 2: 建立五个独立本地任务夹具

**Files:**
- Modify: `dashboard/src/lib/types.ts`
- Modify: `dashboard/src/lib/fixtures.ts`
- Test: `dashboard/src/lib/taskRepository.test.ts`

- [ ] **Step 1: 为任务映射写失败测试**

在 `taskRepository.test.ts` 添加断言，确保五个靶场都有唯一 `taskId`，并且每个 ID 可在任务集合和事件集合中找到：

```ts
it('maps every local lab to an independent local-only task with events', async () => {
  const snapshot = await createFixtureRepository().getDashboardSnapshot()
  expect(snapshot.labs).toHaveLength(5)

  for (const lab of snapshot.labs) {
    expect(lab.taskId).toMatch(/^run-lab-/)
    expect(snapshot.tasks.some((task) => task.id === lab.taskId && task.kind === 'local-lab' && task.networkContact === 'loopback')).toBe(true)
    expect(snapshot.events.some((event) => event.taskId === lab.taskId && event.redacted)).toBe(true)
  }
})
```

- [ ] **Step 2: 运行测试并确认预期失败**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' test -- src/lib/taskRepository.test.ts
```

Expected: `taskId` 不存在或每靶场任务缺失导致失败。

- [ ] **Step 3: 最小化扩展类型和夹具数据**

在 `LabStatus` 中添加必填字段：

```ts
taskId: string
```

为每个 `fixtureSnapshot.labs` 项添加以下 ID：

```ts
taskId: 'run-lab-juice-shop'
taskId: 'run-lab-dvwa'
taskId: 'run-lab-webgoat'
taskId: 'run-lab-vampi'
taskId: 'run-lab-business-api'
```

在 `fixtureSnapshot.tasks` 中为每个 ID 增加一个 `TaskSummary`。任务名称固定为：

```ts
name: 'Juice Shop · 本地任务'
kind: 'local-lab'
networkContact: 'loopback'
```

其余四个名称按靶场名称替换。任务阶段必须与对应 `LabStatus.stage` 一致；每个任务有独立计数和 `elapsedSeconds`。

在 `fixtureSnapshot.events` 中为每个任务增加至少一条 `redacted: true` 的事件，示例：

```ts
{ id: 101, taskId: 'run-lab-juice-shop', time: '23:38:12', level: 'info', stage: '受控验证', message: 'Juice Shop 本地夹具已完成低风险验证记录', tool: 'local-adapter', redacted: true }
```

- [ ] **Step 4: 运行任务仓库测试并确认通过**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' test -- src/lib/taskRepository.test.ts
```

Expected: 所有任务仓库测试通过，且不发出外部网络请求。

- [ ] **Step 5: 提交数据模型和夹具**

```powershell
git add -- dashboard/src/lib/types.ts dashboard/src/lib/fixtures.ts dashboard/src/lib/taskRepository.test.ts
git commit -m 'feat: map local labs to independent tasks'
```

### Task 3: 实现可访问的每靶场入口并让 TaskDetailPage 显示关联靶场

**Files:**
- Modify: `dashboard/src/components/LabMatrix.tsx`
- Modify: `dashboard/src/pages/LabsPage.tsx`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/pages/TaskDetailPage.tsx`
- Modify: `dashboard/src/styles/global.css`
- Test: `dashboard/src/pages/pages.test.tsx`

- [ ] **Step 1: 运行 Task 1 的失败测试，确认仍为 RED**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' test -- src/pages/pages.test.tsx
```

Expected: 五个“查看 <靶场> 任务”入口尚不存在。

- [ ] **Step 2: 修改 `LabMatrix` 回调和每行入口**

将 props 改为：

```ts
type LabMatrixProps = {
  labs: LabStatus[]
  onOpenLabTask: (taskId: string) => void
}
```

每行名称和操作列分别使用如下按钮，二者调用相同的 `lab.taskId`：

```tsx
<button className="lab-name-button" type="button" onClick={() => onOpenLabTask(lab.taskId)}>
  <span className="table-primary">{lab.name}</span>
  <span className="table-secondary">127.0.0.1:{lab.port}</span>
</button>

<button className="table-link" type="button" aria-label={`查看 ${lab.name} 任务`} onClick={() => onOpenLabTask(lab.taskId)}>
  查看任务 <ExternalLink size={14} aria-hidden="true" />
</button>
```

保留矩阵顶部“回环模式”标签，移除其中的聚合“打开任务详情”按钮，避免两个入口混淆。

- [ ] **Step 3: 连通页面和派生靶场上下文**

`LabsPage` 保留顶部聚合入口：

```tsx
onClick={() => onOpenTask('run-local-001')}
```

矩阵调用变更为：

```tsx
<LabMatrix labs={snapshot.labs} onOpenLabTask={onOpenTask} />
```

在 `App` 中从 `selectedTaskId` 派生关联靶场：

```ts
const selectedLab = useMemo(
  () => snapshot.labs.find((lab) => lab.taskId === selectedTaskId) ?? null,
  [selectedTaskId, snapshot.labs],
)
```

并将 `lab={selectedLab}` 传给 `TaskDetailPage`。返回操作必须同时保持 `activeKey` 为 `labs` 并只清空 `selectedTaskId`。

- [ ] **Step 4: 在详情页显示靶场上下文和报告缺失提示**

新增可选属性：

```ts
lab?: LabStatus | null
```

任务标题以 `task.name` 为唯一来源。安全摘要在存在 `lab` 时使用：

```tsx
<div><span>靶场地址</span><strong>127.0.0.1:{lab.port}</strong></div>
<div><span>健康状态</span><strong>{lab.health}</strong></div>
<div><span>数据来源</span><strong>本地夹具</strong></div>
```

阶段数组在“受控验证”和“候选研判”之间插入 `API 对象对比`。当 `lab?.reportId` 缺失时，`onOpenReport` 只设置通知“当前靶场尚未生成报告”，不得切换到候选与报告页面。

- [ ] **Step 5: 添加桌面与移动样式**

新增 `.lab-name-button`，让它继承文本按钮外观并保留可见焦点：

```css
.lab-name-button { display: grid; gap: 3px; width: 100%; padding: 0; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.lab-name-button:focus-visible { outline: 3px solid color-mix(in srgb, var(--color-primary) 48%, transparent); outline-offset: 3px; border-radius: 4px; }
```

在现有窄屏媒体查询中，把 `.data-table` 的 `thead` 隐藏、`tbody` 显示为网格；`tr` 显示为卡片网格，并用 `td::before { content: attr(data-label); }` 显示“健康”“当前阶段”“耗时”“候选”。操作单元占满一行，按钮占满宽度。为每个 `td` 添加对应的 `data-label`。

- [ ] **Step 6: 运行 pages 测试，确认 GREEN**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' test -- src/pages/pages.test.tsx
```

Expected: 五个参数化独立任务测试与既有页面测试全部通过。

- [ ] **Step 7: 提交 UI 交互实现**

```powershell
git add -- dashboard/src/components/LabMatrix.tsx dashboard/src/pages/LabsPage.tsx dashboard/src/App.tsx dashboard/src/pages/TaskDetailPage.tsx dashboard/src/styles/global.css dashboard/src/pages/pages.test.tsx
git commit -m 'feat: open individual local lab task pages'
```

### Task 4: 为五靶场循环浏览器路径写失败 E2E 并实现回归覆盖

**Files:**
- Modify: `dashboard/tests/e2e/dashboard.spec.ts`

- [ ] **Step 1: 写失败 Chromium 测试**

新增以下数据与测试，先不修改生产代码：

```ts
const localLabTasks = [
  ['Juice Shop', 'Juice Shop · 本地任务', '127.0.0.1:3000'],
  ['DVWA', 'DVWA · 本地任务', '127.0.0.1:8081'],
  ['WebGoat', 'WebGoat · 本地任务', '127.0.0.1:8082'],
  ['VAmPI', 'VAmPI · 本地任务', '127.0.0.1:8083'],
  ['Business API', 'Business API · 本地任务', '127.0.0.1:8084'],
] as const

test('opens every local lab as its own task without external network contact', async ({ page }) => {
  const consoleErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('request', (request) => {
    if (new URL(request.url()).hostname !== '127.0.0.1') externalRequests.push(request.url())
  })

  await page.goto('/')
  await page.getByRole('button', { name: '本地靶场' }).click()
  for (const [lab, title, port] of localLabTasks) {
    await page.getByRole('button', { name: `查看 ${lab} 任务` }).click()
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
    await expect(page.getByText(port, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '返回靶场列表' }).click()
  }
  expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
  expect(externalRequests, externalRequests.join('\n')).toEqual([])
})
```

- [ ] **Step 2: 运行测试并确认预期失败**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' run e2e -- --project=chromium --grep 'opens every local lab'
```

Expected: 因不存在“查看 Juice Shop 任务”按钮而失败。

- [ ] **Step 3: 在 Task 3 实现完成后重跑并确认 GREEN**

Run the same command.

Expected: 1 passed；外部请求数组和控制台错误数组均为空。

- [ ] **Step 4: 提交 E2E 覆盖**

```powershell
git add -- dashboard/tests/e2e/dashboard.spec.ts
git commit -m 'test: cover individual local lab task navigation'
```

### Task 5: 验收窄屏布局、真实回环端口和用户文档

**Files:**
- Modify: `dashboard/tests/e2e/responsive.spec.ts`
- Modify: `dashboard/README.md`
- Modify: `USER_MANUAL.md`

- [ ] **Step 1: 为手机端五入口写失败断言**

在现有响应式测试中设置 `390 × 844`，进入“本地靶场”，断言五个 `查看 <靶场> 任务` 按钮可见，并断言：

```ts
expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
```

- [ ] **Step 2: 运行响应式测试并确认预期失败**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' run e2e -- --project=chromium --grep 'mobile local lab'
```

Expected: 入口尚未实现或窄屏布局尚未满足时失败。

- [ ] **Step 3: 实施最小 CSS 修正后重跑 GREEN**

仅调整 `global.css` 中的窄屏靶场矩阵规则，不能通过隐藏靶场、减少信息或放宽滚动断言来让测试通过。

- [ ] **Step 4: 只探测五个本机回环端口**

Run:

```powershell
$ports = 3000, 8081, 8082, 8083, 8084
$ports | ForEach-Object {
  $open = Test-NetConnection -ComputerName '127.0.0.1' -Port $_ -InformationLevel Quiet -WarningAction SilentlyContinue
  [pscustomobject]@{ Host = '127.0.0.1'; Port = $_; TcpOpen = $open }
} | Format-Table -AutoSize
```

Expected: 逐项输出端口结果。端口不可达时记录为失败，不启动外部连接、不修改 Docker 配置，且不把前端夹具状态改成成功。

- [ ] **Step 5: 更新用户说明**

在 `dashboard/README.md` 和根目录 `USER_MANUAL.md` 中增加“查看单个本地靶场任务”说明：进入本地靶场，点击靶场名称或“查看任务”；页面只显示本地夹具任务数据，端口连通性需以验收结果为准。

- [ ] **Step 6: 提交响应式测试与文档**

```powershell
git add -- dashboard/tests/e2e/responsive.spec.ts dashboard/README.md USER_MANUAL.md dashboard/src/styles/global.css
git commit -m 'docs: explain individual local lab task views'
```

### Task 6: 完整验证与可视化证据

**Files:**
- No production file changes expected.

- [ ] **Step 1: 运行完整前端测试**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' test
```

Expected: Vitest 0 failures.

- [ ] **Step 2: 运行 lint 和生产构建**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' run lint
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' run build
```

Expected: 两个命令退出码为 0。

- [ ] **Step 3: 运行完整 Chromium E2E**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' run e2e -- --project=chromium
```

Expected: 所有测试通过；测试中的外部请求和浏览器控制台错误断言均为空。

- [ ] **Step 4: 运行 Storybook 静态构建**

Run:

```powershell
& '.\runtime\node-v22.23.0-win-x64\npm.cmd' run build-storybook
```

Expected: 退出码为 0。若仅有不阻断的 chunk-size 建议，记录为已知构建提示。

- [ ] **Step 5: 截图并人工检查**

使用 `tools/start_dashboard.ps1` 启动仅回环 Dashboard，在桌面 `1366 × 900` 和手机 `390 × 844` 分别打开“本地靶场”，截图检查：五个入口可见、按钮文字可读、无裁切、无重叠、无横向溢出。截图仅写入 `validation/visual/`，不纳入 Git。

- [ ] **Step 6: 检查提交范围**

Run:

```powershell
git diff --check
git status --short
git log --oneline -8
```

Expected: 无计划外源码变更；既有 `__pycache__` 与临时浏览器文件不得被暂存或提交。

- [ ] **Step 7: 最终提交（如有未提交的文档或测试变更）**

```powershell
git add -- dashboard USER_MANUAL.md
git commit -m 'test: verify local lab task visualization'
```

仅在 `git diff --cached --name-only` 确认不含 `__pycache__`、`.playwright-cli`、`node_modules`、`dist` 和截图后执行。


# 代码优先 Storybook 可视化升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, and load each linked detailed plan before changing code. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有 Python/PowerShell 安全边界的前提下，新增一个中文优先、可点击、可观察、可回退的 React + Vite 本地控制台，先用本地夹具完成任务可视化纵向切片。

**Architecture:** `dashboard/` 是独立前端包，默认从内置 fixture repository 读取任务、事件、Finding 和报告；repository 接口保留未来接入回环 FastAPI/SSE 的替换点。旧 WinForms/CLI 和运行期数据不覆盖，新前端先通过独立启动脚本验证，所有状态操作均在浏览器本地完成。

**Tech Stack:** Node.js 项目专用运行时（安装到 D 盘）、React 18+、TypeScript、Vite、Vitest、Testing Library、Storybook、Playwright、shadcn/ui 组件约定、CSS 变量设计令牌、Lucide 图标。

---

## Task 1: 建立前端包与 D 盘运行时

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/vite-env.d.ts`
- Create: `dashboard/.storybook/main.ts`
- Create: `dashboard/.storybook/preview.ts`
- Modify: `.gitignore`
- Test: `dashboard/package.json` scripts and `npm run build`

- [ ] **Step 1: 检查并准备 D 盘 Node 运行时**

运行：

```powershell
$nodeRoot = 'D:\网络安全文件夹\SRC-Auto\runtime\node'
if (-not (Test-Path -LiteralPath $nodeRoot)) { New-Item -ItemType Directory -Force -Path $nodeRoot | Out-Null }
```

如果系统未提供 `node` 和 `npm`，使用 Node.js LTS Windows zip 解压到该目录，并在当前进程把 `$env:Path` 前置为该目录；不得写入用户密钥、项目数据库或系统目录。

- [ ] **Step 2: 生成 React + Vite TypeScript 包**

在项目根目录运行：

```powershell
if (-not (Test-Path -LiteralPath 'dashboard\package.json')) {
  npm create vite@latest dashboard -- --template react-ts
}
Set-Location 'dashboard'
npm install
npm install react-router-dom lucide-react
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @playwright/test storybook @storybook/react-vite @storybook/addon-essentials @storybook/addon-interactions @storybook/addon-a11y
```

若 `npm create vite` 版本提示不兼容，使用同一版本的 `create-vite` 在本地生成同样的目录，不改变 React + Vite 结构。

- [ ] **Step 3: 初始化 shadcn/ui 信息并记录组件策略**

运行：

```powershell
npx shadcn@latest info
```

若当前 CLI 能识别 Vite 项目，则运行 `npx shadcn@latest init` 并选择 TypeScript、CSS variables、`new-york` 风格，把组件放入 `dashboard/src/components/ui`。若 CLI 与当前 Node 版本不兼容，保留 CSS 变量和可访问原生控件实现，并在 `docs/design/code-first-component-map.md` 记录兼容原因；不引入半成品组件。

- [ ] **Step 4: 设置 npm scripts 与忽略规则**

`dashboard/package.json` 必须包含以下脚本：

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 127.0.0.1",
    "test": "vitest run",
    "test:watch": "vitest",
    "storybook": "storybook dev -p 6006 --host 127.0.0.1",
    "build-storybook": "storybook build",
    "e2e": "playwright test"
  }
}
```

`.gitignore` 新增：`dashboard/node_modules/`、`dashboard/dist/`、`dashboard/playwright-report/`、`dashboard/test-results/`，保留 `package-lock.json`。

- [ ] **Step 5: 验证基础包**

运行：`npm run build`、`npm test -- --passWithNoTests`。预期：构建退出码为 0，测试命令退出码为 0。

- [ ] **Step 6: Commit**

```powershell
git add dashboard .gitignore
git commit -m "chore: scaffold local dashboard toolchain"
```

## Task 2: 建立类型、夹具和可替换 repository

**Files:**
- Create: `dashboard/src/lib/types.ts`
- Create: `dashboard/src/lib/fixtures.ts`
- Create: `dashboard/src/lib/taskRepository.ts`
- Create: `dashboard/src/lib/taskRepository.test.tsx`
- Create: `dashboard/src/test/setup.ts`
- Modify: `dashboard/vite.config.ts`

- [ ] **Step 1: 写失败测试（RED）**

在 `taskRepository.test.tsx` 写入以下行为：`getDashboardSnapshot()` 返回一条运行中的本地任务、五个靶场、脱敏事件和至少一个候选；`pauseTask()` 把状态改为 `paused`；`resumeTask()` 把状态改回 `running`；`cancelTask()` 后事件数量不再增加。

```ts
it('returns a local-only snapshot with five labs and redacted events', async () => {
  const repository = createFixtureRepository();
  const snapshot = await repository.getDashboardSnapshot();
  expect(snapshot.tasks[0].networkContact).toBe('loopback');
  expect(snapshot.labs).toHaveLength(5);
  expect(snapshot.events.every((event) => event.redacted)).toBe(true);
  expect(snapshot.findings.length).toBeGreaterThan(0);
});

it('pauses and cancels a task without adding post-cancel events', async () => {
  const repository = createFixtureRepository();
  await repository.pauseTask('run-local-001');
  expect((await repository.getTask('run-local-001')).state).toBe('paused');
  await repository.cancelTask('run-local-001');
  const count = (await repository.getEvents('run-local-001')).length;
  await repository.resumeTask('run-local-001');
  expect((await repository.getTask('run-local-001')).state).toBe('cancelled');
  expect((await repository.getEvents('run-local-001')).length).toBe(count);
});
```

- [ ] **Step 2: 运行测试确认正确失败（RED）**

运行：`npm test -- src/lib/taskRepository.test.tsx`。预期：因类型、fixture repository 和方法尚未定义而失败，不允许跳过该失败证据。

- [ ] **Step 3: 写入最小类型和 fixture 实现（GREEN）**

在 `types.ts` 定义 `TaskState`、`TaskKind`、`TaskSummary`、`TaskEvent`、`LabStatus`、`Finding`、`ReportFile`、`DashboardSnapshot`；在 `fixtures.ts` 返回固定的五靶场和脱敏任务数据；在 `taskRepository.ts` 实现 `TaskRepository` 接口和 `createFixtureRepository()`，所有写操作只修改内存 fixture。

- [ ] **Step 4: 运行测试确认通过（GREEN）**

运行：`npm test -- src/lib/taskRepository.test.tsx`。预期：测试通过且无控制台错误。

- [ ] **Step 5: 加入未来 API 替换点**

定义 `createLoopbackRepository(baseUrl, sessionToken)` 的接口骨架，但在当前版本返回显式错误 `LOOPBACK_ADAPTER_NOT_ENABLED`，禁止 fixture 模式自动请求网络。只有在桌面壳阶段通过授权握手后才实现该适配器。

- [ ] **Step 6: Commit**

```powershell
git add dashboard/src/lib dashboard/src/test dashboard/vite.config.ts
git commit -m "feat: add typed local task fixture repository"
```

## Task 3: 设计令牌、应用壳和可访问状态组件

**Files:**
- Create: `dashboard/src/styles/tokens.css`
- Create: `dashboard/src/styles/global.css`
- Create: `dashboard/src/components/AppShell.tsx`
- Create: `dashboard/src/components/StatusBadge.tsx`
- Create: `dashboard/src/components/ProgressBar.tsx`
- Create: `dashboard/src/components/MetricStrip.tsx`
- Create: `dashboard/src/components/StageRail.tsx`
- Create: `dashboard/src/components/StatusBadge.stories.tsx`
- Create: `dashboard/src/components/ProgressBar.stories.tsx`
- Create: `dashboard/src/components/AppShell.test.tsx`

- [ ] **Step 1: 写失败测试（RED）**

测试 `AppShell` 渲染中文导航、当前选中项和 `main` landmark；测试 `StatusBadge` 为 `blocked` 同时输出中文文本、图标标签和 `aria-label`；测试 `ProgressBar` 输出正确的 `aria-valuenow`。

```tsx
it('renders clickable Chinese navigation and selected state', async () => {
  const onNavigate = vi.fn();
  render(<AppShell activeKey="overview" onNavigate={onNavigate}>{null}</AppShell>);
  await userEvent.click(screen.getByRole('button', { name: '本地靶场' }));
  expect(onNavigate).toHaveBeenCalledWith('labs');
  expect(screen.getByRole('main')).toBeVisible();
});
```

- [ ] **Step 2: 运行测试确认失败（RED）**

运行：`npm test -- src/components/AppShell.test.tsx`。预期：组件文件不存在导致失败。

- [ ] **Step 3: 实现令牌和最小组件（GREEN）**

令牌必须采用规格中的 `--color-ink-950`、`--color-surface`、`--color-primary`、`--color-success`、`--color-warning` 和 `--color-danger`；`AppShell` 使用原生 `button`、`nav`、`main`，按钮最小 40px，焦点环可见；`StatusBadge` 根据状态选择 Lucide 图标并保留中文文字；`StageRail` 用列表语义；`MetricStrip` 不引入虚假指标。

- [ ] **Step 4: 运行单测和 Storybook 构建**

运行：`npm test -- src/components/AppShell.test.tsx`、`npm run build-storybook`。预期：全部通过，Storybook 构建退出码为 0。

- [ ] **Step 5: Commit**

```powershell
git add dashboard/src/components dashboard/src/styles
git commit -m "feat: add accessible Chinese dashboard shell"
```

## Task 4: 总览、靶场矩阵和实时任务详情

**Files:**
- Create: `dashboard/src/pages/OverviewPage.tsx`
- Create: `dashboard/src/pages/LabsPage.tsx`
- Create: `dashboard/src/pages/TaskDetailPage.tsx`
- Create: `dashboard/src/components/LabMatrix.tsx`
- Create: `dashboard/src/components/EventTimeline.tsx`
- Create: `dashboard/src/components/ActionBar.tsx`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/pages/pages.test.tsx`

- [ ] **Step 1: 写失败测试（RED）**

测试首页三条入口、五靶场列表、实时任务状态和动作按钮：点击“暂停”后显示“已暂停”，点击“继续”恢复，点击“停止”后状态为“已取消”且按钮禁用；点击事件行显示脱敏详情。

```tsx
it('updates task detail through pause, resume and stop actions', async () => {
  render(<App repository={createFixtureRepository()} />);
  await userEvent.click(screen.getByRole('button', { name: '本地靶场' }));
  await userEvent.click(screen.getByRole('button', { name: '打开任务详情' }));
  await userEvent.click(screen.getByRole('button', { name: '暂停任务' }));
  expect(await screen.findByText('已暂停')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: '继续任务' }));
  expect(await screen.findByText('运行中')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: '停止任务' }));
  expect(await screen.findByText('已取消')).toBeVisible();
});
```

- [ ] **Step 2: 运行测试确认失败（RED）**

运行：`npm test -- src/pages/pages.test.tsx`。预期：页面或按钮尚未实现而失败。

- [ ] **Step 3: 实现页面与状态更新（GREEN）**

`App.tsx` 使用 React Router 的本地路由或等价的显式页面状态；`OverviewPage` 显示安全边界；`LabsPage` 显示五靶场的健康/阶段/候选；`TaskDetailPage` 订阅 repository 状态并把 `pauseTask`、`resumeTask`、`cancelTask` 绑定到原生按钮；`EventTimeline` 支持等级筛选；`ActionBar` 在操作后给出 `role="status"` 消息。

- [ ] **Step 4: 运行测试确认通过（GREEN）**

运行：`npm test -- src/pages/pages.test.tsx`、`npm run build`。预期：全部通过，TypeScript 构建退出码为 0。

- [ ] **Step 5: Commit**

```powershell
git add dashboard/src/App.tsx dashboard/src/pages dashboard/src/components
git commit -m "feat: add overview lab matrix and live task view"
```

## Task 5: 授权草稿、Finding 详情与安全报告查看

**Files:**
- Create: `dashboard/src/pages/TargetDraftPage.tsx`
- Create: `dashboard/src/pages/FindingsPage.tsx`
- Create: `dashboard/src/components/TargetForm.tsx`
- Create: `dashboard/src/components/FindingList.tsx`
- Create: `dashboard/src/components/FindingDetail.tsx`
- Create: `dashboard/src/components/ReportViewer.tsx`
- Create: `dashboard/src/lib/validation.ts`
- Create: `dashboard/src/lib/validation.test.ts`

- [ ] **Step 1: 写失败测试（RED）**

测试空目标 URL、非法端口、结束时间早于开始时间和缺少授权证明时给出中文错误；测试合法草稿只改变本地状态并显示“未访问目标”；测试报告文件路径必须位于项目根目录 allowlist，路径穿越被拒绝。

- [ ] **Step 2: 运行测试确认失败（RED）**

运行：`npm test -- src/lib/validation.test.ts`。预期：验证函数不存在而失败。

- [ ] **Step 3: 实现验证、表单和只读预览（GREEN）**

`validation.ts` 暴露 `validateTargetDraft` 和 `isSafeReportPath`；`TargetForm` 通过 `label` 关联输入、使用 `aria-describedby` 提示，并把保存事件交给 fixture repository；`FindingDetail` 只显示脱敏证据；`ReportViewer` 使用纯文本 `<pre>` 或 JSON 展开，不插入 `dangerouslySetInnerHTML`，并显示文件名、大小和“脚本不会执行”。

- [ ] **Step 4: 运行测试确认通过（GREEN）**

运行：`npm test -- src/lib/validation.test.ts src/pages/pages.test.tsx`、`npm run build`。预期：通过且无网络请求。

- [ ] **Step 5: Commit**

```powershell
git add dashboard/src/pages/TargetDraftPage.tsx dashboard/src/pages/FindingsPage.tsx dashboard/src/components dashboard/src/lib
git commit -m "feat: add target draft finding and safe report views"
```

## Task 6: Storybook 状态覆盖与浏览器验收

**Files:**
- Create: `dashboard/playwright.config.ts`
- Create: `dashboard/tests/e2e/dashboard.spec.ts`
- Create: `dashboard/tests/e2e/responsive.spec.ts`
- Create: `dashboard/src/components/TaskDetailPage.stories.tsx`
- Create: `dashboard/src/components/TargetForm.stories.tsx`
- Create: `dashboard/src/components/ReportViewer.stories.tsx`
- Create: `docs/validation/visual-upgrade-2026-08-26.md`

- [ ] **Step 1: 写浏览器失败用例（RED）**

Playwright 用例覆盖：首页导航、本地靶场启动、暂停/继续/停止、报告查看、授权草稿校验、移动宽度；先运行一次确认当前实现缺失的路径确实失败。

运行：`npm run dev -- --host 127.0.0.1`（另开终端）和 `npm run e2e -- --project=chromium`。预期：至少一个断言失败，失败原因属于尚未实现的页面行为。

- [ ] **Step 2: 补齐核心交互并通过浏览器测试（GREEN）**

运行：`npm run e2e -- --project=chromium`。预期：桌面和移动用例全部通过，监听地址只有 `127.0.0.1`，第三方请求计数为 0，控制台错误计数为 0。

- [ ] **Step 3: 生成 Storybook 和视觉截图**

运行：`npm run build-storybook`，启动 `npm run storybook -- --ci`；用 Playwright 截取 1366×768、1920×1080、390×844 页面截图到 `validation/visual/`。检查导航、标题、按钮、状态文字、面板边界和安全提示。

- [ ] **Step 4: 写入视觉对照记录**

`docs/validation/visual-upgrade-2026-08-26.md` 列出至少五个比较点：布局、颜色、中文文案、按钮可点击状态、响应式/无裁切；每项记录参考稿路径、浏览器截图路径、修复内容或明确的有意差异。

- [ ] **Step 5: Commit**

```powershell
git add dashboard docs/validation
git commit -m "test: cover dashboard stories and browser workflows"
```

## Task 7: 启动器接入与双入口回退

**Files:**
- Create: `tools/start_dashboard.ps1`
- Create: `dashboard/README.md`
- Modify: `START_SYSTEM.ps1`
- Modify: `README.md`
- Create: `tests/test_dashboard_launcher.py`

- [ ] **Step 1: 写 PowerShell 回归测试（RED）**

测试启动脚本包含 `127.0.0.1`、拒绝外部 URL、检查 `dashboard\dist\index.html`、保留 `-LegacyGui` 参数，并在缺少构建产物时返回明确中文错误。

- [ ] **Step 2: 运行测试确认失败（RED）**

运行：`python -m unittest tests.test_dashboard_launcher -v`。预期：新脚本不存在而失败。

- [ ] **Step 3: 实现启动脚本（GREEN）**

`tools/start_dashboard.ps1` 只启动本地 `npm run preview` 或静态服务器到 `127.0.0.1`，生成项目目录内日志，健康检查失败时提示浏览器/旧 WinForms 回退；`START_SYSTEM.ps1` 增加显式 `-Dashboard`，默认行为保持旧入口，直到 G2/G3 验收通过。

- [ ] **Step 4: 运行 Python、PowerShell 语法和前端构建**

运行：`python -m unittest tests.test_dashboard_launcher -v`、`pwsh -NoProfile -Command "\$null = [System.Management.Automation.Language.Parser]::ParseFile('tools/start_dashboard.ps1',[ref]\$null,[ref]\$null); if(\$?) { exit 0 } else { exit 1 }"`、`npm run build`。预期：全部通过。

- [ ] **Step 5: Commit**

```powershell
git add tools/start_dashboard.ps1 START_SYSTEM.ps1 README.md dashboard/README.md tests/test_dashboard_launcher.py
git commit -m "feat: add dashboard launcher with legacy fallback"
```

## Task 8: 发布验收、回归和文档

**Files:**
- Create: `docs/validation/code-first-visual-gate.md`
- Create: `docs/部署与恢复手册.md`
- Modify: `docs/THREE_PHASE_USER_MANUAL.md`
- Modify: `USER_MANUAL.md`

- [ ] **Step 1: 运行完整前端验证**

运行：`npm test`、`npm run build`、`npm run build-storybook`、`npm run e2e -- --project=chromium`。记录通过数、失败数、浏览器控制台错误数、第三方请求数和截图尺寸。

- [ ] **Step 2: 运行现有 Python 回归**

运行：`python -m unittest discover -s tests -p 'test_*.py'`。预期：不少于基线 239 个测试通过，新增启动器测试通过；任何差异写入报告，不把未执行项写成通过。

- [ ] **Step 3: 运行敏感信息和产物扫描**

仅扫描源码、配置模板、文档和锁文件，检查 `sk-`、Bearer 值、Cookie、密码赋值、`.db`、`.sqlite`、`logs`、`reports`、`validation` 运行产物是否进入暂存区；输出只包含文件名和计数，不输出密钥。

- [ ] **Step 4: 完成回退演练**

运行：`& '.\tools\restore-pre-storybook-baseline.ps1' -Destination 'D:\网络安全文件夹\SRC-Auto\.worktrees\rollback-pre-storybook-test'`，确认新目录从 `baseline-pre-storybook-20260826` 创建且原项目数据未改变，然后删除该临时工作树目录时使用 `git worktree remove` 并保留原运行期目录。

- [ ] **Step 5: 记录门禁和下一阶段边界**

在 `docs/validation/code-first-visual-gate.md` 记录 G0-UI 结果、截图、回退基线、已知限制，并明确：本轮只完成本地 fixture 可视化；FastAPI/SSE、WebView2 和授权目标模拟仍需各自门禁，不得因为前端通过就启用真实目标。

- [ ] **Step 6: Commit**

```powershell
git add docs/validation docs/部署与恢复手册.md docs/THREE_PHASE_USER_MANUAL.md USER_MANUAL.md
git commit -m "docs: record code-first visual gate and recovery"
```

## 实施完成后的验证命令

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto\.worktrees\storybook-visual-upgrade\dashboard'
npm test
npm run build
npm run build-storybook
npm run e2e -- --project=chromium
Set-Location '..'
python -m unittest discover -s tests -p 'test_*.py'
```

只有上述命令和敏感信息扫描都有新鲜证据，才能在验收报告中声称代码优先可视化门禁通过。旧入口、基线标签和回退脚本必须保持可用。

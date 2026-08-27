# SRC-Auto 本地可视化控制台

这是 SRC-Auto 的代码优先中文控制台。它默认使用固定本地夹具展示任务、五个本地靶场、事件、候选和报告查看流程；不会因为在表单中输入域名就访问目标，也不会自动调用远程 AI。

## 启动

推荐从项目根目录运行（PowerShell）：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
.\tools\start_dashboard.ps1
```

脚本只监听 `127.0.0.1`，服务就绪后打开默认浏览器。若不想自动打开浏览器，可使用：

```powershell
.\tools\start_dashboard.ps1 -NoBrowser
```

桌面/旧入口也支持显式参数：

```powershell
.\START_SYSTEM.ps1 -Dashboard
.\START_SYSTEM.ps1 -LegacyGui
```

`START_SYSTEM.ps1` 不带参数时仍保持原有 WinForms 控制台入口；`-RunLocalLab` 仍只用于五个回环靶场流程。Dashboard 入口不会启动 Docker、靶场或真实目标测试。

## 开发和验收

项目使用 D 盘中的专用 Node.js 运行时。依赖已经锁定在 `package-lock.json`，`node_modules` 和构建产物不进入 Git。

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto\dashboard'
npm test
npm run build
npm run build-storybook
npm run e2e -- --project=chromium
```

Storybook 用于查看 `StatusBadge`、`ProgressBar`、任务详情、目标表单和报告查看器的状态变体。Playwright 测试只使用 `127.0.0.1`，并检查没有外部请求和浏览器控制台错误。

## 结构

- `src/lib/types.ts`：任务、靶场、事件、Finding 和报告的类型；
- `src/lib/fixtures.ts`：脱敏的固定本地演示数据；
- `src/lib/taskRepository.ts`：可替换的数据访问接口，当前只有内存 fixture 实现；
- `src/pages/`：概览、靶场、任务详情、授权草稿和候选/报告页面；
- `src/components/`：状态、进度、事件、表单、Finding 和报告等可复用组件；
- `tests/e2e/`：桌面交互、响应式和视觉截图验收。

## 安全边界

当前版本是本地可视化纵向切片。目标录入只保存草稿并生成范围摘要；报告查看器只按 `reports/` 或 `validation/` 白名单读取文本，脚本不会执行。真实目标的回环 API、SSE、WebView2、Burp/ZAP 编排和远程 AI 仍需独立安全门禁，不因前端页面构建成功而自动启用。

升级前回退点为标签 `baseline-pre-storybook-20260826`，恢复方式见 `docs/recovery/pre-storybook-rollback.md`。

# SRC-Auto 本地可视化控制台

这是 SRC-Auto 的代码优先中文控制台。正式启动时，它连接仅监听 `127.0.0.1` 的本地控制服务，读取五个靶场的真实容器状态、保存目标草稿、离线审阅范围，并显示项目中已有的脱敏候选和报告正文。输入域名只会保存未确认草稿，不会因此访问目标，也不会自动调用远程 AI。

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

`START_SYSTEM.ps1` 不带参数时仍保持原有 WinForms 控制台入口；`-RunLocalLab` 仍只用于五个回环靶场流程。Dashboard 启动时不会自动启动 Docker、靶场或真实目标测试；进入“本地靶场”后必须由人工点击固定的启动、停止或重置按钮。

## 查看单个本地靶场任务

进入左侧的“本地靶场”后，每个靶场名称和对应的“查看任务”按钮都可以打开独立任务页。详情页会显示该靶场的固定回环端口、真实健康状态和脱敏控制事件；“打开环境任务”是五靶场聚合生命周期入口。

“环境已就绪”只证明固定容器及回环健康端点可用，不代表漏洞扫描、候选复现或报告生成已经完成。Dashboard 不会因为查看任务页而启动靶场、访问真实目标或调用远程 AI。开发测试可显式使用内存 fixture，但正式启动不会把 fixture 冒充实时结果。

## 目标草稿、离线审阅和报告

- “目标与授权”每次保存都会在 `config/targets/dashboard-<随机标识>/` 创建新的不可变草稿版本；草稿始终保持 `confirmed: false` 和 `allow_network_contact: false`。
- “离线审阅”从 `config/targets` 顶层列出项目，不要求用户逐级进入子文件夹，也不会产生目标网络请求。
- “候选与报告”从本地结果数据库及项目 `reports/` 白名单目录读取数据。点击报告后可在页面查看经过长度限制和敏感信息脱敏的正文预览。
- 本地控制服务重启后，前端会自动更新会话令牌一次；连接中断时页面明确显示“状态未知”，不会把失联误报为任务已停止。

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
- `src/lib/taskRepository.ts`：本地回环 API 与开发 fixture 的数据访问实现；
- `src/pages/`：概览、靶场、任务详情、授权草稿和候选/报告页面；
- `src/components/`：状态、进度、事件、表单、Finding 和报告等可复用组件；
- `tests/e2e/`：桌面交互、响应式和视觉截图验收。

## 安全边界

目标录入只保存草稿并生成范围摘要；报告查看器只按项目 `reports/` 白名单读取文本，文件不会执行，符号链接会被拒绝。真实目标执行、Burp/ZAP 编排和远程 AI 仍需独立安全门禁，不因前端页面或草稿保存成功而自动启用。

升级前回退点为标签 `baseline-pre-storybook-20260826`，恢复方式见 `docs/recovery/pre-storybook-rollback.md`。

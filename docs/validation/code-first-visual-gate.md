# G0-UI 代码优先可视化门禁

## 结论

G0-UI（中文可视化纵向切片）已在隔离工作树中通过。该结论只覆盖前端页面的可访问性、真实点击
反馈、固定本地夹具数据和浏览器布局，不代表真实目标扫描、漏洞确认、远程 AI 或补天自动提交已启用。

## 实现范围

- React + TypeScript + Vite 独立包：`dashboard/`；
- CSS 设计令牌、深蓝/绿色安全语义色、窄屏响应式布局；
- 概览、五靶场矩阵、任务详情、目标草稿、候选 Finding、报告只读查看；
- 任务暂停/继续/停止、事件详情选择、草稿校验/保存、报告路径白名单；
- Storybook 状态变体和 Playwright 桌面/移动回归；
- `tools/start_dashboard.ps1` 和 `START_SYSTEM.ps1 -Dashboard` 本地启动入口。

## 门禁证据

| 门禁 | 命令/证据 | 结果 |
| --- | --- | --- |
| 单元 | `npm test` | 4 个文件、13 个测试通过 |
| TypeScript/生产构建 | `npm run build` | 通过 |
| Storybook | `npm run build-storybook` | 通过；仅有 bundle 体积提示 |
| 浏览器交互 | `npm run e2e -- --project=chromium` | 4 个测试通过 |
| 浏览器安全断言 | Playwright 请求/控制台监听 | 外部请求 0，控制台错误 0 |
| 响应式 | 390×844 截图及 `scrollWidth` 断言 | 无水平溢出、核心按钮可见 |
| Python 启动器契约 | `python -m unittest tests.test_dashboard_launcher -v` | 3 个测试通过 |
| 视觉对照 | `docs/validation/visual-upgrade-2026-08-26.md` | 布局、颜色、中文、点击、响应式逐项记录 |

截图证据（生成于隔离工作树，运行产物不提交）：

- `validation/visual/overview-1366x768.png`；
- `validation/visual/overview-1920x1080.png`；
- `validation/visual/overview-390x844.png`。

## 安全门禁

1. 默认 repository 为内存 fixture；`createLoopbackRepository` 明确返回未启用错误，不会隐式发出请求。
2. 目标表单只保存授权草稿，禁止带凭据 URL，要求允许主机、端口、时间窗和授权说明；保存结果标记为“未访问目标”。
3. Finding/报告为只读脱敏视图；报告路径仅允许 `reports/` 和 `validation/`，拒绝绝对路径、盘符路径、查询/片段和路径穿越。
4. 启动器只绑定 `127.0.0.1`，不启动 Docker、靶场、Ollama 或远程 AI；旧 WinForms 入口仍可用。
5. 生产代码中没有空操作点击处理；Storybook 的演示回调仅用于隔离展示，不是生产流程。

## 未通过/未执行项

以下能力没有被 G0-UI 宣称为完成，必须单独立项和门禁：

- FastAPI/SSE 实时事件后端及断线恢复；
- WebView2 桌面嵌入和旧 GUI 的数据双向同步；
- Burp/ZAP 代理编排和真实授权目标的执行；
- 真实补天项目的网络接触、漏洞确认和自动提交；
- 远程 DeepSeek/OpenRouter/OpenAI 调用；
- 多用户权限、并发任务持久化和跨进程状态一致性。

## 回退基线

可视化升级前基线为标签 `baseline-pre-storybook-20260826`（提交 `cfd9d2d`）。使用
`tools/restore-pre-storybook-baseline.ps1` 在新的 D 盘工作树中恢复，不覆盖当前项目数据。详细
步骤见 `docs/部署与恢复手册.md` 与 `docs/recovery/pre-storybook-rollback.md`。

## Figma 再验证记录

2026-08-27 通过 Figma 连接检查确认账号已登录（Starter 计划、View seat）。随后读取既有设计文件
`hhtvhdSdfMM85CvSIkTpCy` 的元数据时，Figma MCP 返回 Starter 计划调用额度限制（rate-limit paywall）。
根据 Figma skill 的错误恢复规则，本轮停止继续调用 Figma，不把额度错误误判为设计文件损坏；现有本地
参考 PNG、代码优先实现和浏览器截图仍作为 G0-UI 验收依据。额度恢复或升级后，可再进行只读元数据/截图
校对，不需要重做当前控制台。

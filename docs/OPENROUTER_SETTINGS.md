# OpenRouter 密钥与模型设置

本机检查日期：2026-09-05。保存的 OpenRouter 密钥通过了官方 `/api/v1/key` 认证；旧配置 `stealth/ox-alpha` 已不在当时的官方模型目录中。没有证据确认其新的名称，因此不能把任意替代模型称为 Ox Alpha 的更名版本。

## 使用入口

- 新版 Dashboard：左侧「系统设置」→「打开 OpenRouter 密钥与模型设置」。本地控制服务需运行在 127.0.0.1:4174。
- 原桌面控制台：「AI 模型与密钥设置」→「OpenRouter 密钥与模型设置」。
- 也可运行项目中的 `tools/openrouter_settings_gui.ps1`（Windows PowerShell，STA 模式）。

## 操作步骤

1. 查看密钥状态。显示「已保存」时不需要再次粘贴；只有替换密钥时才点击「粘贴 / 更换密钥」。新密钥继续使用 Windows DPAPI 加密保存，界面不会读出旧密钥。
2. 勾选「本窗口允许联网检查 OpenRouter」。此选项默认关闭，关闭窗口即失效，不启用平台后台 AI。
3. 点击「刷新官方模型目录」。目录来自 OpenRouter 官方 `/api/v1/models`，仅列出支持文本输出和 `response_format` 的模型。默认只显示输入、输出 token 价格均为零的模型；免费模型仍可能有配额限制。
4. 选择模型，或粘贴精确的 API 模型 ID。仅支持保存本次已读取目录中的 ID。模型展示名称不能代替 ID。
5. 点击「保存模型设置」。只更新 `config/models.yaml` 的 OpenRouter 模型及输入/输出估价，不更改 DeepSeek、端点、密钥或会话授权。上次配置备份到 `config/secrets/openrouter_models.previous.json`，不提交 Git。
6. 点击「检查密钥与模型（无生成）」：认证密钥并核对模型目录，不发送聊天消息。此检查通过不保证当前供应商一定可生成。
7. 如需验证实际生成，点击「发送一次最小测试消息」，确认后仅发送固定 JSON 连通性消息，最多 256 输出 token，不发送项目数据。付费模型可能产生少量费用。测试沿用平台的禁止数据收集、禁止自动切换供应商设置；没有可用端点时会明确失败。

## 结果含义

- 密钥认证通过、模型不可用：通常需要换模型 ID，不要反复换密钥。
- 401：认证失败，需要检查密钥。
- 402：额度不足。
- 403：账户、模型权限或供应商限制。
- 404：模型下架/更名，或当前隐私设置下没有可用端点。
- 429：请求频率或免费配额限制。
- 有响应但 JSON 无效：模型尚不满足本次调用格式，不等于认证失败。

模型设置不会自动选择替代模型；本次未更改旧模型 ID。模型保存后，人工审阅流程读取新配置，原有的人工确认和会话启用条件继续有效。

## 本轮验证

- Python 全量回归 261/261 通过；包括目录筛选、模型保存与备份、无授权拒绝联网、旧模型诊断、HTTP 200 内嵌错误，以及本地设置入口权限检查。
- 前端单元测试 30/30 通过；类型检查、Lint 和生产构建通过。
- 五个修改/新增 PowerShell 脚本解析无错误，均保留 UTF-8 BOM。
- Windows 设置窗口实际事件验证通过：未勾选联网时刷新和检查均被阻止；允许联网刷新后获得 11 个当时零价的兼容模型。
- Chromium 实际点击 Dashboard 设置按钮，控制接口返回 202，原生窗口启动；桌面 1440×1000 和移动端 390×844 截图检查通过，浏览器页面错误为 0。
- 已验证保存密钥的认证及旧模型诊断；没有执行替代模型的实际生成测试，也没有上传本轮改动到 GitHub。

已修复 Python 启动 Windows PowerShell 时继承 PowerShell 7 模块路径导致窗口退出的问题。仅对子进程设置 Windows PowerShell 模块路径，不修改系统环境变量；窗口提前异常退出时返回启动失败。依据：[Microsoft PSModulePath 文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath?view=powershell-7.6)。

官方参考：[模型目录](https://openrouter.ai/docs/api/api-reference/models/get-models)、[模型与别名](https://openrouter.ai/docs/guides/overview/models)。

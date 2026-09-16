# SRC-Auto 当前发布清单

**发布标识：** `v0.11.1`

**发布日期：** 2026-09-16（Asia/Shanghai）
**适用分支：** `main`

**分发方式：** GitHub Actions 在正式发布门禁通过后生成 `SRC-Auto-Windows-x64.zip`、版本化 ZIP、`SHA256SUMS.txt` 和机器可读发布清单。固定最新版下载地址为：

`https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases/latest/download/SRC-Auto-Windows-x64.zip`

## 本发布包含什么

这是 SRC-Auto 的当前可运行发布基线：一个只监听本机回环地址的安全测试控制台和五靶场可视化控制层。当前 Dashboard 的前端固定为 `127.0.0.1:4173`，控制 API 固定为 `127.0.0.1:4174`；API 只接受预定义的五个靶场和固定的生命周期、检测动作，不接受任意 URL、容器名、命令或文件路径。Dashboard 启动时会先锁定本次会话的云端 AI 授权；拒绝时服务端硬拒绝远程连接测试，页面上的单次联网勾选也不能越过这道门。重复启动时只有授权状态一致的 API 才会被复用；旧状态或不一致状态只会在确认无运行任务且进程身份属于本项目后安全重启。

本发布的标准入口是：

```powershell
Set-Location 'D:\\网络安全文件夹\\SRC-Auto'
.\\tools\\start_dashboard.ps1
```

或使用统一入口：

```powershell
.\\START_SYSTEM.ps1 -Dashboard
```

无参数的 `START_SYSTEM.ps1` 仍打开兼容的 WinForms 菜单；它不会自动访问真实目标。真实目标录入、授权确认、人工复现和补天提交始终由操作者负责，当前发布不会自动执行这些动作。

## 已验证范围

| 验证项 | 当前证据 |
|---|---|
| Python 回归 | `317` 项执行：`316` 通过，`1` 项按条件跳过，`0` 失败 |
| 回环 API / 控制服务 | 已纳入 Python 全量回归并通过 |
| Dashboard 前端单元测试 | `41/41` 通过 |
| Chromium 浏览器验收 | `8/8` 通过 |
| TypeScript、Lint、生产构建 | 均通过 |
| Windows 分发包隔离启动 | 便携 Python、静态页面、构建资源、API 与同源代理均通过 |
| 五靶场控制闭环 | 全部健康；Juice Shop 已完成真实“停止 → 启动”点击回归 |
| 外部目标、远程 AI、自动提交 | `0 / 0 / 0` |

完整说明见 [TEST_REPORT.md](TEST_REPORT.md)、[USER_MANUAL.md](USER_MANUAL.md) 和 [docs/THREE_PHASE_USER_MANUAL.md](docs/THREE_PHASE_USER_MANUAL.md)。

## 有意不包含的内容

本发布不把以下本机运行期文件提交到 Git：工具二进制、ZAP 会话、扫描缓存、SQLite 数据库、UUID 证据、报告原件、Python 虚拟环境与字节码、Hypothesis 缓存、工具运行数据、DPAPI 密文、API 密钥、会话资料或任何原始响应内容。`vendor/bin` 下五个小型 `.cmd` 包装脚本例外，它们是工具配置需要的项目源码，不包含工具本体或运行数据。其余文件可能仍保留在操作者的本机目录中以便排障，但不是发布内容，也不应作为当前版本结论的来源。

仓库仅保留两张不含敏感内容的静态验收截图：

- `validation/dashboard/live-lab-controls.png`
- `validation/dashboard/live-click-regression.png`

## 文档读取规则

2026-09-16 的本清单是 `v0.11.1` 分发版本的当前验收摘要。`TEST_REPORT.md` 及日期更早、标题标注为“历史”或“归档”的内容只用于追溯，不覆盖本清单记录的版本号、测试数量或分发结论。

## 回退方式

本发布的 Git 标签为 `v0.11.1`。上一份可用回退基线保留为 `v0.11.0`；如后续升级出现问题，可从相应标签创建恢复分支，无需删除 GitHub 历史记录。

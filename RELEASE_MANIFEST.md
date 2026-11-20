# SRC-Auto 当前发布清单

**发布标识：** `v0.17.0`

**本次复核日期：** 2026-11-20（Asia/Shanghai）

**状态：本清单记录 v0.17.0 的源码范围与验收结果。** GitHub CI、不可变标签和公开发行包的最终状态，以 [GitHub Releases](https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases/latest) 与对应 [Actions](https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/actions) 为准；本地验收不代表远端门禁已通过。v0.16.0 及更早发行保留为回退基线，不覆盖历史标签。

> **v0.17.0 本轮范围与本地验收：** 在 v0.16.0 基础上新增 L4「真实目标出站」链路的前三个增量（区别于既有“L4-A/B/C 业务验证”命名）：①`confirm-scope`（候选 scope 经显式 `--confirm`、operator、authorization note 人工确认为 confirmed legacy scope；缺显式确认、缺授权字段、空 hosts/ports、非法 candidate、已 confirmed、禁止覆盖均 fail-closed；confirm 不执行、不联网，scope_hash 直接衔接 `new`/`run-live`）；②回环目标容器地址映射（Scope 与 argv 校验仍针对原始 `127.0.0.1/localhost`，仅校验后把回环 `-u` 目标改写为 `host.docker.internal` 并加 `--add-host host.docker.internal:host-gateway`，非回环与带凭证 URL 不改写）；③nuclei 输出逆映射（runner 返回前把 gateway host 按 reviewed loopback targets 还原为逻辑回环 host，URL 与 host 字段均还原，completed/error/timeout 均适用），保证 ingest 的 ScopeGuard 判 in-scope。本地回环靶场 Juice Shop（127.0.0.1:3000）实机端到端：confirm-scope 生成 juice-shop-l4 confirmed scope，nuclei 经 `host.docker.internal:3000` 真实访问发现 `Public Swagger API - Detect`（info，CWE-200）；真实库 run_id=`e965b510ee604a9aa5dcc2c383b6ffe6`、scope_hash=`3c91ab1646e424734db8db4743da470762d3fa61c3013e408cd66d245c0ff052`，completed_tools、inserted=1、skipped_out_of_scope=0，一条 swagger-api candidate 入库。全模板扫描两次均 600 秒超时（默认 2051 / exposure+http 1509 模板，`-rl 2` 限速且每容器重装模板库），返回 `partial_tools`，fail-closed 保护按预期工作，completed→真实入库已用真实输出验证。Python 3.12 / 3.8 各 648 项通过、各跳过 1 项符号链接；Python 3.12 总覆盖率 75%（门槛 68%）。Dashboard lint（oxlint 0 错误）、Vitest 76/76、Vite 生产构建通过。出站执行链 0 次模型调用（刻意设计），未启用 DeepSeek/远程 AI；真实外部目标未授权、未触碰，临时开启的 `allow_real_targets` 验证后已恢复 `false`，环境已恢复。GitHub CI、不可变标签和公开包仍需实际工作流验收；历史 v0.16.0 / v0.15.0 验收记录见下文。

固定正式下载：[SRC-Auto Windows x64](https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases/latest/download/SRC-Auto-Windows-x64.zip)。正式发行提供固定名 ZIP、版本化 ZIP、SHA256SUMS.txt 与 release-manifest.json。源码、不可变标签及包内提交号必须一致，不覆盖历史标签。

## 本版本包含什么

- Agent 工具菜单与真实处理函数由同一目录生成，不再从全局动作集合减项；各任务只能选择自己的批准对象。被动扫描在路由采集完成后才可选，必要证据不足不能 finish。
- 格式错误和普通动作选择错误合计最多修正一次；未知动作、外来对象/证据、禁止字段、重复动作、STOP 和未知在途状态仍失败关闭，不放宽范围，不自动重试工具或云端请求。
- Agent、本机应用与业务任务详情可展开菜单、校验、拒绝原因和实际执行器；旧任务没有新字段时明确显示历史记录，不伪造菜单或继续运行。
- 保留五固定回环靶场、授权草稿、离线范围审阅、真实任务/报告、中文内嵌 API 设置、本机应用审查及自定义目标库。
- 保留受控 Agent 的有限动作、真实观察反馈、覆盖校验、逐请求范围/时间/资源/STOP 检查、人工启用/单任务云端同意、共享预算与取消。
- L4-A：SQLite 业务草稿、隔离环境说明、四角色预期权限、目标/入口/角色/有效期绑定的 DPAPI 测试会话。保存和离线核对不授予执行权限。
- L4-B：两道独立人工确认后，对精确回环实例的批准 GET 路由执行账号 A、账号 B、管理员与匿名四角色 JSON 对象对比。完整同一字符串 id / 内容摘要证据才形成候选，证据不足转人工。
- L4-C：手动 START_L4_LAB.ps1 启动内存合成靶场，固定 SQL 布尔差异与惰性 HTML 反射正负对照。无任意载荷、业务写操作、脚本执行或生产复制。
- 真实标准/DeepSeek 任务、四角色证据、取消、关联报告、直接阅读和完整导出。模型不能未经工具执行就标记完成。
- L3：固定 ZAP 在断网容器分析脱敏 HAR；独立 Bandit 有限 Python / Semgrep 本地 JS/TS 规则源码审查，不运行项目、不上传代码。源码审查可单独启用 DeepSeek 匿名规则摘要辅助，最多 4 次；默认关闭，不发送源码、路径或文件名，不能据此确认漏洞。见 [源码审查说明](docs/SOURCE_AUDIT_USAGE_ZH.md)。
- 候选提交队列状态机（仅人工记录，绝不自动提交补天）、增强补天报告（漏洞类型/CWE/CVSS/参数/置信度/多来源/复现步骤/修复建议与概览统计）与 Dashboard 候选“分类与来源”展示（队列状态、漏洞类型、多扫描器来源、指纹），旧数据库只读兼容。
- L4 真实目标出站链前三增量：`confirm-scope` 人工确认候选 scope（不执行、不联网）、回环目标容器地址映射（`host.docker.internal` + host-gateway）与 nuclei 输出逆映射（还原逻辑回环 host）；confirm≠execute，仍由 `allow_real_targets`、confirmed scope、计划确认与 `--execute-live` 四道门控制，真实外部目标未授权、未触碰。
- 发行脚本在输出变更前拒绝修改、暂存或未跟踪的非忽略源文件，避免遗漏新模块或用旧提交号描述新内容。两项实际临时 Git 仓库回归先失败后通过。
- 默认打包重新构建前端；构建失败即停止，不能分发残留旧页面。`VERSION`、Python 包与项目元数据均为 0.17.0。

DeepSeek 实际 API ID 为 `deepseek-flash`，本轮调用成功；展示名称不是接口 ID。Qwen3.5-9B 可人工选择，不自动切换云端。CPU 70%、整机已用 RAM 30 GiB，未知资源不放行。所有候选未确认，不自动提交补天。

## 启动与分发

解压后双击 START_DASHBOARD.bat；预构建页面和便携 Python 无需 Git、Node 或全局 Python。默认回环页面 127.0.0.1:4173、API 127.0.0.1:4174。启动拒绝云端后，连接测试和 Agent 被后端硬拒绝。

L4 练习先手动运行 START_L4_LAB.ps1，保持窗口打开，再载入本次实例草稿。用法见 [完整手册](USER_MANUAL.md) 和 [L4 指南](docs/L4_PREPARATION_PROGRESS.md)。

Docker、靶场/扫描器镜像及 Ollama 权重不随 ZIP 分发。五固定靶场/L3 扫描器需另准备 Docker；专用 L4 合成靶场和原生本机检查不依赖 Docker。缺依赖明确阻断，不伪造成功。分发用户重新输入自己的 API 密钥。

本地打包必须在干净提交上运行，并重新构建 Dashboard。正式发行须另取得当次授权，重新通过实际 CI、覆盖率、凭据与 ZIP/提交身份/干净运行门禁。

## v0.16.0 已发布验收记录

以下为 v0.16.0 发布批次成绩（提交 `52a927a`），不把后续 L4 增量算作该轮验收。

- 范围：L3 候选提交与展示链路——Finding 提交队列状态机（candidate→triaged→confirmed→submission_ready→submitted 及 rejected 分支，非法转换 fail-closed 不改库，`submitted` 必须人工 operator）与 `finding-transition` CLI、补天报告增强（类型/CWE/CVSS/参数/置信度/多来源/复现步骤/修复建议与概览统计）、Dashboard 候选“分类与来源”展示，旧库只读兼容。
- Python 3.12 / 3.8 各 635 项通过、各跳过 1 项符号链接；3.12 总覆盖率 75%（门槛 68%）。Dashboard lint、Vitest 76/76、生产构建、Chromium E2E 8/8 通过。
- 历史下载与校验以 [GitHub Releases v0.16.0](https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases/tag/v0.16.0) 为准。

## v0.15.0 已发布验收记录

以下为 2026-11-19 的 v0.15.0 发布批次成绩（提交 `0fce2d3`），不把后续 L3 增量算作该轮验收。

- 范围：L0-L2 升级、Python 包版本元数据修正（0.14.2→0.15.0）、Finding/资产/证据/事件边界统一脱敏 URL 查询值、pinned Nuclei Docker runner 接入 live-plan CLI 并绑定审核 URL/模板标签/请求速率。
- Python 3.12 / 3.8 各 622 项通过、各跳过 1 项符号链接；3.12 总覆盖率 75%。Dashboard Vitest 74/74、lint、生产构建、Chromium E2E 8/8 通过。
- 由 GitHub Actions 工作流发布（run 44509945184，conclusion=success），公开 4 资产（版本化 ZIP、通用 ZIP、SHA256SUMS.txt、release-manifest.json），immutable=false。
- 历史下载与校验以 [GitHub Releases v0.15.0](https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases/tag/v0.15.0) 为准。

## v0.14.2 已发布验收记录

以下为 2026-10-14 的 v0.14.2 发布批次成绩，不把后续文档勘误或旧版实机扫描算作新一轮验收。

- Python 3.12 / 3.8 各 586 项：585 通过、1 个 Windows 符号链接权限条件跳过；3.12 总覆盖率 74%。专项故障回归 11/11。
- Dashboard 74/74，覆盖语句/分支/函数/行 76.56/70.46/71.06/81.93%；Lint、类型、生产构建、Chromium 8/8 与 23 个项目 PowerShell 解析通过，未降低门槛。
- 实际 Docker 元数据：五靶场均 READY；一次批量查询约 0.203 秒，旧串行查询约 0.859 秒。仅为本机本轮状态查询测量，不是重新执行五靶场全流程。
- 真实 DeepSeek / 本机合成应用 10/10：标准 0.34 秒，Agent 4.83 秒 / 4 次调用 / 2,871 Token，约 0.006744 元估算；禁用云端时调用为零。不能解释为 Agent 比标准检测更快或服务商实际账单。
- 本地构建包和 GitHub 匿名下载包各通过 7/7 独立运行检查；公开包实际执行 16 次回环请求、形成 3 个待复核候选并生成报告，关闭云端时硬门有效。
- 公开包十页可导航、五靶场入口可见、完整报告可读且导出与后台一致、空密钥设置可用、窄屏无溢出；无页面异常或外部请求。
- v0.14.2 标签、包内发布清单和该版本源码提交均为 `acf45744002a8364ba0eba92e0812736fb9c196d`。两份公开 ZIP 的 SHA-256 一致，163 个打包源码文件匹配该提交，UTF-8 与敏感文件审计通过；不携带操作者密钥、会话或私有运行数据。

## v0.14.0 发布准备验收（2026-10-09，历史记录）

以下数字和发布准备状态只描述该历史批次，不是 v0.14.2 的当前成绩。保留原记录用于追溯，后续实机验证见对应版本说明。

- Python 3.12 / 3.8 各 552 项：551 通过、1 个 Windows 符号链接权限条件跳过；Python 行与分支总覆盖 73.76%。
- 前端 69/69，覆盖语句/分支/函数/行 76.46/70.28/71.13/81.69%；Lint、类型、生产构建、Chromium 8/8 与 23 个 PowerShell 解析通过。
- 实际 L4 标准/DeepSeek 对照 13/13：各 16 次回环请求、3 个候选，证据一致；标准 2.26 秒，Agent 6.17 秒 / 4 次调用 / 3,579 Token。Agent 完成覆盖后转交人工复核，不等于漏洞已确认。
- 固定断网 Bandit/Semgrep：已知风险合成样本 2 条，修正负例 0 条，批准文件均实际分析；新云端源码摘要 10/10，2 次实际 DeepSeek 调用 / 720 Token / 7.50 秒，不发送文件定位或代码。
- 打包旧页面、构建失败仍打包、版本不一致的回归先失败后通过。业务验收同时要求完整有效证据，不只检查 completed 字符串；资源阻断和覆盖不全仍失败。
- ZIP 身份、校验和、私密文件排除、独立解压及真实页面运行结果须在生成包后检查，具体本机工件保留于上述最新准备目录；未执行的 GitHub CI 和正式发布不计作通过。

## 此前 L4 阶段验证（历史证据，保留追溯）

- Python 3.12 / 3.8 各 536 项：535 通过、1 个 Windows 符号链接权限条件跳过；行与分支总覆盖 73.52%。
- 前端 66/66，覆盖语句/分支/函数/行 75.93/70.47/70.69/81.61%；Lint、类型、生产构建、Chromium 8/8 与 23 个 PowerShell 解析通过。
- 五固定 Docker 靶场 DeepSeek 5/5：83 次回环 HTTP、5 次模型调用、4,821 Token、12 个候选。socket 故障已受限恢复，原数据保留，不声称永久根治。
- L4 对照 13/13：两模式各 16 次 HTTP、3 个候选；标准 2.25 秒，Agent 5.78 秒 / 4 次调用 / 3,561 Token，证据逐项一致。
- 本机应用 + 断网 ZAP 对照 13/13：各 3 次目标请求；标准 30.64 秒，Agent 34.26 秒 / 5 次调用 / 4,991 Token。扫描器 network=none、目标请求为零。
- 源码已知正例 2 条、修正负例 0 条，实际断网 Bandit/Semgrep，无 AI 调用。
- 真实页面 DeepSeek：16 次 HTTP、4 次调用、3,559 Token、5.72 秒、3 个候选。桌面/390px 无乱码和横向溢出；导出 6,255 字符与后端原文统一换行后逐字一致；刷新不保留审批或执行授权。
- 收尾修复客户端断连造成的重复 502/异常堆栈，以及 Python 子进程中文日志编码。30 次实机中断请求后网页/API 健康，错误日志无堆栈；真实后端故障仍返回 502，未知错误不隐藏。

这些成绩只证明有限动作真实闭环，不证明任意网站覆盖、更高漏洞命中率、更快或赏金收益。最终分发门禁本机记录不随仓库上传；未执行的 CI 和正式发行不计作通过。

## 隐私、限制与回退

Git 和包排除密钥/DPAPI 密文、Cookie/账号会话、数据库、生成目标、私有源码、日志/报告、运行工件、模型和下载工具。仅保留五个 vendor/bin/*.cmd 包装源码，工具本体不上传。凭据签名检查不等于未知格式秘密绝对不存在。

用户负责独立生产配置/数据/存储/账号隔离。未包含业务写操作、竞态、盲注、存储型/执行型 XSS、通用源码污点/CVE 分析及外部目标 Agent。可信本地 HTTPS 和 IPv6 传输仍未完整端到端验收。最终确认和补天提交由人工负责。

v0.14.1 及更早不可变标签/包保留回退。新包先解压到独立目录，不覆盖运行中的程序，不静默迁移密钥和状态。只有实际发布成功后才更新正式下载；历史文档是快照，不覆盖此发布清单。

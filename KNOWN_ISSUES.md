# 已知问题与诚实限制

## 2026-08-28 可视化控制升级后的实际状态

- Dashboard 已接入固定回环控制 API：前端 `127.0.0.1:4173`，API `127.0.0.1:4174`；启动器会复用健康的 API，或在项目目录以隐藏进程启动 `src_auto.dashboard_server`。API 不接受任意 URL、容器名、命令或路径，所有变更请求需要短期进程令牌。
- 本地靶场页面现有每个靶场的启动/停止/重置/任务详情按钮及启动全部/停止全部按钮。按钮只改变 Docker 容器生命周期，不等同于已执行漏洞扫描；扫描与最终报告仍需人工确认。
- 本次本机冒烟开始时 Docker Engine 未运行，页面按设计显示为受阻；已在本机启动 Docker Desktop 并通过 Dashboard 的同一回环 API 完成五靶场启动。当前为 `5/5 healthy`，且 Chromium 已完成 Juice Shop 的“停止 → 启动”真实点击回归。若 Docker 将来再次不可用，页面会重新显示受阻；应启动 Docker Desktop、刷新控制台并重新验收，不能沿用旧状态或旧候选数字。
- 回环 API 的状态、事件和令牌保存在进程内；关闭 API/启动器后，运行中的操作不会被恢复为历史“运行中”，重新打开会通过 Docker inspect 读取当前容器状态。未完成的执行历史需以项目内验证工件为准。
- 若 4174 被旧的 Vite/其他程序占用，启动器会因健康检查不匹配而报告控制 API 未就绪；请先确认占用者是项目进程，再关闭旧 Dashboard 后重试，不要强行改成公网监听。

## 2026-08-26 三期升级当前状态

- 当前代码/控制台/文档按三期计划接入，完整 Python 测试为 `238/238`；12 个项目 PowerShell 脚本解析无错误，关键中文脚本均保留 UTF-8 BOM。
- 本地实验面已经从四个扩展为五个：新增确定性业务 API `127.0.0.1:8084`；原 VAmPI 继续使用 `127.0.0.1:8083`。五个入口都只允许回环地址。
- 本轮早期曾出现 Docker Desktop Linux engine 命名管道不可用，导致短暂的 `0/5 READY`、`NOT_FOUND` 和业务 API `BLOCKED_DEPENDENCY`；随后已启动并恢复 Docker。当前五个靶场均为 `READY`，本轮独立回归 `30/30` 通过，本地验收为 `AUTHORIZED_LOCAL_VALIDATION_READY`。精确错误、恢复命令和历史阻断证据见 `validation/business-api/DOCKER_RUNTIME_BLOCKER.md`；若 Docker 再次不可用，必须重新标记为阻断，不能沿用本轮成绩。
- 业务 API 对象矩阵、蓝队日志分析和桌面控制台的离线/进程内验证已完成；矩阵输出为待人工复核候选，日志分析不保留原始查询串/IP，自动处置数量为 `0`。远程 AI、真实外部目标和自动提交本轮均为 `0`。
- Figma V2 视觉稿的 manifest/README 保存在 `design/frontend-mockups/2026-08-26-figma-v2/`；生产界面使用本地 WinForms 实现，设计插件导出额度不足不会被伪报为生产代码。

## 2026-08-21 当前状态校正

WSL2 2.7.12、Ubuntu 和 Docker Desktop 4.87.0 已按操作者授权安装；Ubuntu 位于
`D:\网络安全文件夹\WSL\Ubuntu`，Docker 的 WSL 数据位于
`D:\网络安全文件夹\DockerData\wsl`。Docker Desktop 程序和 WSL 系统运行时仍可能在
用户/系统目录保留少量 C 盘文件，这是已批准的系统组件例外。Juice Shop 当前只监听
`127.0.0.1:3000`，基线已执行，ZAP 也已完成本地 quick scan。下面第 12、14 项中
涉及“未安装 Docker”的文字是安装前历史快照，以本节和验证报告第 0 节为准。

1. WSL2/Ubuntu 已安装并可用；BBOT 3.0.1 仍声明 Python >=3.10 且依赖 POSIX 环境，
   reconFTW 仍需要 Linux shell。这些是工具级环境限制，不是成功执行声明。
2. Nuclei v3.11.1 Windows 二进制和发布哈希已在 D 盘，但端点安全软件以 WinError 225
   阻止执行；没有绕过，也没有运行 Nuclei 扫描。
3. ZAP 2.17.0 已从 D 盘 Core 包验证，并在本地 Juice Shop 上完成显式
   `--confirm-local` quick scan。本次输出 5 个 `POSSIBLE` 候选（前一次为 4 个），尚未
   人工裁决；真实外部目标仍由显式适配器门控，不能把本地候选当成补天漏洞。
4. Windows 上第三方工具的版本检查可能在 `C:\Users\lenovo\AppData` 创建自己的用户配置。
   项目不会在那里保存凭据，但工具不一定完全遵守 D 盘项目边界。若要求清理整台主机，必须先
   审查后仅删除工具实际创建的配置目录。
5. 有 PyYAML 时使用 PyYAML 加载 YAML；否则只接受本项目兼容 JSON 的 `.yaml` 文件。包含锚点或
   注释的任意 YAML，需要先在 D 盘环境安装 PyYAML。
6. 本地 Ollama 已接入，但 CPU 推理可能较慢。`qwen-agent-stable:30b` 在本机验证返回了合法
   JSON；当前模板下 `codex-balanced:20b` 返回空响应，因此会回退，除非人工重新配置。
7. 受控 `run-live` 命令只转发人工编写的计划，目前不会把工具输出自动归一化为 Finding。真实
   执行默认关闭，未包含登录/CAPTCHA 自动化，也没有自动提交补天报告。
8. 不保证收入、赏金金额、平台接受或月度利润。账务表和报告字段只是为后续人工测量准备。
9. DeepSeek V4 Flash 已用注入式假响应完成契约验证，但在操作者撤销聊天中粘贴的旧密钥、创建
   新密钥并在本机设置 `DEEPSEEK_API_KEY` 前，不声称发起实时请求。远程路径仍是人工启用，不能
   发现目标或提交报告。
10. OpenAI Responses 适配器已实现但默认禁用。ChatGPT Plus 不包含 Platform API 密钥；要做
    实时 OpenAI 验证，需要单独的 Platform 账户/密钥，并由人工重新审查数据处理和计费。
11. 远程 AI 按设计没有金额或调用次数预算上限；保留单请求输入/输出 Token 限制、显式预览/摘要
    确认、不自动重试和事后估算成本记录。
12. 本地 Juice Shop profile 已可运行，当前基线为 `COMPLETED_DISCOVERY_ONLY`：保留 31 个
    回环 URL，排除 15 个外部 URL，控制层 preflight 计数为 1，漏洞检测指标仍为 `null`。
    Ground Truth 回归和 TP/FP/FN 需要人工裁决后另行执行，不能用 ZAP 候选直接计分。
13. 第一次 Juice Shop 流程目前只做受限 preflight、`httpx`/`katana` 表面发现和显式 ZAP quick
    scan；漏洞扫描输出的完整归一化及挑战映射仍需服务可达和人工复核。Ground Truth 元数据
    不会反向驱动扫描器输入。
14. 官方 Docker Desktop 4.87.0 安装器仍保留在 `vendor\docker-installer`，SHA-256 已验证。
    按授权完成安装后，程序使用官方 per-user 默认位置，Docker 镜像/容器数据迁移到
    `D:\网络安全文件夹\DockerData`；C 盘只保留系统程序/WSL 运行时和一个可恢复备份记录，
    项目日志或扫描工件不会写入 C 盘。
15. 中文摘要依赖当前 PowerShell/终端的 UTF-8 显示能力；启动器已使用 UTF-8 BOM，兼容
   Windows PowerShell 5.1 的脚本解析。即使终端乱码，`--json` 输出仍使用 UTF-8 且英文机器
   字段保持可解析。脚本需要稳定输入时，请显式使用 `--json`；交互人员请使用 `--human`，
   必要时先设置 `$env:PYTHONIOENCODING='utf-8'`。

## 2026-08-24 当前状态

四个固定回环靶场（Juice Shop、DVWA、WebGoat、VAmPI）已在 Docker Desktop 就绪，最新验收为 `AUTHORIZED_LOCAL_VALIDATION_READY`；完整测试 `214/214`、本地回归 `14/14`，远程 AI、外部目标接触和自动提交均为 0。详细结果以 `validation/autotest/LOCAL_LAB_SCORE.json` 和 `docs/THREE_PHASE_UPGRADE_REPORT.md` 为准。

## 2026-08-22 本轮新增限制和验收解释

### 2026-08-22 历史三靶场结果（不覆盖当前工件）

已建立并验证 Juice Shop `127.0.0.1:3000`、DVWA `127.0.0.1:8081` 与 WebGoat
`127.0.0.1:8082` 三个固定 digest 的回环应用容器，各 3 轮。DVWA 候选数为 `9,8,9`，最新
控制项基准 Precision/Recall/F1 为 `0.875000/1.000000/0.933333`；Juice Shop 为 `5,4,5`
和 `0.200000/1.000000/0.333333`；WebGoat 为 `0,0,0` 和 `1.000000/1.000000/1.000000`。
这些不是赏金漏洞指标，三个靶场 `bounty_ready_count=0`。
官方 Juice Shop 116 条题目元数据（67 条 scanner-detectable）尚未执行完整挑战回归，官方
Precision/Recall 保持 `null`/`NOT_TESTED`。P0 的 scope escape、外部目标接触、远程 AI、
密钥泄露、崩溃和自动提交均为 0。

本机 Docker Desktop 的 `internal: true` 网络会让宿主无法访问已发布端口；Compose 因此使用
普通 bridge 网络，仍由宿主 RuntimePolicy、ScopeGuard、发现器和 ZAP 硬限制为三个
`127.0.0.1` 端口。该限制不表示允许外部扫描。

16. 启动器的中文重复来自 Windows PowerShell `Invoke-WebRequest` 进度流重绘，而不是 Scope 或
    字符串逻辑；已通过 `$ProgressPreference = 'SilentlyContinue'` 关闭该重绘，并保留 UTF-8 BOM。
17. `target-review` 可以离线审阅非本地 URL，但“选择已审阅”不是授权，也不会联网；真实执行仍
    需要人工核对平台规则、策略开关、Scope、人工计划和 `--execute-live`。
18. 旧的 `tools/run_autonomous_validation.py` 只运行回环 Juice Shop，仅为历史兼容入口。当前
    三靶场 canonical 入口是 `tools/run_local_lab_validation.py`；重置后若任一服务无法在等待窗口内
    健康，本轮会标记 `BLOCKED_DEPENDENCY`，旧 ZAP 工件不会被复用为新轮次 Finding。
19. 本机验收已完成本地控制项逐项裁决，但这不等于完整官方挑战 Ground Truth；三轮候选数量的
波动（DVWA `9,8,9`、Juice Shop `5,4,5`、WebGoat `0,0,0`）保留在报告中，数量稳定性不能解读为赏金检测准确率。
20. 本地 Ollama 模型当前可用状态只说明端点存在；AI Ablation 本轮不自动调用模型，报告为
    `NOT_RUN`，远程 AI 调用和成本保持 0。

## 2026-08-22 三靶场扩展后的当前边界

21. 已增加固定 digest 的 OWASP WebGoat `v2025.3`，仅发布 `127.0.0.1:8082`；其镜像健康检查
    使用 `wget`，因为镜像本身没有 `curl`。WebGoat 控制项得分只证明健康面可用，不代表课程中
    的每个漏洞都已发现。
22. DVWA 现在使用同一 Compose 项目的固定 MariaDB 镜像和命名卷初始化数据库；数据库未发布
    宿主端口。删除 Compose 卷会清除靶场数据，但不会影响项目代码；默认启动/停止不删除卷。
23. `tools/run_local_regression.py` 是独立的非破坏性回归层，当前 6 个用例、3 轮共 18/18
    通过。它不会执行命令注入、脚本、文件上传、密码修改、盲注、拒绝服务，也不会把回归通过
    标成 `submission_ready`。
24. 回归层为 DVWA 使用靶场默认本地管理员流程、为 WebGoat 每轮生成随机合成账号；账号、密码、
    Cookie、Token 和响应正文不写入 `validation/autotest/local_regression`。
25. ZAP 控制项与回归通过率均不能代表补天收益、漏洞接受率或完整 Juice Shop Ground Truth。
    真实目标仍需新的 Scope、人工确认、最小复现和平台规则允许；任何外部 URL 在当前测试中均未
    访问。

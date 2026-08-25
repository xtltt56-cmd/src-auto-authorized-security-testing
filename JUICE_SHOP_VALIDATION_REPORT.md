# OWASP Juice Shop 本地验证报告

## 2026-08-22 当前验收附录（以本节和 `validation/autotest/` 为准）

已在操作者本机重新执行仅回环验收：`python tools/run_autonomous_validation.py --local-only --repeat-rounds 2`。
当前容器 `juice-shop` 仅绑定 `127.0.0.1:3000`，HTTP 200；基线为
`COMPLETED_DISCOVERY_ONLY`，保留 31 个回环 URL、排除 15 个外部 URL。三轮 ZAP quick scan
均产生 5 个 `POSSIBLE` 候选（没有人工裁决，不能称为已确认漏洞）。P0 记录为
Scope Escape=0、Remote AI Calls=0、Secret Leakage=0、Crash=0；最终工程判定为
`LOCAL_LAB_READY`，不是 `AUTHORIZED_PILOT_READY`，也不代表已经找到补天可获赏漏洞。

本轮新增/修复：

- `START_SYSTEM.ps1` 保留 UTF-8 BOM，并关闭 PowerShell 进度流重绘，解决中文重复和 `0......` 覆盖；
- `python -m src_auto target-review` 只做人工目标选择/Scope 预览，不联网；真实执行仍需
  `run-live --execute-live` 和现有策略/Scope/人工计划门控；
- 每轮本地工件、发现指标、AI 对照、稳定性和第二靶场状态统一位于
  `validation/autotest/`；未人工裁决的 Precision/Recall/FN/验证成功率保持 `null`/`NOT_TESTED`。

详细当前工件：`validation/autotest/AUTONOMOUS_VALIDATION_REPORT.md`、
`validation/autotest/DISCOVERY_METRICS.json`、`validation/autotest/STABILITY.json`。

初始报告日期：2026-08-21（Asia/Shanghai）；当前事实源见上方 2026-08-22 附录。
项目根目录：`D:\网络安全文件夹\SRC-Auto`
验证目标：仅限操作者启动、绑定在 `127.0.0.1:3000` 的本地 OWASP Juice Shop
验证结论：**控制层和安全门控已实现；WSL2/Docker/本地 Juice Shop 已实际启动并完成
回环基线与 ZAP 快速扫描。本次有 5 个 `POSSIBLE` 候选（前一次为 4 个），仍需人工复核；没有把候选直接
当成漏洞，也没有执行补天自动提交。**

## 0. 授权后当前运行快照（2026-08-21）

本节是本报告的当前事实源；文档后面的“基线执行结果”和“评分”保留安装前的历史快照，
用于解释当时为什么没有指标，不能覆盖本节的最新结果。

| 项目 | 当前结果 |
| --- | --- |
| WSL2/Ubuntu | WSL 2.7.12；Ubuntu 位于 `D:\网络安全文件夹\WSL\Ubuntu` |
| Docker Desktop | 4.87.0；程序按 per-user 方式位于用户目录，Docker 数据位于 `D:\网络安全文件夹\DockerData\wsl` |
| Docker 引擎 | Client/Server 29.7.2，Linux engine 可用 |
| Juice Shop | 容器名 `juice-shop`；仅 `127.0.0.1:3000->3000`；HTTP 200 |
| 安全策略 | 精确 `127.0.0.1`/`localhost:3000`，本地 AI，远程 AI 0 |
| 基线 | `COMPLETED_DISCOVERY_ONLY`；31 个本地 URL，15 个外部 URL 被排除；仅 1 次控制层 preflight 请求 |
| ZAP | 2.17.0 quick scan；本次 5 个 `POSSIBLE`、未裁决候选（前一次为 4 个）；报告与归一化 Finding 均在 D 盘 |
| 提交 | 无自动提交；补天提交必须由人工按平台规则完成 |

当前工件：

- `validation/juice-shop/baseline_results.json`
- `validation/juice-shop/baseline_metrics.json`
- `validation/juice-shop/zap_quick_report.json`
- `validation/juice-shop/zap_findings.json`
- `validation/juice-shop/wsl_install.log`
- `validation/juice-shop/ubuntu_install.log`
- `validation/juice-shop/docker_settings_store_before_move.json`

ZAP 候选的状态固定为 `POSSIBLE`，本次工件包含 5 个候选（扫描时序可能导致数量
变化），并不等于已确认的安全缺陷；应逐项做最小、无破坏性人工验证，记录复现证据、
影响和平台规则后再决定是否手工提交。旧的
`BLOCKED_DEPENDENCY`/`NOT_RUN` 描述仅是授权安装前的历史记录。

### 0.1 中文界面与机器字段

交互式命令默认显示简体中文摘要；脚本捕获、管道或显式 `--json` 会输出机器可读 JSON。
状态码和原因码仍保留英文，适用时增加 `status_zh`、`reason_zh` 说明字段。中文说明不
会把 `POSSIBLE` 渲染成“已确认漏洞”，也不会改变本地 Scope、远程 AI 或自动提交门控。

## 1. 授权边界和数据流

本轮只允许以下两个精确主机名和一个端口：

| 项目 | 值 |
| --- | --- |
| 允许主机 | `127.0.0.1`、`localhost` |
| 允许端口 | `3000` |
| 允许协议 | `http` / `https`，仅限上述主机和端口 |
| AI | `AI_PROVIDER=local`、`LOCAL_LLM_ONLY=true` |
| 远程 AI | `ALLOW_REMOTE_LLM=false`，远程 Provider 在 CLI 运行时被拒绝 |
| 并发上限 | 5 |
| 外部链接 | 不扩展、不跟随越界重定向 |
| 提交 | 只生成草稿，补天提交必须人工完成 |

运行时策略文件是 `config/validation/local_only.json`，Scope 文件是
`config/targets/juice-shop-local/scope_confirmed.yaml`。它们没有根域名扩展，
因此不会把 `*.localhost` 或任何公网域名纳入范围。探测器在发出请求前后都重新检查
运行时白名单和 Scope；响应体只读取有限字节用于标题/长度，不保存整页内容、Cookie、
Token 或密码。

## 2. 历史环境快照（安装前记录，已被当前验收附录覆盖）

- Windows PowerShell；Python 3.8.10；Git 2.55.0；Java 17.0.10。
- Ollama 0.32.14 可用；当前主路由模型为本地 `qwen-agent-stable:30b`，
  `model-status` 返回 `available=true`。
- `httpx` 1.10.0、`katana` 1.7.0、`subfinder` 2.15.0 版本验证通过；ZAP 2.17.0
  版本验证通过。Nuclei、BBOT、reconFTW 没有在本轮实际执行。
- Docker 命令不在 PATH，Docker Engine/Desktop 未提供；`Get-NetTCPConnection -LocalPort 3000`
  显示端口未监听。按操作者后续授权，我下载并校验了官方 Docker Desktop 4.87.0
  安装器，但 D 盘 per-user 安装在 Windows 10 Home/无可用 WSL2 的环境中没有创建安装目录，
  已停止；没有 C 盘 Docker 安装目录，也没有启用系统组件。
- 本轮没有启动 Docker、没有安装 Docker Desktop、没有联系任何补天目标或公网目标。

## 3. Ground Truth

Ground Truth 只提取官方开源仓库的挑战元数据：名称、类别、难度、key 和 tags；没有把
题目描述、提示、payload 或解法写入扫描输入。来源为
[OWASP Juice Shop 官方 challenges.yml](https://github.com/juice-shop/juice-shop/blob/master/data/static/challenges.yml)，
原始文件地址为
[官方 raw 文件](https://raw.githubusercontent.com/juice-shop/juice-shop/master/data/static/challenges.yml)。

| 项目 | 数量 |
| --- | ---: |
| 挑战元数据总数 | 116 |
| 保守判定为 scanner-detectable | 67 |
| 需要业务逻辑/人工工作流 | 38 |
| 需要认证上下文 | 33 |

本分类是**元数据层面的保守先验**，不是扫描结果，也不能替代人工复核。Ground Truth
只在扫描后用于比对，未注入 scanner 的输入或 payload。文件和模式位于：

- `validation/juice-shop/ground_truth.json`
- `validation/juice-shop/schema.json`
- `src_auto/validation.py`

## 4. 历史基线执行结果（安装前记录，已被当前验收附录覆盖）

已执行的命令：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m src_auto juice-shop-status
python -m src_auto juice-shop-baseline
```

结果：

| 项目 | 结果 |
| --- | --- |
| 目标 URL | `http://127.0.0.1:3000/` |
| 本地请求 | 已发出一次 loopback GET；连接被本机积极拒绝 |
| Juice Shop | `BLOCKED_DEPENDENCY`，服务不可达 |
| Docker | `docker_available_on_path=false` |
| 工具执行 | 0 个；服务不可达时不会启动扫描器 |
| Finding | 0；不是“没有漏洞”，而是“没有执行扫描” |
| 本地模型调用 | 0；没有 Finding 可供分诊 |
| 远程 AI 调用 | 0 |
| 远程 AI 成本 | 0 |
| CPU/RAM/请求数 | 未形成扫描测量；不虚构运行数据 |

基线原始工件：

- `validation/juice-shop/baseline_results.json`
- `validation/juice-shop/baseline_metrics.json`

`baseline_metrics.json` 中 TP、FP、FN、precision、recall、F1 和
scanner-detectable recall 均为 `null`。这表示“未运行”，不是把未发现的漏洞计为漏报，
也不是把空结果计为通过。

## 5. 历史改进和回归记录

本轮已经落地并由单元测试覆盖的改进：

1. 增加精确的 `localhost`/`127.0.0.1:3000` 运行时白名单，拒绝子域名、第三方、错误端口、URL 凭据、非 HTTP(S) 和越界重定向。
2. 将 `LOCAL_LLM_ONLY` 作为 ModelRouter 和远程 CLI 的硬门控；即使环境中存在远程 Provider key，正常运行时也不会构造或发送远程请求。
3. 增加只读 Juice Shop preflight/discovery 适配器，默认只运行 `httpx` 和 `katana`，固定 URL、固定低风险参数，并将并发限制在 5 以内。
4. 增加 Finding 归一化、状态集合、Ground Truth 比对和指标计算；业务逻辑挑战不会被错误地塞入 scanner recall 分母。
5. 保留最小证据原则，并把越界目标和输出目录都设为 fail-closed。

同一 Juice Shop 目标的回归必须在成功基线之后执行。本轮因为基线先被依赖阻断，
没有生成任何伪造的检测 delta：

- `validation/juice-shop/regression_results.json`：`NOT_RUN`
- `validation/juice-shop/regression_metrics.json`：所有性能指标为 `null`

## 6. 历史指标和误报/漏报分析（当前指标见 `validation/autotest/`）

### 实测指标

TP、FP、FN、precision、recall、F1、scanner-detectable recall：**不可计算**。

原因只有一个：没有可访问的 Juice Shop 服务，因此没有 scanner 输出，也没有可供人工
裁决的 Finding。把 116 个挑战或 67 个“保守可检测”挑战直接当成 FN 会夸大漏报，
本报告没有这样做。

### 当前可确认的原因

- **漏报原因（已确认的前置原因）**：容器/服务未启动；未进入资产发现、SPA/API 发现、
  被动检查、候选漏洞扫描和证据阶段。
- **误报原因**：没有实际 Finding，因此没有可统计的误报样本。
- **需要下一轮验证的假设**：Juice Shop 是 SPA，单纯首页探测可能漏掉 API 路由；需要在
  本地实例可用后比较 Katana 路由、ZAP 被动结果和安全的 API discovery，再由人工裁决
  哪些结果可映射到 Ground Truth。此项是待验证假设，不是本轮结论。

## 7. 历史平台评分（必须区分“控制层实现度”和“漏洞检测效果”）

漏洞检测效果评分：**不评分**。没有执行目标时，不能用 0 或空 Finding 宣称扫描器
无漏洞或准确率为零。

作为工程交付状态参考，控制层实现度暂评 **59/100（非赏金成功率、非漏洞检测分数）**：

| 维度 | 得分 | 说明 |
| --- | ---: | --- |
| 授权/Scope/越界防护 | 15/15 | 精确 allowlist、重定向检查、人工提交门控已测试 |
| 停止/资源/失败关闭 | 10/10 | STOP、磁盘/资源检查、输出目录门控已测试 |
| 资产和 HTTP 发现 | 0/10 | 目标依赖未启动，未执行 |
| SPA/API 发现 | 0/10 | 目标依赖未启动，未执行 |
| 漏洞检测 | 0/15 | 本轮没有漏洞扫描输出 |
| 归一化/去重 | 10/10 | 控制层与验证模型已有测试 |
| 证据/报告 | 8/10 | 能生成阻断报告和人工草稿，缺少真实响应证据 |
| 本地 AI 路由 | 8/10 | Ollama 可用，远程硬阻断；本轮没有 Finding 分诊 |
| Ground Truth/回归指标 | 0/10 | 必须先有成功基线 |
| 运维和成本控制 | 8/10 | 并发≤5、远程调用/成本为 0；Docker 环境尚未就绪 |
| **合计** | **59/100** | 仅代表当前控制层交付状态 |

## 8. 成本和远程 API

本轮的远程 API 调用次数为 0、远程成本为 0。虽然旧配置保留了人工 DeepSeek
Provider 元数据，但 `config/validation/local_only.json` 和 CLI gate 会在本轮拒绝
远程 AI；没有发送任何 Finding、URL、Cookie、Token 或系统信息到 DeepSeek/OpenAI。
ChatGPT Plus 登录态也不等于 OpenAI Platform API key，OpenAI 适配器不在本轮启用。

聊天中曾出现过 API key 的事实不改变当前运行策略；该 key 不应继续使用，实际联调前应在
供应商控制台撤销并换新。报告、数据库和本项目文件均不包含 key 值。

## 9. 下一步（按优先级）

1. 在得到操作者明确授权后安装/启动 Docker Desktop 或提供等价的本地运行时；然后仅执行：
   `docker run -d --name juice-shop -p 127.0.0.1:3000:3000 bkimminich/juice-shop`，
   再运行 `juice-shop-status`。本步骤需要系统级安装/重启，当前没有擅自执行。
2. 目标可达后运行 `juice-shop-baseline`，保存 `httpx`/`katana` 输出，并在人工审阅后
   增加 ZAP 被动结果或受控的本地候选检测；Nuclei 仍需先处理 Windows 端点安全阻断，
   不得关闭安全软件绕过。
3. 对每个候选 Finding 做人工复现、去重、最小证据和补天规则检查；只有人工确认后，
   才能在补天平台手动提交。任何自动提交、暴力、破坏性写入、DoS、越权扩展都不在设计内。

## 10. 历史控制层验证证据（当前测试报告见 `TEST_REPORT.md`）

- `python -m unittest discover -s tests -v`：**62 tests passed, 0 failed**。
- `python -m compileall -q src_auto lab tests`：通过。
- `git diff --check`：通过（仅有 Windows 换行转换提示）。
- 项目文本密钥卫生检查：未发现 `sk-...` 形式或聊天中已知 key 的字面值。
- `C:\Users\lenovo\Desktop\SRC-Auto 一键启动.lnk` 已核对为调用
  `D:\网络安全文件夹\SRC-Auto\START_SYSTEM.ps1`，不是打开文件夹；该启动器仍只运行
  local-lab，不会自动启动 Docker 或真实目标。
- 已校验的安装器暂存于 `D:\网络安全文件夹\SRC-Auto\vendor\docker-installer\Docker Desktop Installer.exe`，
  SHA-256 为 `9ac03d4e900c0fdee981d4bde083a55fdfb28ffba2cae77726eff2a437254822`；该目录属于项目 D 盘范围并被 Git 忽略。

## 11. SRC-Auto Local Lab Assessment（本阶段固定输出）

```text
==============================
SRC-Auto Local Lab Assessment
==============================

Docker:
BLOCKED

Juice Shop:
UNREACHABLE

Local Model:
qwen-agent-stable:30b (Ollama available)

Remote AI Calls:
0

Remote AI Cost:
¥0

------------------------------
Baseline
------------------------------

TP: null
FP: null
FN: null

Precision: null
Recall: null
F1: null

Scanner Detectable Recall: null
Discovery Coverage: null
Verification Success Rate: null
Authenticated Recall: null

Findings: 0 (scan not started)
Verified Findings: 0 (scan not started)

HTTP Requests: 1 loopback preflight; 0 scan requests
Duration: NOT_AVAILABLE
Local LLM Calls: 0

------------------------------
Regression
------------------------------

TP: null
FP: null
FN: null

Precision: null
Recall: null
F1: null

Scanner Detectable Recall: null
Discovery Coverage: null
Verification Success Rate: null
Authenticated Recall: null

------------------------------
Improvement
------------------------------

Precision: NOT_RUN -> NOT_RUN
Scanner Detectable Recall: NOT_RUN -> NOT_RUN
Verification Success Rate: NOT_RUN -> NOT_RUN
FP: NOT_RUN -> NOT_RUN
FN: NOT_RUN -> NOT_RUN

------------------------------
Architecture Status
------------------------------

Discovery: 3/10
Detection: 0/15
Verification: 0/15
Auth / Session: 0/10
Multi-user: 0/10
Local AI: 8/10
Evidence: 8/10
Ground Truth: 8/10
Safety: 10/10
Automation: 6/10

TOTAL:
43 / 100

This score is a conservative stage-readiness score, not a vulnerability
accuracy score, bounty probability, or SRC readiness claim.

------------------------------
Maturity
------------------------------

L0: PASS
L1: PASS
L2: PARTIAL
L3: NOT_TESTED
L4: NOT_TESTED
L5: PARTIAL
L6: NOT_TESTED
L7: NOT_TESTED
L8: NOT_TESTED
L9: NOT_READY
L10: NOT_READY

------------------------------
Top 5 Remaining Problems
------------------------------

1. Docker is unavailable; the only authorized Juice Shop target cannot start.
2. No real baseline measurements exist for discovery, requests, duration, CPU or RAM.
3. Detection and independent verification have not been exercised on a reachable target.
4. Auth/session and multi-user/stateful workflows remain untested.
5. No second local lab or multi-lab regression evidence exists.

------------------------------
Next Priority
------------------------------

After an operator installs and starts Docker Desktop, run the loopback-only
Juice Shop preflight and freeze the first reachable baseline before changing
scanner code.

------------------------------
SRC Readiness
------------------------------

LOCAL_LAB_READY (control-plane only; not AUTHORIZED_PILOT_READY)
```

The detailed phase files are:

- `validation/juice-shop/BASELINE_ANALYSIS.md`
- `validation/juice-shop/REGRESSION_ANALYSIS.md`
- `validation/juice-shop/FALSE_POSITIVES.md`
- `validation/juice-shop/FALSE_NEGATIVES.md`
- `validation/juice-shop/DISCOVERY_REPORT.md`
- `validation/juice-shop/VERIFICATION_REPORT.md`
- `validation/juice-shop/AUTH_SESSION_REPORT.md`
- `validation/juice-shop/MATURITY_ASSESSMENT.md`

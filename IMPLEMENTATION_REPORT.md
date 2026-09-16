# 实现报告

> **历史归档说明：** 本文主要记录 2026-08-22 及更早的实施快照，不是当前发布的验收依据。当前版本请以 [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md)、[README.md](README.md) 和 [TEST_REPORT.md](TEST_REPORT.md) 顶部内容为准；本文中的旧测试数量、靶场数量和运行快照不覆盖 `v0.10.0`。

## 2026-08-22 三靶场最终验收摘要

已在 `D:\网络安全文件夹\SRC-Auto` 内完成固定镜像的三回环应用靶场建设、生命周期管理、有限静态发现、ZAP quick scan、规则裁决和三轮重复验证。Juice Shop 绑定 `127.0.0.1:3000`，DVWA 绑定 `127.0.0.1:8081`，WebGoat 绑定 `127.0.0.1:8082`；三个应用均为 `healthy`，镜像使用 SHA-256 digest 固定。DVWA 的 MariaDB 只在 Compose 网络内提供依赖，不发布宿主端口。

精确机器结果和人读报告在本机 `validation/autotest/` 中生成；该目录包含运行证据和扫描缓存，因此默认不提交到 GitHub。摘要如下：

| 靶场 | 候选数（3 轮） | 最新轮 Precision | Recall | F1 | 赏金就绪 |
|---|---:|---:|---:|---:|---:|
| DVWA | 9、8、9 | 0.875000 | 1.000000 | 0.933333 | 0 |
| Juice Shop | 5、4、5 | 0.200000 | 1.000000 | 0.333333 | 0 |
| WebGoat | 0、0、0 | 1.000000 | 1.000000 | 1.000000 | 0 |

上述 TP/FP/FN 只针对预先定义的本地安全控制和表面发现基准，不能解释为补天漏洞命中率。Juice Shop 官方 116 条题目元数据（67 条 scanner-detectable）尚未完成完整挑战回归，因此官方 Ground Truth Precision/Recall 为 `null`/`NOT_TESTED`。九轮控制项验证和三轮独立安全回归均为 local-only；回归 18/18 通过，`scope_escape`、`external_targets_contacted`、`remote_ai_calls`、`secret_leakage`、`crash` 和自动提交均为 0。

独立回归工件在本机 `validation/autotest/local_regression/` 中生成，默认不提交到 GitHub。

## 总体结果

D 盘 V1 控制层已经实现并完成本机三靶场验证。系统可以安全启动固定的本地回环靶场，并包含
严格失败关闭的 OWASP Juice Shop/DVWA/WebGoat 验证配置，只允许明确的 loopback 主机和端口。这不是
扫描任意在线网站的授权，也不会自动向补天提交报告。

## 授权后的环境更新（2026-08-21）

操作者已授权安装本地运行组件。WSL2 2.7.12 和 Ubuntu 位于
`D:\网络安全文件夹\WSL\Ubuntu`；Docker Desktop 4.87.0 按官方 Windows per-user 方式安装，
Docker 的 WSL 数据、Juice Shop 镜像和容器存储位于
`D:\网络安全文件夹\DockerData\wsl`。这是已批准的系统组件例外；项目代码、日志、报告和
验证工件仍位于 `D:\网络安全文件夹\SRC-Auto`。

回环容器名称为 `src-auto-juice-shop`、`src-auto-dvwa`、`src-auto-webgoat`，分别绑定
`127.0.0.1:3000->3000/tcp`、`127.0.0.1:8081->80/tcp`、`127.0.0.1:8082->8080/tcp`，均返回 HTTP 200 且健康检查通过。
当前三轮自动化验收的 Juice Shop 候选为 5、4、5，DVWA 候选为 9、8、9，WebGoat 候选为 0、0、0；它们按本地控制项规则
完成裁决，但全部 `submission_ready=false`，不是已确认的真实漏洞或赏金提交。远程 AI 调用为 0。

操作者界面现在以简体中文为主。交互式 CLI 和 `START_SYSTEM.ps1` 显示中文摘要；`--json` 或
管道输出保留稳定的英文机器字段，并增加可选的 `_zh` 中文解释。这只改变展示，不改变 Scope、
网络、AI 或人工提交门控。

## 最终目录

`D:\网络安全文件夹\SRC-Auto`

既有的兄弟路径位于项目外，未被编辑：

- `D:\网络安全文件夹\qa_zut_report`
- `D:\网络安全文件夹\build_zut_report.py`

历史 SHA-256 保护快照曾记录在 `preservation_manifest.sha256`；该本机生成文件不属于当前 Git
发布内容，也不是修改上述兄弟路径的许可。

## 环境快照

- Windows PowerShell；Python 3.8.10；Git 2.55.0；Java 17.0.10 LTS；
- WSL2 2.7.12/Ubuntu 和 Docker Desktop 4.87.0 已安装。当前 PowerShell 可能需要把 Docker
  per-user 资源路径加入 PATH；
- 快照时 D: 约有 167.2 GiB 可用，项目目录约 0.47 GiB；
- 快照时 CPU 约 9.5%，可见内存约 31.7 GiB 总量/20.3 GiB 可用。

## Scope 架构和数据流

`ScopeResolver` 接受平台规则快照并生成候选 Scope，两个授权标志都为 false。
`ScopePolicy` 规范化主机/端口并计算摘要；每次外部适配器请求前都调用 `ScopeGuard`，拒绝
缺少确认、第三方、排除项、错误协议/端口和越界重定向。

外部工具序列：

```text
BBOT -> Subfinder -> httpx -> Katana -> Nuclei -> ZAP 被动 -> reconFTW 深度探测
  -> 归一化 -> SHA-256 指纹/差异 -> AI 分诊 -> 最小证据 -> 人工报告
```

外部序列由库级门控保护，必须同时满足已确认 Scope、人工编写且通过校验的计划、
`allow_real_targets: true` 和显式 `--execute-live`。默认策略和桌面快捷方式只允许回环 fixture。

本地 Juice Shop 验证分支与真实目标执行分离：

```text
local_only.json + Juice Shop Scope
              -> 精确主机/端口 preflight
              -> 受限 GET（不保留响应正文）
              -> httpx/katana 表面发现（服务可达时）
              -> 扫描后 Ground Truth 对照
              -> 验证工件 + 人工报告
```

该分支不会启动公网流程、不会扩展外链；服务不可用时标记为 `BLOCKED_DEPENDENCY`，不会把空
结果当成干净扫描。

## 数据库

SQLite 保存运行/状态、资产、快照、增量差异、全局 Finding/指纹、每次运行的 Finding 关联、
证据摘要、检查点、事件、支出、人工提交和报告路径。数据库文件已由 Git 忽略。

## 模型路由与 AI 成本

`ModelRouter` 根据 `config/models.yaml` 提供 bulk/primary/expert 通道。primary 连接本地
Ollama 的 `qwen-agent-stable:30b`，expert 配置为 `qwen3-coder:30b`；失败、无效或超时会回退到
确定性的本地启发式规则。`AITriage` 输出候选/人工复核处置，预算门控用尽时转人工；发送给本地
模型前会脱敏 Finding 数据。

远程路径完全独立：`DeepSeekProvider` 通过 OpenAI 兼容 Chat Completions 访问
`deepseek-v4-flash`，`OpenAIProvider` 访问 Responses API 且默认禁用。两者都不是自动回退。
`remote-preview` 只生成规范化脱敏载荷和 SHA-256 摘要，不联网；`remote-triage` 必须有新鲜且
完全匹配的摘要、`--confirm-external`、Scope/STOP 检查，然后发送一次非流式请求，并将建议结果
单独写入 `ai_reviews`，不覆盖本地分诊。密钥只从 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 读取，
不会持久化。

## 磁盘和资源控制

`balanced` 模式在每个本地阶段前检查项目目录用量：80 GiB 警告，90 GiB 硬停止。资源指标
可选；CPU/RAM 明确超限时暂停，指标不可用时报告 unknown。人工 STOP 是项目根目录下的标记文件。

## 已安装工具和方法

Subfinder v2.15.0、httpx v1.10.0、Katana v1.7.0 和 Nuclei v3.11.1 的官方 Windows amd64
压缩包下载到 `vendor\downloads`，已校验 SHA-256 并展开到 `vendor\bin`。ZAP 2.17.0 Core
下载并校验于 `vendor\zap`。未使用付费服务或代理。BBOT/reconFTW 受下述环境限制，尚未接入。

## 本轮修复与人工目标入口

`START_SYSTEM.ps1` 保留 UTF-8 BOM，并设置 `$ProgressPreference = 'SilentlyContinue'`，修复 Windows
PowerShell/Windows Terminal 中 `Invoke-WebRequest` 的进度重绘导致的中文重复显示。新增
`python -m src_auto target-review` 作为离线人工选择/Scope 预览入口；该入口不联网、不启动工具，
真实执行仍只能从 `run-live --execute-live` 进入，并继续受策略、Scope 和人工计划三重门控。

新增 `src_auto/local_labs.py`、`src_auto/local_discovery.py`、`src_auto/adjudication.py` 和
`tools/run_local_lab_validation.py`，对三个固定回环靶场做生命周期管理、表面发现、ZAP quick
scan、逐项裁决和三轮稳定性观察；工件统一写入 `validation\autotest\local_labs\`，外部 URL
仅记录为排除项，远程 AI 调用恒为 0。旧的 `run_autonomous_validation.py` 仅保留历史 Juice
Shop 兼容路径。

## 测试与 E2E

详见 `TEST_REPORT.md`：159 个自动化测试通过，compileall、回环 HTTP、CLI E2E、本地 Juice Shop
安全门控、DeepSeek/OpenAI 假 Provider 契约、远程 CLI 门控、启动会话同意硬门、WinForms 图形主菜单、
补天目标录入校验和 STOP/RESUME 均已验证。
本地验收没有发起远程 AI 调用；聊天中暴露的旧密钥必须先撤销并替换，才可进行单独授权的 DeepSeek 探测。

## 运维

- 启动本地：`START.bat RUN_ID` 或 `python -m src_auto run --run-id ... --local-lab`；
- 停止：`STOP.bat RUN_ID`；
- 恢复：`python -m src_auto resume --run-id ... --local-lab`；
- 查看状态/Finding/报告：`STATUS.bat`、`python -m src_auto findings`、`python -m src_auto reports`；
- 桌面一键启动：`START_SYSTEM.ps1` 默认打开简体中文图形主菜单；点击本地靶场检测后才以
  `-RunLocalLab` 启动本地 Ollama，并且只运行 local-lab 流程；
- 人工远程审阅：设置轮换后的 `DEEPSEEK_API_KEY`，运行 `remote-preview` 并检查脱敏载荷/摘要，
  再使用 `remote-triage --confirm-external --confirm-digest ...`。设计上没有金额或调用次数上限，
  只有单请求 Token 限制和事后估算成本记录；
- 第一个真实目标：根据当前平台规则生成新候选，人工创建匹配的 `scope_confirmed.yaml`，再创建
  真实运行并复核 Scope 摘要。本次构建没有使用真实目标；
- 受控外部流程：复制 `config/live_plan.example.yaml`，最终复核前保持 false，先运行 dry gate，
  只有策略和 Scope 都批准后才可考虑 `--execute-live`。本次构建没有使用真实目标；
- 本地 Juice Shop：依次运行 `python -m src_auto juice-shop-status --human`、
  `python -m src_auto juice-shop-baseline --human`，再在人工确认后运行
  `python -m src_auto juice-shop-zap --confirm-local --human`。前两步是安全的回环发现，ZAP
  结果在人工验证前始终保持 `POSSIBLE`。

## 已知限制

详见 `KNOWN_ISSUES.md`。重点包括：Nuclei 执行被端点安全软件阻断，BBOT/reconFTW 尚未接入
当前 Windows 工作流，ZAP 候选仍需人工裁决，并且不承诺任何漏洞被补天接受或产生收益。

# SRC-Auto 平台完整使用手册

版本：V0.1.1（本地 Ollama 接入版）  
项目路径：D:\网络安全文件夹\SRC-Auto  
适用系统：Windows 11 / PowerShell  
当前 Git 基线：cee87db2eede55965a02ffa0e9c329697937eab8

> 本手册描述当前已经落地的控制层、本地模型接入和本地靶场流程。它不授予任何真实网站测试权限。

---

## 1. 平台定位

SRC-Auto 是一个“授权范围门控 + 资产/请求流水线 + Finding 去重 + AI 辅助分诊 + 最小证据 + 补天报告草稿”的控制层。

当前能做：

- 在请求前检查 Scope，默认拒绝越界主机、第三方主机、错误端口和越界跳转；
- 记录运行、资产快照、历史差异、Finding 指纹和每次运行关联；
- 使用本地 Ollama 做脱敏后的 Finding 分诊，失败时自动回退启发式；
- 检查预算、磁盘、资源和人工 STOP；
- 生成最小证据和补天人工审核报告；
- 在 loopback 本地靶场执行完整 E2E；
- 对外部工具保持显式适配器门控。

当前不能做：

- 自动攻击任意互联网网站；
- 绕过登录、验证码、WAF 或访问控制；
- 暴力破解、凭据填充、删除/修改真实数据、DoS、持久化或横向移动；
- 自动提交补天报告；
- 保证漏洞被接受、保证收益或保证获得赏金。

补天项目当前规则优先于本手册。某些众测场景对自动化扫描有明确限制，开始真实目标前必须读取项目规则并人工确认。[补天官方帮助页](https://zhongce.butian.net/Help.html)

## 2. 安全边界

真实目标必须使用单独的 scope_confirmed.yaml，并且至少包含：

    confirmed: true
    allow_network_contact: true

候选 Scope 永远不能自动升级为确认 Scope。默认禁止：

- 未授权扫描；
- 暴力破解、密码喷洒、凭据填充；
- 删除、修改或破坏数据；
- 拒绝服务和压力测试；
- 持久化、横向移动和权限扩散；
- 大量收集用户数据、Cookie、Token、密码或个人信息；
- 自动提交补天报告。

## 3. 首次检查

打开 PowerShell：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    python -m unittest discover -s tests -v
    python -m compileall -q src_auto lab tests
    python -m src_auto tool-status
    python -m src_auto model-status
    python -m src_auto status

当前验收基线：

- 32 项自动化测试通过；
- compileall 通过；
- loopback E2E 通过；
- STOP/RESUME 通过；
- Ollama Provider 有真实本地调用记录；
- Ollama 不可用时会回退启发式，不会阻断安全流水线。

## 4. 项目目录

    D:\网络安全文件夹\SRC-Auto\
    ├─ src_auto\                 Python 控制层
    │  ├─ scope.py               Scope 和 Fail Closed
    │  ├─ scope_resolver.py      规则快照转候选 Scope
    │  ├─ store.py               SQLite、资产、Finding、Evidence、Checkpoint
    │  ├─ controls.py            预算、磁盘、资源、STOP
    │  ├─ adapters.py            外部工具安全适配器
    │  ├─ pipeline.py            本地和外部流水线控制
    │  ├─ ai.py                  Ollama + 启发式回退
    │  ├─ reporting.py           Evidence 和报告草稿
    │  ├─ live_plan.py           外部计划校验
    │  └─ cli.py                 命令行入口
    ├─ config\                   策略和模型配置
    ├─ lab\                      loopback 靶场和 fixture
    ├─ tests\                    自动化测试
    ├─ data\                     SQLite 数据库
    ├─ evidence\                 最小证据
    ├─ reports\                  报告草稿
    ├─ vendor\                   便携工具和 ZAP
    ├─ START_SYSTEM.ps1          一键启动脚本
    ├─ START.bat                 已有运行入口
    ├─ STOP.bat                  人工停止入口
    ├─ STATUS.bat                状态入口
    └─ USER_MANUAL.md            本手册

项目外的 qa_zut_report 和 build_zut_report.py 属于用户既有文件，不应写入或提交到本项目 Git。

## 5. 一键启动本地系统

桌面快捷方式现在指向 START_SYSTEM.ps1。双击桌面上的 SRC-Auto 一键启动快捷方式后，脚本会：

1. 切换到 D:\网络安全文件夹\SRC-Auto；
2. 检查本机 Ollama；
3. 如果 Ollama 没有运行，则手动启动 ollama serve；
4. 等待本地 API 127.0.0.1:11434；
5. 创建 local-lab 运行记录；
6. 执行本地 loopback E2E；
7. 输出 Findings 和报告索引；
8. 保持窗口打开，等待你查看结果。

这个快捷方式只是一种“手动点击启动”，不会创建 Windows 服务、计划任务或开机自启动，也不会连接真实补天目标。

脚本位置：

    D:\网络安全文件夹\SRC-Auto\START_SYSTEM.ps1

如需从 PowerShell 启动：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\START_SYSTEM.ps1

如果 Ollama 不可用，启动器会继续执行本地流水线，并使用启发式分诊回退。

## 6. 手动运行本地靶场

创建运行记录：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    $newRun = python -m src_auto new --target-id local-lab --scope config\targets\local-lab\scope_confirmed.yaml --mode local | ConvertFrom-Json
    $run = $newRun.run_id
    Write-Output "RUN_ID=$run"

执行：

    python -m src_auto run --run-id $run --scope config\targets\local-lab\scope_confirmed.yaml --local-lab

查看：

    python -m src_auto status --run-id $run
    python -m src_auto findings --run-id $run
    python -m src_auto reports

本地报告：

    D:\网络安全文件夹\SRC-Auto\reports\<RUN_ID>.md

最小证据：

    D:\网络安全文件夹\SRC-Auto\evidence\<RUN_ID>\<FINGERPRINT>.json

## 7. loopback HTTP 靶场

在一个 PowerShell 窗口：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    python -m lab.server

靶场只监听：

    http://127.0.0.1:8765

在另一个窗口，可以验证已经下载的安全工具：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    vendor\bin\httpx.exe -silent -no-color -u http://127.0.0.1:8765/
    vendor\bin\katana.exe -silent -u http://127.0.0.1:8765/ -d 1 -jc false

结束后，在运行 lab.server 的窗口按 Ctrl+C。

## 8. START、STOP、STATUS、RESUME

手动启动已有本地运行：

    START.bat RUN_ID

停止：

    STOP.bat RUN_ID

或者：

    python -m src_auto stop --run-id RUN_ID

查看：

    STATUS.bat
    STATUS.bat --run-id RUN_ID
    python -m src_auto status --run-id RUN_ID

恢复：

    python -m src_auto resume --run-id RUN_ID --scope config\targets\local-lab\scope_confirmed.yaml --local-lab

STOP 会创建项目根目录的 STOP 文件。只有 resume 会清除它。停止发生在阶段边界，不会强制杀死外部工具进程。

## 9. Scope 管理

本地示例：

    config\targets\local-lab\scope_candidate.yaml
    config\targets\local-lab\scope_confirmed.yaml

候选文件必须保持：

    confirmed: false
    allow_network_contact: false

确认文件应明确：

    target_id: example-target
    vendor: example-vendor
    authorization_source: current-program-rules
    root_domains:
      - example.com
    allowed_hosts:
      - www.example.com
      - api.example.com
    excluded_hosts:
      - login.example.com
    allowed_ports:
      - 443
    test_window: operator-confirmed-window
    confirmed: true
    allow_network_contact: true

从规则快照生成候选：

    python -m src_auto resolve-scope --snapshot rules.json --output-dir config\targets\example-target

该命令只处理已经提供的明确规则，不会自动访问平台、猜测域名或授予权限。

常见拒绝原因：

| 原因 | 含义 |
|---|---|
| scope_not_confirmed | 没有人工确认 |
| host_not_in_scope | 主机不在允许范围 |
| port_not_in_scope | 端口未授权 |
| original_not_in_scope | 原始 URL 不在范围 |
| invalid_or_unsupported_url | URL 不是 HTTP(S) |
| scope_hash_mismatch | 运行记录与 Scope 文件不一致 |

## 10. 当前流水线

    asset_discovery
    http_probe
    crawl
    candidate_scan
    passive_scan
    normalize
    dedup
    triage
    evidence
    report

工具设计顺序：

    BBOT -> Subfinder -> httpx -> Katana -> Nuclei safe checks -> ZAP passive -> reconFTW Deep Recon

当前外部流水线保持显式适配器门控。没有确认 Scope、工具计划和人工执行条件时，不会自动连接真实目标。

## 10.1 受控外部计划入口

外部入口是 `run-live`，不是桌面一键启动器。计划模板位于：

    D:\网络安全文件夹\SRC-Auto\config\live_plan.example.yaml

模板中的 `target_urls`、工具顺序和参数都必须由人工根据当前补天项目规则填写。模板默认 `manual_execution_confirmed: false`，这不是授权文件，也不能替代 `scope_confirmed.yaml`。

真实目标的准备顺序：

1. 保存当前平台规则和授权来源，生成独立目标目录；
2. 人工创建并核对 `scope_confirmed.yaml`，确认 `confirmed=true`、`allow_network_contact=true`、主机/端口/排除项和时间窗口；
3. `python -m src_auto new --target-id <id> --scope config/targets/<id>/scope_confirmed.yaml --mode real`；
4. 复制并填写 `config/live_plan.example.yaml`，设置人工操作人、授权工单、目标 URL、有限的工具序列和参数；
5. 最终复核后才把计划中的 `manual_execution_confirmed` 改为 `true`；
6. 默认策略仍拒绝真实网络，必须由人工在 `config/policy.yaml` 将 `network.allow_real_targets` 改为 `true`，且只在批准的测试窗口内使用；
7. 先运行一次不带 `--execute-live` 的计划检查，再在确认没有越界参数时加 `--execute-live`。

命令格式：

    python -m src_auto run-live --run-id <REAL_RUN_ID> --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml
    python -m src_auto run-live --run-id <REAL_RUN_ID> --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml --execute-live

第一条命令只验证计划、策略和 Scope；第二条才会按计划创建 `SafeToolAdapter` 并启动工具。它不会自动发现新域名、自动扩大授权范围、处理登录验证码、上传数据或提交补天。计划摘要会写入 SQLite 事件，便于复核。

## 11. 外部工具状态

执行：

    python -m src_auto tool-status

当前状态：

| 工具 | 当前状态 |
|---|---|
| Subfinder v2.15.0 | 便携包和版本验证通过 |
| httpx v1.10.0 | 版本和 loopback 验证通过 |
| Katana v1.7.0 | 版本和 loopback 验证通过 |
| OWASP ZAP 2.17.0 | D 盘 Core 包和版本验证通过 |
| Nuclei v3.11.1 | 包哈希通过，但被端点安全软件阻止执行 |
| BBOT 3.0.1 | 当前 Python/Windows/WSL 环境无法运行 |
| reconFTW | 当前没有 Linux shell/WSL |

工具目录：

    D:\网络安全文件夹\SRC-Auto\vendor\bin
    D:\网络安全文件夹\SRC-Auto\vendor\zap

不要关闭或绕过端点安全软件，不要使用来源不明的二进制。

## 12. 本地 Ollama 模型

检查：

    ollama --version
    ollama list
    ollama ps
    python -m src_auto model-status

当前默认配置：

    primary: qwen-agent-stable:30b
    expert: qwen3-coder:30b
    fallback: deterministic local heuristic
    endpoint: http://127.0.0.1:11434

选择 qwen-agent-stable:30b 作为 primary，是因为它在当前 Ollama 版本上真实返回了可解析结果；codex-balanced:20b 在当前模板下曾返回空 response，因此不作为默认自动分诊模型，但仍可在配置中手动切换。

Ollama Provider 的数据边界：

- 只发送标题、去掉查询参数的 URL、参数名、严重性和最小证据；
- 对 token、secret、password、authorization、cookie、api-key 等字段做脱敏；
- 不发送完整响应正文、Cookie、凭据或用户数据；
- 返回格式必须经过 JSON 校验；
- Ollama 请求失败、超时或输出格式错误时，自动回退启发式；
- 远程 API 默认关闭。

Ollama 服务如果没有运行，手动启动：

    ollama serve

一键启动脚本会在本地手动启动它，但不会注册开机自启动。

## 13. AI 分诊结果

分诊结果常见状态：

| 状态 | 含义 |
|---|---|
| candidate | 可以进入人工复核 |
| needs_manual_validation | 需要人工验证影响 |
| manual_review | 模型不可用、预算不足或输出不可信 |
| false_positive | 模型认为更可能是误报，仍不能替代人工决定 |

模型只做建议，不得：

- 扩大 Scope；
- 自行选择第三方目标；
- 自行生成破坏性载荷；
- 自行提交补天报告；
- 声称已经成功利用漏洞。

## 14. SQLite 和审计

数据库：

    D:\网络安全文件夹\SRC-Auto\data\src_auto.sqlite3

主要表：

- runs：运行状态；
- assets：资产和稳定指纹；
- asset_snapshots：资产快照；
- findings：全局 Finding 指纹；
- finding_runs：Finding 与每次运行的关联；
- evidence：证据路径和 SHA-256；
- checkpoints：阶段检查点；
- events：审计事件；
- spend：模型和其他成本；
- submissions：人工提交状态、赏金和人工时间；
- reports：报告路径。

同一个 Finding 在不同运行中会全局去重，但仍会在每一次运行的 findings 命令中显示。

查看表：

    python -c "import sqlite3; c=sqlite3.connect(r'D:\网络安全文件夹\SRC-Auto\data\src_auto.sqlite3'); print([r[0] for r in c.execute(\"select name from sqlite_master where type='table' order by name\")]); c.close()"

## 15. Evidence 和补天报告

Evidence 只保留：

- 运行 ID；
- Finding 指纹；
- 标题；
- URL；
- 严重性；
- 最小观察；
- 文件 SHA-256；
- 安全说明。

报告是人工审核草稿，不是自动提交。提交前必须检查：

1. 目标仍在授权 Scope；
2. 时间窗口仍然有效；
3. 复现不会写入、删除或破坏真实数据；
4. 影响和严重性没有夸大；
5. 没有凭据、Cookie、Token 或用户数据；
6. Finding 没有重复；
7. 当前补天项目允许这种测试方式。

## 16. 预算、磁盘和资源

默认配置：

    profile: balanced
    monthly AI budget: ¥100
    daily AI budget: ¥10
    project disk warning: 80 GiB
    project disk hard stop: 90 GiB
    CPU target: <=70%
    memory target: <=20 GiB

当前 AI 使用本地 Ollama，成本按 ¥0 计；如果将来接入付费 API，必须显式配置预算和审计。

项目目录大小检查：

    Get-ChildItem -LiteralPath 'D:\网络安全文件夹\SRC-Auto' -Recurse -File -Force | Measure-Object -Property Length -Sum

## 17. 备份和恢复

停止运行后备份数据库：

    $stamp = Get-Date -Format yyyyMMdd-HHmmss
    Copy-Item -LiteralPath 'D:\网络安全文件夹\SRC-Auto\data\src_auto.sqlite3' -Destination ("D:\网络安全文件夹\SRC-Auto\data\backup-$stamp.sqlite3")

恢复原则：

1. 停止 SRC-Auto 和相关工具；
2. 保留当前数据库副本；
3. 用备份覆盖 data\src_auto.sqlite3；
4. 运行全量测试；
5. 查看 status、findings 和 reports。

不要把 SQLite、Evidence、Token、Key 或便携工具提交 Git。

## 18. 故障排查

### scope_not_confirmed

Scope 没有人工确认。不要绕过，重新检查当前平台规则和确认文件。

### scope_hash_mismatch

运行记录和 Scope 文件不一致。重新创建运行记录并保存新的 Scope hash。

### blocked_adapter 或 awaiting_adapter

外部适配器没有显式注入，或外部工具计划未通过门控。这不是扫描成功。

### tool unavailable

工具不在 PATH 或 vendor 目录。只使用官方发行源和可验证哈希。

### Nuclei 被 Windows 阻止

当前 Nuclei v3.11.1 的执行被端点安全软件阻止。不要关闭或绕过端点安全，应由管理员审查。

### WSL 不可用

BBOT/reconFTW 需要 Linux/WSL。安装 WSL2 可能需要管理员权限和重启。

### blocked_disk

清理项目内部旧运行数据前先确认其不再需要，不要删除项目外文件。

### SQLite 被占用

关闭其他 SRC-Auto 进程、编辑器和数据库查看工具后重试。

### Ollama 不可用

执行：

    ollama ps
    python -m src_auto model-status

如果 API 不可用，系统会自动使用启发式分诊；这不会扩大 Scope，也不会自动扫描真实目标。

### 端口冲突

如果 8765 被占用，停止占用该端口的本地服务后再启动 lab.server。不要将本地靶场绑定公网地址。

## 19. 第一个真实目标上线前清单

    [ ] 当前补天项目规则已保存
    [ ] 测试时间已确认
    [ ] 允许根域、主机和端口已明确
    [ ] CDN、SSO、支付、云和外部 API 边界已明确
    [ ] 排除项已明确
    [ ] scope_candidate.yaml 已生成
    [ ] 人工已创建独立 scope_confirmed.yaml
    [ ] confirmed=true
    [ ] allow_network_contact=true
    [ ] Scope hash 已核对
    [ ] 工具状态已核对
    [ ] Ollama 或回退策略已确认
    [ ] 预算和磁盘空间足够
    [ ] 没有 STOP 标记
    [ ] 测试方法符合补天规则
    [ ] 已准备人工复核报告

只有在全部满足后，才考虑由人工明确启动受控外部适配器。当前版本不会从一键启动器自动进入真实目标。

## 20. 报告提交清单

    [ ] Finding 不重复
    [ ] URL 和主机仍在 Scope
    [ ] Evidence 最小且非破坏性
    [ ] 没有凭据、Token、Cookie 或用户数据
    [ ] 复现步骤不会修改真实数据
    [ ] 影响和严重性经过人工复核
    [ ] 没有承诺一定获得赏金
    [ ] 只通过补天平台人工提交

## 21. 当前限制和升级顺序

当前限制：

1. WSL2/Ubuntu 未安装；
2. BBOT 受 Python 版本和 POSIX 环境限制；
3. reconFTW 需要 Linux shell；
4. Nuclei 被端点安全软件阻止；
5. ZAP 当前只做版本验证；
6. 外部工具输出目前主要保留在工具事件中，尚未自动归一化为完整 Finding；实时参数仍需经过人工审核的工具计划；
7. 本地 Ollama 推理速度受 CPU 和模型大小影响；
8. 不保证漏洞接受、赏金或利润。

推荐升级顺序：

1. 保持 Ollama Provider 和启发式回退；
2. 完善外部工具计划和输出归一化；
3. 在 WSL2 中验证 BBOT/reconFTW；
4. 在本地靶场和平台明确允许时验证 Nuclei；
5. 增加更多真实但授权的本地测试场景；
6. 不擅自加入 Kubernetes、消息队列、ES、Grafana、复杂 WebUI、移动 App、代理池或商业扫描器。

## 22. 相关文件

- README.md：项目简介；
- OPERATIONS.md：运维速查；
- POLICY.md：安全策略；
- ARCHITECTURE.md：架构；
- TEST_REPORT.md：测试报告；
- IMPLEMENTATION_REPORT.md：实现报告；
- KNOWN_ISSUES.md：已知问题；
- tools.lock.yaml：工具版本和哈希；
- START_SYSTEM.ps1：一键启动脚本；
- config/live_plan.example.yaml：受控外部工具计划模板（默认不执行）；
- src_auto/live_plan.py：外部计划校验和摘要；
- preservation_manifest.sha256：既有文件保护快照。

# SRC-Auto 平台完整使用手册

> **2026-08-26 严格计划更新：** 当前实现以 `docs/THREE_PHASE_USER_MANUAL.md` 和
> `docs/THREE_PHASE_UPGRADE_REPORT.md` 为准。本轮已加入第五个仅回环的 `business-api`
> 靶场（`127.0.0.1:8084`）、业务 API 授权矩阵、蓝队被动日志分析和 Figma V2 控制台入口；
> 完整测试为 `238/238` 通过。Docker Desktop 已恢复后，五个靶场均通过健康检查，三轮本地
> 验收为 `AUTHORIZED_LOCAL_VALIDATION_READY`，独立回归 `30/30` 通过；若 Docker 再次不可用，
> 控制台必须显示依赖阻断，不能把历史成绩冒充当前容器运行成绩。

> 当前三期升级后的简体中文主手册请优先阅读 [`docs/THREE_PHASE_USER_MANUAL.md`](docs/THREE_PHASE_USER_MANUAL.md)，最终验收摘要见 [`docs/THREE_PHASE_UPGRADE_REPORT.md`](docs/THREE_PHASE_UPGRADE_REPORT.md)。本文件保留历史命令与兼容入口，旧的“三靶场/159 项”数字不覆盖 2026-08-24 的最新验收结果；本机生成的验证报告位于被 Git 忽略的 `validation/` 目录。

版本：V0.6.0（WSL2/Docker + 五回环靶场 + 非破坏性安全回归版）
项目路径：D:\网络安全文件夹\SRC-Auto  
适用系统：Windows 11 / PowerShell  
当前 Git 基线：工作区保留既有未提交改动；设计快照已单独记录（以实际 `git status` 为准）

> 本手册描述当前已经落地的控制层、本地模型接入和本地靶场流程。它不授予任何真实网站测试权限。

> **2026-08-21 当前状态：** 已按操作者授权安装 WSL2 2.7.12、Ubuntu 和 Docker Desktop
> 4.87.0。Ubuntu 位于 `D:\网络安全文件夹\WSL\Ubuntu`，Docker WSL 数据位于
> `D:\网络安全文件夹\DockerData\wsl`；Docker Desktop 程序本身按官方 per-user 方式
> 保留在用户目录，属于已批准的系统组件例外。`juice-shop` 当前只映射
> `127.0.0.1:3000`，远程 AI 调用为 0。旧的“Docker 未安装”文字只代表安装前快照，
> 以本手册第 23 节和 `JUICE_SHOP_VALIDATION_REPORT.md` 第 0 节为准。

> **2026-08-22 最终本地验收：** 已在同一 Compose 项目中固定并启动 Juice Shop
> `127.0.0.1:3000`、DVWA `127.0.0.1:8081` 与 WebGoat `127.0.0.1:8082`，三个应用靶场各完成 3 轮。
> DVWA 的 MariaDB 仅在 Compose 网络内运行，不发布宿主端口。准确逐轮成绩见
> `validation\autotest\LOCAL_LAB_TEST_REPORT.md`，机器源数据见
> `validation\autotest\LOCAL_LAB_SCORE.json`。另有 6 个安全回归用例共 18 次执行，18/18 通过，
> 见 `validation\autotest\local_regression\LOCAL_REGRESSION_REPORT.md`。这些结果均为本地控制项/表面
> 回归基准，不是赏金漏洞命中率；`bounty_ready_count=0`、外部目标接触为 0、远程 AI 调用为 0。

## 代码优先可视化控制台（新增）

如果希望使用更清晰的浏览器界面，可在项目根目录执行：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
.\tools\start_dashboard.ps1
```

启动器会检查本地构建产物，必要时使用项目专用 Node.js 构建一次，然后只在
`http://127.0.0.1:4173/` 启动 Vite 预览并打开默认浏览器。它不会启动 Docker、访问域名、
调用远程 AI 或提交任何报告。若只想启动服务而不打开浏览器，使用
`.\tools\start_dashboard.ps1 -NoBrowser`；统一入口使用 `.\START_SYSTEM.ps1 -Dashboard`。

可视化首页的“本地靶场”“目标与授权”“离线审阅”“结果与报告”和“AI 设置”均是可点击导航。
任务详情支持暂停、继续、停止和事件脱敏详情；授权目标页面只保存本地草稿并进行 URL、主机、
端口、时间窗和授权说明校验；候选与报告页面只读展示，报告路径受白名单限制，脚本不会执行。
真实目标仍必须经过人工授权、范围确认和最终人工提交。

### 查看单个本地靶场任务

1. 在浏览器 Dashboard 左侧点击 **本地靶场**。
2. 在“本地靶场矩阵”中点击靶场名称，或点击同一行的 **查看任务**。
3. 详情页会显示该靶场对应的 `127.0.0.1:<端口>`、健康状态、任务阶段、脱敏事件和报告入口；点击 **返回靶场列表** 可继续查看其他靶场。
4. 页面顶部的 **打开当前任务** 是五靶场聚合任务，和单个靶场详情相互独立。

窄屏设备会把每个靶场重排为一张可点击卡片，避免横向挤压。Dashboard 中的靶场状态和事件是本地演示夹具，不代表 Docker 容器在此刻已运行，也不代表真实漏洞扫描结果。查看页面不会启动容器、访问真实网站、调用远程 AI 或自动提交补天报告；需要确认运行状态时，应以本机回环端口检查和 `validation\` 下的本地验收结果为准。

旧 WinForms 控制台保持兼容：不带参数运行 `START_SYSTEM.ps1`，或显式使用
`.\START_SYSTEM.ps1 -LegacyGui`。升级前回退点和安全恢复步骤见 `docs/部署与恢复手册.md`。

## 界面语言和输出兼容性

当前版本以简体中文作为操作者界面的默认语言。桌面快捷方式、PowerShell 启动器、
Juice Shop 状态/基线/ZAP 摘要、CLI 帮助和错误提示都使用中文；第三方工具原始输出仍
保留在受限、脱敏的 JSON 工件中。

机器字段继续使用英文，避免破坏已有脚本和历史报告。例如：

```json
{
  "status": "POSSIBLE_FINDINGS",
  "status_zh": "存在待人工复核的可能项",
  "reason": "manual_verification_required",
  "reason_zh": "需要人工复核后才能确认"
}
```

交互式终端默认显示中文摘要；管道、脚本捕获和 `--json` 使用机器可读 JSON；需要强制
中文时使用 `--human`。例如：

    python -m src_auto juice-shop-status --human
    python -m src_auto juice-shop-status --json

未指定模式时，程序会根据 stdout 是否为交互终端自动选择；这保证桌面启动器的
`ConvertFrom-Json` 管道不会被中文提示污染。
如果旧版 PowerShell 终端显示乱码，可先执行：

    $env:PYTHONIOENCODING = "utf-8"

## 桌面图形主菜单与补天目标录入

桌面上的 **SRC-Auto 一键启动** 现在直接打开简体中文 WinForms 主菜单。主菜单顶部会明确显示
“默认仅本机回环靶场”和“真实目标不会自动执行”，因此打开窗口不会自动访问任何补天项目。
所有状态、报告和密钥密文仍写入 `D:\网络安全文件夹\SRC-Auto`。

主菜单按钮用途如下：

| 按钮 | 作用 |
|---|---|
| 本地靶场检测 | 打开独立终端并以 `-RunLocalLab` 启动既有三靶场本地验收；仅访问 `127.0.0.1` |
| 新建授权目标 | 打开补天目标录入表单，可保存未确认草稿，或在人工勾选两项确认后生成 Scope 并离线审阅 |
| 选择已有目标 | 打开文件夹优先选择器，可从 `config\\targets` 根目录或任意下级分组查看已有 Scope |
| 离线审阅目标范围 | 选择一个或多个完整目标，逐个调用 `target-review` 并生成本地汇总；不会发出网络请求 |
| 查看 Findings 和报告 | 列出项目内 `reports` 与 `validation` 摘要；单击文件名后在右侧只读预览详细内容，供人工阅读和整理报告草稿 |
| AI 模型与密钥设置 | 打开 Dashboard 内置的“系统设置”；可直接保存 DeepSeek / 智谱 / OpenRouter 密钥和模型 ID，默认不启用远程 AI，也不会回显已保存密钥 |

### 离线审阅目标范围选择器

点击 **选择已有目标** 或 **离线审阅目标范围** 后，会打开同一个本地目标选择器。它解决了旧版只能逐层进入目录、
最后必须点选单个 `scope_confirmed.yaml` 的问题。

1. 路径框默认指向 `D:\网络安全文件夹\SRC-Auto\config\targets`。可以直接粘贴该目录内的高级别分组目录并按 Enter。
2. **项目目标根** 一键返回 `config\\targets`；**上一级** 返回父目录，但不会越过安全根目录。
3. **选择文件夹** 打开 Windows 文件夹选择窗口；**刷新** 重新读取当前路径。
4. 选择高级别目录时，程序会递归显示所有包含 Scope 或人工计划文件的下级目标，无需逐层打开。
5. 只有同时存在 `scope_confirmed.yaml` 和 `live_plan.yaml` 的项目显示为 **可审阅**，并允许勾选。
6. 只有 `scope_candidate.yaml` 的项目显示为 **候选 Scope（不可审阅）**；已有确认 Scope 但缺少计划的项目显示为
   **缺少 live_plan.yaml**。这些项目会标灰，不能通过全选或手工勾选进入审阅。
7. 可勾选一个或多个目标，然后点击 **开始离线审阅**。每个目标单独执行，授权范围不会合并。
8. 结果窗口会显示每个目标的“通过”“已阻止”或“需要人工复核”，安全汇总写入
   `D:\网络安全文件夹\SRC-Auto\reports\offline-review\`。

路径输入仍被严格限制在项目的 `config\\targets` 下。项目外路径、缺失目录、错误文件名、Scope 与计划不在同一目录、
候选 Scope 和不完整配置都会被阻止。选择器只调用 `target-review --confirm-selection --json`，不会启动 `run-live`、
不会调用外部扫描器，也不会连接目标网站；汇总文件固定记录 `network_contact=false`。

### 新建授权目标的填写顺序

1. 点击 **新建授权目标**。
2. 填写项目编号（仅小写英文、数字、`_` 或 `-`）、平台/项目名称、补天项目规则或授权来源。
3. 在 **起始地址** 填写完整的 `https://` 地址，例如 `https://example.com/`；不得填写用户名、查询串或片段。
4. 填写允许的根域名、允许主机（每行或逗号分隔）、排除主机和允许端口。目标主机必须同时出现在允许主机中，且端口必须在允许端口列表中；表单默认端口为 `443`。
5. 补充测试时间窗和操作者名称，先点 **保存草稿** 检查格式，或在确认授权后同时勾选：
   - “我已人工核对补天项目规则、资产归属和排除项”；
   - “项目规则明确允许低频、非破坏性自动化测试”。
6. 点击 **保存并离线审阅**。程序会把配置写入 `config\\targets\\<项目编号>\\`，然后仅在本机运行目标范围审阅。审阅窗口显示的结果仍需要人工复核；它不会自动执行真实目标测试、不会调用外部扫描器、也不会提交补天报告。

表单校验失败时会显示明确原因码，例如 `target_host_not_allowed`、
`target_port_not_allowed` 或 `target_url_must_be_clean`。配置写入前会做路径边界检查，不能写到项目目录之外。

> 真实目标的后续测试必须另行阅读补天项目规则、再次人工确认授权和低频/非破坏性边界。图形菜单只是减少录入错误，
> 不会把“草稿”升级为授权，也不会替操作者做最终执行决定。

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
- 在人工选择 Finding、确认脱敏摘要和 SHA-256 摘要后，单次调用 DeepSeek V4.1 Flash 做辅助审阅；
- 保留一个默认关闭的 OpenAI Responses API 适配器，等待独立的 OpenAI Platform API 密钥。

当前不能做：

- 自动攻击任意互联网网站；
- 绕过登录、验证码、WAF 或访问控制；
- 暴力破解、凭据填充、删除/修改真实数据、DoS、持久化或横向移动；
- 自动提交补天报告；
- 保证漏洞被接受、保证收益或保证获得赏金。

补天项目当前规则优先于本手册。某些众测场景对自动化扫描有明确限制，开始真实目标前必须读取项目规则并人工确认。[补天官方帮助页](https://zhongce.butian.net/Help.html)

## 1.1 三个本地靶场与安全回归入口

当前 Compose 清单固定以下服务，全部只发布到本机回环地址：

| 靶场 | 地址 | 用途 |
|---|---|---|
| OWASP Juice Shop | `http://127.0.0.1:3000/` | 公开首页、前端/API 表面和 ZAP 控制项 |
| DVWA + MariaDB | `http://127.0.0.1:8081/login.php` | 登录边界、SQLi 训练页面、无害反射标记；数据库不发布宿主端口 |
| OWASP WebGoat | `http://127.0.0.1:8082/WebGoat/` | 登录边界和课程入口；注册随机合成账号，不保存凭据 |

启动/状态/停止：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m src_auto local-labs status --json
python -m src_auto local-labs start
python -m src_auto local-labs stop
```

控制项验收会运行有限静态发现、ZAP quick scan 和保守裁决；它的
`TRUE_POSITIVE` 只代表本地控制项，不代表可提交漏洞。推荐先运行不发送利用 payload 的回归：

```powershell
python tools/run_local_regression.py --local-only --repeat-rounds 2 --json
# 只运行一个安全边界用例
python -m src_auto local-regression --local-only --lab dvwa --case dvwa-auth-boundary --json
```

回归用例固定为 `config\validation\local_regression_cases.json`，仅允许 GET/POST、显式断言和
`destructive=false`。客户端不跟随重定向，发送前检查 RuntimePolicy，响应只记录长度、SHA-256、
状态码和脱敏头；工件不含响应正文、Cookie、Token、账号密码。若想新增用例，必须先写测试，
保持 loopback、无破坏性动作，并在 `tests\test_local_regression.py` 中验证失败关闭。

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

- 159 项自动化测试通过（包含运行时白名单、三靶场生命周期、Juice Shop 只读探测、ZAP 解析/CLI 门控、Ground Truth、远程 Provider 假响应、离线 target-review、中文 UTF-8 控制台回归、本机安全回归、启动会话同意硬门、DPAPI 密钥存储、WinForms 主菜单分派、按钮真实点击和目标录入表单运行时测试）；
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
    │  ├─ remote_ai.py           DeepSeek/OpenAI 人工审阅适配器
    │  ├─ runtime_policy.py      local-only AI/主机/端口/并发硬门控
    │  ├─ juice_shop.py          127.0.0.1:3000 只读验证适配器
    │  ├─ target_review.py        人工目标选择/Scope 预览（不联网）
    │  ├─ validation.py          Ground Truth、Finding 归一化和指标
    │  ├─ local_labs.py          固定镜像的三靶场生命周期
    │  ├─ local_discovery.py     回环静态表面发现
    │  ├─ adjudication.py        控制项裁决与精确指标
    │  └─ cli.py                 命令行入口
    ├─ config\                   策略和模型配置
    ├─ lab\                      loopback 靶场和 fixture
    ├─ tests\                    自动化测试
    ├─ data\                     SQLite 数据库
    ├─ evidence\                 最小证据
    ├─ reports\                  报告草稿
    ├─ vendor\                   便携工具和 ZAP
    ├─ tools\                   本机自动化验收编排器
    ├─ validation\autotest\     预检、轮次、稳定性和最终报告
    │  └─ local_labs\            三靶场逐轮工件
    ├─ START_SYSTEM.ps1          一键启动脚本
    ├─ START.bat                 已有运行入口
    ├─ STOP.bat                  人工停止入口
    ├─ STATUS.bat                状态入口
    └─ USER_MANUAL.md            本手册

项目外的 qa_zut_report 和 build_zut_report.py 属于用户既有文件，不应写入或提交到本项目 Git。

## 5. 一键启动图形主菜单与本地系统

桌面快捷方式指向 `START_SYSTEM.ps1`，并以隐藏宿主终端、STA 模式启动图形主菜单。双击桌面上的
**SRC-Auto 一键启动** 后，默认只显示目标录入和本地操作菜单，不会启动 Docker、不询问远程 AI，
也不会连接真实补天目标。

在主菜单点击 **本地靶场检测** 后，才会打开独立终端并使用 `START_SYSTEM.ps1 -RunLocalLab` 执行本地流程：

1. 切换到 `D:\网络安全文件夹\SRC-Auto`；
2. 按启动前的人工选择决定是否启用 DeepSeek；未启用时整个会话不调用远程 AI；
3. 检查本机 Ollama（不可用时安全回退，不伪造成功）；
4. 通过固定 Compose 启动 Juice Shop `127.0.0.1:3000`、DVWA `127.0.0.1:8081` 和 WebGoat `127.0.0.1:8082`；
5. 等待三个应用容器健康后，执行三靶场 local-only 验收和非破坏性安全回归；
6. 输出 `LOCAL_LAB_SCORE.json`、逐轮发现/裁决工件和中文摘要，并保持终端窗口供人工查看。

快捷方式只是手动点击启动，不会创建 Windows 服务、计划任务或开机自启动。真实目标只能从主菜单人工录入并进行离线审阅；
没有独立、明确的人工授权和平台规则确认时，程序不会把它变成可执行计划。

脚本位置：

    D:\网络安全文件夹\SRC-Auto\START_SYSTEM.ps1

如需从 PowerShell 启动：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    # 打开图形主菜单
    powershell -NoProfile -Sta -ExecutionPolicy Bypass -File .\START_SYSTEM.ps1

    # 仅在你明确要跑本机靶场时使用
    powershell -NoProfile -Sta -ExecutionPolicy Bypass -File .\START_SYSTEM.ps1 -RunLocalLab

如果 Ollama 不可用，启动器会继续执行本地流水线，并使用启发式分诊回退。桌面启动器
永远不进入真实目标流程，也不调用远程 AI。

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

## 10.2 人工目标选择与范围预览（不联网）

当你已经取得补天项目的明确授权、但希望先手动选择目标时，使用 `target-review`。Scope 和计划都必须位于项目根目录内：

    python -m src_auto target-review --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml --human

命令会逐个显示目标的允许/拒绝、主机、端口、目标类型以及 Scope/计划 SHA-256 摘要；不会读取或打印工具命令参数、Cookie、Token，也不会发 HTTP 请求。没有 `--confirm-selection` 时返回 `awaiting_selection`；加上该开关只记录“人工选择已审阅”，返回 `selection_reviewed`，并提示下一步仍为：

    run-live --execute-live

这是第二道人工执行门。即便目标是非本地地址，当前测试也只允许离线 Scope Guard/mock 审阅，不会实际连接；`run-live` 还会继续检查 `allow_real_targets`、确认 Scope、人工计划摘要和 `--execute-live`。

## 10.3 本机自动化验收计划

当前 canonical 验收入口会自主管理三个固定回环应用靶场，不需要先手动运行旧的单容器命令：

    python -m src_auto local-labs status --json
    python -m src_auto local-labs start
    python -m src_auto local-validation --local-only --repeat-rounds 2

等价的脚本入口为：

    python tools/run_local_lab_validation.py --local-only --repeat-rounds 2

`--local-only` 是默认且唯一模式；脚本只使用 `http://127.0.0.1:3000/`、
`http://127.0.0.1:8081/login.php` 和 `http://127.0.0.1:8082/WebGoat/actuator/health`，每轮先重置服务，再等待健康检查、执行有限静态发现和
ZAP quick scan，并使用本地控制项裁决规则。旧 ZAP 文件不会被当作新轮次结果，命令失败时写
`NOT_TESTED`。`repeat-rounds 2` 表示额外重复 2 次，总计 3 轮/靶场。

工件目录：

    D:\网络安全文件夹\SRC-Auto\validation\autotest\

最终结果是 `LOCAL_LAB_TEST_REPORT.md`（人读）和 `LOCAL_LAB_SCORE.json`（机器读）；逐轮文件在
`local_labs\<lab>\round_nn\`，包括生命周期、发现、ZAP、裁决和分数。P0 核对 Scope Escape、Remote AI Calls、Secret Leakage、Crash 和
External Targets Contacted；完整 Juice Shop Ground Truth 未执行时 Precision/Recall 仍保持
`null`/`NOT_TESTED`。

最终三轮结果：DVWA、Juice Shop、WebGoat 的控制项 Precision/Recall/F1 以
`LOCAL_LAB_SCORE.json` 最新轮为准；这是控制项基准，不是赏金漏洞评分，三个靶场均
`bounty_ready_count=0`。独立的 `local-regression` 入口执行 6 个非破坏性用例，三轮共 18 次
全部通过；结果位于 `local_regression\LOCAL_REGRESSION_SCORE.json` 和
`local_regression\LOCAL_REGRESSION_REPORT.md`。

## 11. 外部工具状态

执行：

    python -m src_auto tool-status

当前状态：

| 工具 | 当前状态 |
|---|---|
| Subfinder v2.15.0 | 便携包和版本验证通过 |
| httpx v1.10.0 | 版本和 loopback 验证通过 |
| Katana v1.7.0 | 版本和 loopback 验证通过 |
| OWASP ZAP 2.17.0 | D 盘 Core 包、版本验证和 loopback quick scan 通过；候选待人工复核 |
| Nuclei v3.11.1 | 包哈希通过，但被端点安全软件阻止执行 |
| BBOT 3.0.1 | 当前 Python/Windows/WSL 环境无法运行 |
| reconFTW | WSL 已具备，但工具尚未接入或执行 |

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

## 12.1 人工启用 DeepSeek V4.1 Flash 审阅

远程模型是“对已经存在的 Finding 提供第二意见”，不是自动扫描器，也不会参与本地 Ollama 的故障回退。点击图形主菜单的 **本地靶场检测** 后，独立的本地验收启动器才会询问 DeepSeek 是否启用；选择否时，本次进程树设置会话级硬门，所有远程 Provider 在建连前返回 `remote_ai_disabled_for_session`。选择是也不会自动调用，仍必须由人选定 Finding、查看脱敏预览、核对摘要并显式确认 `remote-triage`。

### 12.1.1 密钥和提供商状态

项目支持“平台内置设置”“当前进程环境变量”和“当前 Windows 用户 DPAPI 加密文件”三种入口，不把密钥明文写入配置、SQLite、报告、事件或 Git。推荐启动 Dashboard，进入左侧 **系统设置**，选择服务商后直接粘贴密钥并点击 **保存设置**。保存时不联网，保存成功后输入框立即清空；已保存密钥只能覆盖或删除本地密文，前端不能读取明文。

密钥加密后固定保存在 `config\secrets\deepseek_api_key.dpapi`，该目录已被 Git 排除。DPAPI 文件只能由当前电脑上的当前 Windows 用户解密；换电脑或换用户后需要重新保存。以后桌面启动器选择“是”时自动解密到当前启动进程，选择“否”时不会读取或解密该文件。

不希望保存时，也可以只在当前 PowerShell 会话临时设置：

    $env:DEEPSEEK_API_KEY = "<轮换后的新密钥>"
    # 不经过桌面启动器时，必须由操作者在当前会话显式授权；默认仍为拒绝
    $env:SRC_AUTO_REMOTE_AI_CONSENT = "enabled"
    $env:SRC_AUTO_DEEPSEEK_CONSENT = "enabled"
    python -m src_auto remote-status

`remote-status` 只显示 `key_present: true/false`，不显示密钥、长度、哈希或请求结果。曾经直接粘贴到聊天中的密钥不能继续使用；请先在 DeepSeek 控制台撤销并创建新密钥。临时环境变量会在会话关闭后失效，DPAPI 加密文件可通过重新运行保存工具进行轮换。

点击 **本地靶场检测** 后，独立终端的提示为“是否启用 DeepSeek V4.1 Flash 远程 AI？输入 Y/是 启用，N/否/回车 禁用”。
选择 `N`、`否` 或回车会设置 `SRC_AUTO_DEEPSEEK_CONSENT=disabled`；即使环境变量中存在
`DEEPSEEK_API_KEY`，也不会发出远程请求。选择 `Y`/`是` 只对当前进程树生效，关闭窗口后不会保存授权。
直接运行 Python 命令时不会额外弹窗；如果没有在当前会话显式设置上述两个 `CONSENT` 变量，
同样保持拒绝。不要把授权变量写入脚本、系统环境变量或配置文件。

当前配置：

| 提供商 | 模型 | 状态 | 用途 |
|---|---|---|---|
| DeepSeek V4.1 Flash | `deepseek-flash` | 已接入、人工启用 | 单次 Finding 审阅，非自动回退 |
| 智谱 GLM-5.3-Flash | `glm-5.3-flash` | 已接入、人工启用 | 单次 Finding 审阅；费用和权限以账户为准 |
| OpenRouter 通用入口 | `openrouter/free`（可编辑） | 已接入、人工启用 | 模型更名时可在平台内更新精确模型 ID |
| OpenAI | `gpt-5.6-luna` | 默认关闭 | 仅保留适配器，等待独立 Platform API 密钥 |

ChatGPT Plus 订阅与 OpenAI Platform API 是两套独立的账户/计费体系，Plus 登录态不能当作 API 密钥，也不使用浏览器 Cookie 自动调用。需要 GPT 时，必须另外创建 Platform API key，再由人工审查后启用配置。

### 12.1.2 预览、摘要确认和单次调用

先完成一次本地运行并查看 Finding：

    python -m src_auto findings --run-id <RUN_ID>

生成远程请求预览。预览只从 SQLite 读取 Finding，不接触网络：

    $preview = python -m src_auto remote-preview --run-id <RUN_ID> --finding-id <FINDING_ID> --provider deepseek --scope config/targets/local-lab/scope_confirmed.yaml | ConvertFrom-Json
    $preview.payload
    $preview.payload_digest

预览中的 URL 会移除查询参数、片段、用户名和密码；证据中的 Authorization、Cookie、Token、Secret、Password 和 API key 会被脱敏。预览还会标明 `network_contact: false`。如果 URL、Scope hash、Finding 关联或提供商状态不满足要求，命令会 fail closed。

确认内容确实是本次要发送的最小观察后，才执行一次人工确认的请求：

    python -m src_auto remote-triage --run-id <RUN_ID> --finding-id <FINDING_ID> --provider deepseek --scope config/targets/local-lab/scope_confirmed.yaml --confirm-external --confirm-digest $preview.payload_digest

发送命令会重新从 SQLite 构造同一 payload 并再次核对摘要；摘要不一致、缺少 `--confirm-external`、STOP 文件存在、密钥缺失、Scope 未确认或 Finding 越界时，不会发出请求。一次命令最多发出一次非流式请求，不自动重试。远程结果只写入 `ai_reviews`，不会覆盖本地 `findings.triage_json`，也不能自动提交补天。

### 12.1.3 成本和数据边界

本版本按你的要求不设置金额上限或调用次数上限。仍保留单次请求 `max_input_tokens: 2000`、`max_output_tokens: 256`，用于控制数据量、延迟和意外长响应；每次响应记录实际 token（若服务返回）和估算美元成本，但不会因累计金额自动阻断。DeepSeek 价格以官方页面为准，配置中的价格只是峰值估算元数据。

远程模型只收到标题、脱敏后的 URL、参数名、严重性、最小证据和“未确认观察”标记，不收到完整响应、Cookie、凭据、用户数据、工具输出或文件。模型意见只能作为人工复核线索，不能证明漏洞存在、扩大授权范围或生成破坏性操作。

### 12.1.4 远程审阅审计

远程意见保存在 SQLite 的 `ai_reviews` 表，包含提供商、模型、payload 摘要、标准化结论、建议检查、token 和估算成本。查看记录：

    python -c "import sqlite3; c=sqlite3.connect(r'D:\网络安全文件夹\SRC-Auto\data\src_auto.sqlite3'); print([dict(r) for r in c.execute('select id,run_id,finding_fingerprint,provider,model,disposition,confidence,input_tokens,output_tokens,estimated_cost_usd,created_at from ai_reviews order by id desc')]); c.close()"

审阅记录与 `spend` 分开，便于在不设置预算上限的前提下做事后核算。不要把输出中的任何密钥或个人数据复制到报告。

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

本地 Ollama 成本按 ¥0 计。远程 DeepSeek 审阅按本项目约定不设置金额上限或调用次数上限；仅执行每次请求的输入/输出 token 限制，并把服务返回的 token 与估算成本写入 `ai_reviews` 供事后查看。远程请求始终需要人工预览、摘要确认和 `--confirm-external`，不会自动回退、自动重试或自动扩大范围。

磁盘、CPU、内存和 STOP 是安全与稳定性控制，不是远程 API 的消费预算。若你希望未来增加预算开关，应先修改设计、测试和操作手册，再启用付费模型。

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

### remote provider_key_missing 或 key_present=false

在当前 PowerShell 会话设置轮换后的环境变量，再重新执行 `remote-status`。不要把密钥写进 `config/models.yaml`、脚本、SQLite 或聊天记录；不要继续使用已经粘贴到聊天中的旧密钥。

### blocked_confirmation 或 blocked_digest

先运行同一 Finding 的 `remote-preview`，完整查看脱敏 payload，再把该次输出的 `payload_digest` 原样传给 `--confirm-digest`，并添加 `--confirm-external`。任何 Finding、Scope、参数或证据变化都会使摘要变化。

### remote_http_401、403、402、429 或 5xx

系统不会自动重试。先检查密钥是否已轮换、账户权限和服务状态，再由人决定是否重新预览并重新确认；不要通过并发或脚本循环规避限制。

### OpenAI provider_disabled

ChatGPT Plus 不是 Platform API 额度。OpenAI 适配器默认关闭，只有在单独拥有 Platform API key、审查数据流和价格后，才可由人工修改配置并进行假响应/小范围验证。

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

1. WSL2/Ubuntu 已安装，但 Ubuntu/WSL 不是本项目的扫描器配置；
2. BBOT 受 Python 版本和 POSIX 环境限制；
3. reconFTW 需要 Linux shell，当前仍未接入或执行；
4. Nuclei 被端点安全软件阻止；
5. 三靶场 ZAP quick scan 已完成三轮控制项裁决，但仍不代表真实漏洞；完整 Juice Shop 官方
   116 条题目 Ground Truth 回归尚未执行；
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
- validation\autotest\LOCAL_LAB_TEST_REPORT.md：三靶场人读最终成绩；
- validation\autotest\LOCAL_LAB_SCORE.json：三靶场机器成绩和 P0 计数；
- validation\autotest\local_regression\LOCAL_REGRESSION_REPORT.md：非破坏性回归人读摘要；
- validation\autotest\local_regression\LOCAL_REGRESSION_SCORE.json：非破坏性回归机器成绩；
- preservation_manifest.sha256：既有文件保护快照。

## 23. OWASP Juice Shop 本地验证

这一节只适用于操作者自己启动的本地 Juice Shop。它不授予任何公网目标权限，
也不会把 Juice Shop 的外链、第三方 API 或子域名加入范围。

### 23.1 固定边界

验证配置：

    config\validation\local_only.json
    config\targets\juice-shop-local\scope_confirmed.yaml

允许主机严格为 `127.0.0.1` 和 `localhost`，允许端口严格为 `3000`、`8081`、`8082`，并发上限为 5。
本地验证配置强制 `AI_PROVIDER=local`、`LOCAL_LLM_ONLY=true`、
`ALLOW_REMOTE_LLM=false`。即使 PowerShell 中存在 `DEEPSEEK_API_KEY`，
`remote-preview` 和 `remote-triage` 也会返回 `blocked_runtime`，不会联网。

### 23.2 启动本地 Juice Shop（当前已完成）

桌面快捷方式指向 `START_SYSTEM.ps1`，双击后先打开图形主菜单；它不会启动 Docker，也不会触碰公网目标。
点击主菜单的 **本地靶场检测** 才会传入 `-RunLocalLab`，随后启动 Docker Desktop（若尚未运行），
通过 `docker-compose.local-labs.yml` 确保 `src-auto-juice-shop`、`src-auto-dvwa`、`src-auto-webgoat`
使用固定镜像摘要、回环端口 `127.0.0.1:3000`/`127.0.0.1:8081`/`127.0.0.1:8082`，等待健康检查，
然后运行三靶场 local-only 验收和安全回归。它不会触碰公网目标，也不会自动提交报告。

如果当前 PowerShell 没有 Docker 路径，先执行：

    Set-Location 'D:\网络安全文件夹\SRC-Auto'
    $env:Path = "$(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin');$env:Path"
    docker version

启动器已验证的手动等价命令（只适用于本机三靶场）：

    docker compose -f docker-compose.local-labs.yml up -d --wait
    python -m src_auto local-labs status --json

容器必须绑定到 loopback；不要改成 `-p 3000:3000` 或绑定公网地址。Docker Desktop 的
程序位置是官方 per-user 默认位置，Docker 镜像、容器和 WSL 虚拟磁盘位于：

    D:\网络安全文件夹\DockerData\wsl

安装器仍保留在 `vendor\docker-installer\Docker Desktop Installer.exe`，SHA-256 为：

    9ac03d4e900c0fdee981d4bde083a55fdfb28ffba2cae77726eff2a437254822

结束本地验证后，如需释放容器资源：

    python -m src_auto local-labs stop

### 23.3 检查和执行基线

先做不启动工具的状态检查：

    python -m src_auto juice-shop-status --human
    python -m src_auto juice-shop-status --url http://localhost:3000/ --human

目标可达时再执行：

    python -m src_auto juice-shop-baseline --human

适配器只做有限 GET、`httpx` 和 `katana` 的表面发现，固定目标 URL，不跟随越界重定向，
不会执行暴力、删除、修改、DoS 或自动提交。结果写入：

    validation\juice-shop\baseline_results.json
    validation\juice-shop\baseline_metrics.json

当前实际基线为 `COMPLETED_DISCOVERY_ONLY`：保留 31 个 loopback URL，排除 15 个外部
URL，只计算 1 次控制层 preflight 请求；因为尚未对 Ground Truth 做人工裁决，
TP/FP/FN、precision、recall、F1 和 scanner-detectable recall 仍保持 `null`。如果
Docker 未安装、容器未启动或 3000 端口拒绝连接，结果会回到 `BLOCKED_DEPENDENCY`，
`Finding=0` 仍不能解读为“没有漏洞”。

### 23.3.1 人工确认的本地 ZAP 快速扫描

基线完成后，如需运行候选漏洞扫描，必须显式确认目标仍是本机靶场：

    python -m src_auto juice-shop-zap --confirm-local --human

命令固定调用项目内的 ZAP 2.17.0 quick scan，只接受已确认的本地回环目标，输出 `POSSIBLE`
候选，不自动复现、不自动提交、不调用远程 AI。当前三轮三靶场验收的候选数为：Juice Shop
`5、4、5`、DVWA `9、8、9`、WebGoat `0、0、0`；数量可能随扫描时序变化。它们可能是安全配置或信息披露
提示，不能直接当作补天漏洞，精确控制项指标请以 `validation/autotest/LOCAL_LAB_SCORE.json` 为准。

ZAP 工件：

    validation\juice-shop\zap_quick_report.json
    validation\juice-shop\zap_findings.json

人工复核每个候选时，只能在授权的本地靶场做最小、无破坏性的验证，记录请求、响应、
影响和复现条件；真实 SRC 目标必须重新建立平台 Scope，不能沿用本地 Scope。

### 23.3.2 输出模式和中文摘要

交互式终端会优先显示简体中文摘要；脚本管道和 `--json` 保持机器可读 JSON。需要把
结果交给 `ConvertFrom-Json` 或其他程序时，显式使用：

    python -m src_auto juice-shop-status --json
    python -m src_auto juice-shop-baseline --json
    python -m src_auto juice-shop-zap --confirm-local --json

JSON 中原有的 `status`、`reason`、`network_contact`、`finding_count` 等英文字段不变，
新运行会在适用时增加 `status_zh`、`reason_zh`。这两个字段只是解释，不改变安全决策。

### 23.4 Ground Truth 和回归

Ground Truth 来自官方 Juice Shop `data/static/challenges.yml` 的元数据，只用于扫描后
比对，不包含题目提示、payload 或解法：

    validation\juice-shop\ground_truth.json
    validation\juice-shop\schema.json

本版本会记录挑战总数、保守可检测数、业务逻辑/认证分类，但不会自动把题目当作 Finding。
只有成功的同一目标基线之后，才可以再运行相同序列并填写：

    validation\juice-shop\regression_results.json
    validation\juice-shop\regression_metrics.json

当前文件仍明确标记为 `NOT_RUN`，原因是 ZAP 候选尚未完成 Ground Truth 的人工裁决；
这不表示本地基线失败，也不表示检测器没有漏洞。

完整结果见：

    JUICE_SHOP_VALIDATION_REPORT.md

阶段分析工件：

    validation\juice-shop\BASELINE_ANALYSIS.md
    validation\juice-shop\REGRESSION_ANALYSIS.md
    validation\juice-shop\FALSE_POSITIVES.md
    validation\juice-shop\FALSE_NEGATIVES.md
    validation\juice-shop\DISCOVERY_REPORT.md
    validation\juice-shop\VERIFICATION_REPORT.md
    validation\juice-shop\AUTH_SESSION_REPORT.md
    validation\juice-shop\MATURITY_ASSESSMENT.md
    validation\juice-shop\validation_checkpoint.json

如果 Docker 不可用，这些文件必须显示 `BLOCKED_DEPENDENCY`、`NOT_RUN` 或
`NOT_TESTED`；当前 Docker 已可用，但 ZAP 候选仍是 `POSSIBLE`，不能被解释为扫描
通过、漏洞成立或漏洞不存在。

### 23.5 一次性执行本机验收计划

当前三靶场控制项 canonical 入口为：

    python tools/run_local_lab_validation.py --local-only --repeat-rounds 2

脚本只允许 `http://127.0.0.1:3000/`、`http://127.0.0.1:8081/login.php` 和
`http://127.0.0.1:8082/WebGoat/actuator/health`，重置三个应用服务后
等待健康状态；不会访问外部 URL，也不会发送远程 AI 请求。所有工件写到：

    validation\autotest\

重点文件为 `LOCAL_LAB_TEST_REPORT.md`、`LOCAL_LAB_SCORE.json` 和
`local_labs/<lab>/round_nn/`。如果某轮 ZAP 未完成，报告会写 `NOT_TESTED`，不会复制或解释
上一次的旧 Finding；完整官方挑战 Ground Truth 未执行时，官方 Precision/Recall/FN 保持
`null`。旧版 `run_autonomous_validation.py` 仅为 Juice Shop 历史兼容入口，不作为本轮三靶场
成绩来源。

### 23.6 非破坏性安全回归

控制项验收完成后，可运行独立回归矩阵：

    python tools/run_local_regression.py --local-only --repeat-rounds 2 --json

它执行 6 个固定用例：Juice Shop 公开首页；DVWA 未登录 SQLi 边界、登录后 SQLi 页面、普通文本
反射标记；WebGoat 未登录课程边界、随机合成账号登录后课程入口。三轮共 18 次执行，当前
`18/18` 通过（`pass_rate=1.000000`）。每个用例只记录 HTTP 状态、响应长度、SHA-256、脱敏头和
断言结果；不记录正文、Cookie、Token 或密码，不执行脚本、命令、上传、修改密码、盲注或 DoS。

机器结果：`validation\\autotest\\local_regression\\LOCAL_REGRESSION_SCORE.json`；人读结果：
`validation\\autotest\\local_regression\\LOCAL_REGRESSION_REPORT.md`。回归通过不等于漏洞确认，
也不会把任何 Finding 标记为 `submission_ready`。

# SRC-Auto

一个面向补天 SRC 的低成本、CPU 友好、人工确认门控控制层。V1 的目标不是“扫描数量”，而是缩短人工复核时间、降低误报和重复、形成最小证据，并让每一个真实目标请求都可审计、可停止、可恢复。

完整中文使用手册：`USER_MANUAL.md`

OpenRouter 模型下架、更名或密钥设置问题：见 [密钥与模型设置说明](docs/OPENROUTER_SETTINGS.md)。新版 Dashboard 的「系统设置」可打开原生密钥与模型设置窗口。

> **当前发布基线（2026-08-28）：** 请先阅读 [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md) 与 [TEST_REPORT.md](TEST_REPORT.md) 顶部的本轮验收。当前版本为 `v0.8.28-loopback-lab-control`；本仓库中早于该日期并标注为“历史”的说明仅供追溯，不覆盖当前功能或测试结论。

## 三期严格计划状态（2026-08-26，历史实施记录）

本轮按已批准的三期计划完成了代码、控制台和本地证据链的升级：

- 完整 Python 测试：`238/238` 通过；12 个项目 PowerShell 脚本解析通过，关键中文脚本均为 UTF-8 BOM。
- 本地靶场从四个扩展为五个：新增确定性的 `business-api`（`127.0.0.1:8084`），仅 GET/HEAD、合成订单、对象授权矩阵和 OpenAPI 契约均受回环门控。
- 业务 API 进程内矩阵已实际完成：`candidate_broken_object_authorization` 仅作为候选，`confirmed=false`、`manual_review_required=true`、`raw_bodies_retained=false`；证据见 `validation/business-api/matrix_unit.json`。
- 三期蓝队入口已加入资产登记、授权待确认、防护计划、JSONL 日志脱敏统计和建议型报告；示例证据见 `validation/defense/`，不联网、不自动处置。
- 桌面控制台已接入 Figma V2 信息架构：工作台、本地靶场、目标与授权、会话与任务、代理与 API 复核、发现与报告、蓝队被动分析、AI 与工具、审计与设置；审计页的“请求停止”按钮会在项目根写入 `STOP` 标记并关闭窗口。视觉对照与本机截图见 `docs/design/src-auto-main-console-fidelity.md` 和 `validation/gui/`。
- Docker Desktop 已恢复，五个靶场本轮均为 `READY`；三轮本地验收为 `AUTHORIZED_LOCAL_VALIDATION_READY`，独立回归为 `30/30` 通过。此前 Docker 不可用的阻断过程和修复后的证据保存在 `validation/business-api/DOCKER_RUNTIME_BLOCKER.md` 与 `validation/autotest/`。
- 远程 AI、真实目标接触和自动提交均为 `0`。选择启动提示中的“否”时，本次会话不会调用远程 AI；补天报告仍由人工复现、编辑和提交。

> **发布内容说明：** 当前仓库只提交源码、配置、文档、测试和两张静态 Dashboard 验收截图。`vendor/bin` 下的五个 `.cmd` 包装脚本作为源码保留，但工具二进制、扫描缓存、ZAP 会话、`validation/` 下的运行工件、DPAPI 密文、API 密钥和会话资料均不上传；它们不属于可复现的发布基线。详见 [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md)。

## 历史本地四靶场验收（2026-08-24）

本机已经建立并固定了四个只供授权测试使用的回环靶场：OWASP Juice Shop（`127.0.0.1:3000`）、DVWA（`127.0.0.1:8081`）、OWASP WebGoat（`127.0.0.1:8082`）和 VAmPI（`127.0.0.1:8083`）。四个应用镜像均为 pinned digest、仅绑定回环地址，并完成最新 local-only 验收；DVWA 额外使用同一 Compose 内的无宿主端口 MariaDB 初始化数据库。逐轮验证工件会在本机运行时生成，出于隐私、体积和可复现性考虑不提交到仓库；指标摘要保留在本说明和 `TEST_REPORT.md` 中。

| 靶场 | 每轮候选数 | 最新轮 Precision / Recall / F1 | 说明 |
|---|---:|---:|---|
| DVWA | 9、8、9 | 0.875000 / 1.000000 / 0.933333 | 7 个控制项真阳性、1 个信息型误报、2 个未验证 |
| Juice Shop | 5、4、5 | 0.200000 / 1.000000 / 0.333333 | 1 个 CSP 控制项真阳性、4 个非赏金信息项 |
| WebGoat | 0、0、0 | 1.000000 / 1.000000 / 1.000000 | 1 个本地健康面控制项；不代表漏洞 |
| VAmPI | 0 | 1.000000 / 1.000000 / 1.000000 | 只读 OpenAPI 契约控制项；不代表漏洞 |

这些是本地控制项/表面发现基准，不是补天赏金漏洞命中率；四个靶场 `bounty_ready_count=0`，没有自动提交。官方 Juice Shop 116 条题目元数据（其中 67 条标记为 scanner-detectable）尚未做完整挑战回归，官方 Ground Truth Precision/Recall 保持 `null`/`NOT_TESTED`。

独立的非破坏性安全回归已在本机执行；运行生成的报告和机器分数保留在本地 `validation/` 目录，默认不提交到 GitHub。

本轮安全计数为：`scope_escape=0`、`external_targets_contacted=0`、`remote_ai_calls=0`、`secret_leakage=0`、`crash=0`。远程 AI 未调用；人工启用 DeepSeek 的路径仍与本地发现流程隔离。

靶场采用成熟的 OWASP/官方项目，而不是重新编写脆弱应用： [Juice Shop 官方仓库](https://github.com/juice-shop/juice-shop)、[DVWA 官方仓库](https://github.com/digininja/DVWA) 和 [WebGoat 官方仓库](https://github.com/WebGoat/WebGoat)。项目只引用固定镜像 digest，并把端口发布限制在本机回环；这些上游项目的“故意脆弱”属性只用于本地训练，不构成任何真实目标授权。

## 可运行状态记录（2026-08-26，历史基线）

本机回环靶场已经完成真实启动和五靶场验证：WSL2 2.7.12、Ubuntu 和 Docker Desktop
4.87.0 已安装，Docker 镜像/容器数据位于 `D:\网络安全文件夹\DockerData`，项目和
验证工件仍全部位于 `D:\网络安全文件夹\SRC-Auto`。Docker Desktop 程序本身按官方
per-user 安装方式保留在用户目录，这是系统组件例外；不代表项目数据写回 C 盘。

五个应用容器只映射到 `127.0.0.1`，数据库不发布宿主端口，不监听公网或局域网地址。远程 AI 仍为 0 调用；本地
Ollama 只有在人工启动或桌面启动器发现它可用时才参与本地分诊。ZAP 结果必须人工复核，
`POSSIBLE` 不等于已确认漏洞，也不会自动提交补天。

启动器已保留 UTF-8 BOM，并关闭 Windows PowerShell 的进度流重绘，因此不会再用
`0......` 进度行覆盖中文提示。启动器顶部仍设置“仅本机回环靶场”，桌面快捷方式不会进入
真实目标流程。

桌面快捷方式现在默认打开简体中文 WinForms 主菜单，而不是直接启动靶场。主菜单提供“本地靶场检测”、
“新建授权目标”、“选择已有目标”、“离线审阅目标范围”、“查看 Findings 和报告”和“AI 模型与密钥设置”。
其中目标录入表单会校验 HTTPS、允许主机、排除主机和端口，并把配置限制写入
`config\targets\<target_id>\`；“保存并离线审阅”只调用本地 `target-review`，不会发出网络请求。
只有点击“本地靶场检测”才会显式传入 `-RunLocalLab` 执行本机五靶场流程。

“选择已有目标”和“离线审阅目标范围”现在打开文件夹优先选择器。路径框允许直接粘贴
`config\targets` 内的上级分组目录，也可使用“项目目标根”“上一级”“选择文件夹”和“刷新”。
程序会递归列出该目录下的 Scope：同时存在 `scope_confirmed.yaml` 和 `live_plan.yaml` 的项目可勾选审阅；
候选 Scope 或缺少计划的项目会标灰并说明原因。多个目标始终逐个运行现有离线审阅逻辑，不合并授权范围，
结果汇总保存在 `reports\offline-review\`，其中固定记录 `network_contact=false`。

“查看 Findings 和报告”使用双栏只读浏览器：左侧列出项目内 `reports` 与 `validation` 摘要，
单击文件名后在右侧显示详细内容；预览不会执行 HTML、链接或脚本，超过 1 MB 的文件会提示改看摘要，
避免大型扫描工件阻塞界面。

## 代码优先可视化控制台

本次可视化升级新增 `dashboard/` React + Vite 控制台。它使用脱敏的本地夹具展示
概览、五靶场状态、任务进度、事件详情、授权目标草稿、候选 Finding 和只读报告；页面上的
暂停/继续/停止、事件选择、草稿保存和报告预览均为真实可点击交互。当前版本仍不访问真实目标、
不启动靶场、不调用远程 AI，也不把输入域名当成授权。

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
.\tools\start_dashboard.ps1
# 或从统一入口显式启动：
.\START_SYSTEM.ps1 -Dashboard
```

启动器只监听 `127.0.0.1`，服务就绪后打开浏览器；`-NoBrowser` 可关闭自动打开。旧 WinForms
主菜单仍是无参数默认入口，`-LegacyGui` 可显式选择旧界面，`-RunLocalLab` 仍只启动五个回环靶场流程。
Dashboard 的 Storybook、单元测试、Playwright 浏览器验收和截图记录见
`docs/validation/visual-upgrade-2026-08-26.md`，部署/恢复方式见 `docs/部署与恢复手册.md`。

## 简体中文界面与输出模式

交互式 PowerShell 中默认显示简体中文摘要，例如“可访问”“依赖不可用”“需要人工复核”。
为了兼容现有脚本，状态码、原因码、URL、路径、模型名和 SHA-256 等机器字段仍保持英文。
JSON 工件会在适用时增加 `status_zh`、`reason_zh` 等中文说明字段，不重命名原字段。

可以显式选择输出模式：

```powershell
# 给人看的简体中文摘要
python -m src_auto juice-shop-status --human

# 给脚本读取的稳定 JSON
python -m src_auto juice-shop-status --json
```

未指定模式时，连接交互式终端会使用中文摘要；通过管道或被脚本捕获时自动使用 JSON。
桌面启动器对需要 `ConvertFrom-Json` 的内部命令显式使用 `--json`，不会被中文提示打断。
如果旧版终端出现中文乱码，可先设置 `$env:PYTHONIOENCODING = "utf-8"`；这只影响显示，
不改变安全策略或机器字段。

## 快速开始（本地靶场）

在 PowerShell 中：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m unittest discover -s tests -v
python -m src_auto new --target-id local-lab --scope config/targets/local-lab/scope_confirmed.yaml --mode local
# 将上一步输出的 run_id 代入下一行
python -m src_auto run --run-id <RUN_ID> --scope config/targets/local-lab/scope_confirmed.yaml --local-lab
python -m src_auto findings --run-id <RUN_ID>
python -m src_auto reports
```

也可使用 `START.bat`、`STOP.bat`、`STATUS.bat`；它们不会创建开机自启动或后台任务。

## 本地靶场生命周期与最终验收（仅 loopback）

Compose 文件 [`docker-compose.local-labs.yml`](docker-compose.local-labs.yml) 定义已知的
Juice Shop、DVWA、DVWA MariaDB 和 WebGoat 服务；镜像摘要、健康检查、资源上限和回环端口都在 D 盘配置中固定。

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m src_auto local-labs status --json
python -m src_auto local-labs start
python -m src_auto local-labs reset --lab juice-shop
python -m src_auto local-validation --local-only --repeat-rounds 2
python tools/run_local_lab_validation.py --local-only --repeat-rounds 2
python -m src_auto local-regression --local-only --repeat-rounds 2 --json
python tools/run_local_regression.py --local-only --repeat-rounds 2 --json
python -m src_auto local-labs stop
```

`local-validation` 和脚本入口等价；`local-regression` 是独立的非破坏性回归入口；`repeat-rounds 2` 表示额外重复 2 次，总计 3 轮。每轮
先重置服务，再做有限静态发现、ZAP quick scan 和人工规则裁决。本机工件写入
`validation/autotest/local_labs/<lab>/round_nn/`，回归证据写入 `validation/autotest/local_regression/`；这些运行产物默认由 Git 忽略。桌面菜单只有在人工点击“本地靶场检测”后才调用四靶场启动、控制项验收和安全回归流程。

Docker Desktop Windows 本机对 `internal: true` 网络中的已发布端口处理为宿主不可达，因此
Compose 使用普通 bridge 网络；宿主 RuntimePolicy、ScopeGuard、发现器和 ZAP 仍强制只允许
`127.0.0.1:3000/8081/8082`。这保证了本机可测，同时不把网络权限扩展到公网或局域网。

## 非破坏性安全回归（推荐先运行）

回归层和 ZAP 控制项评分分开：它不发送 SQL 注入、命令注入、脚本、文件上传或密码修改
payload，只验证可达性、登录边界、登录后训练页面和普通文本标记反射。DVWA 的 MariaDB
初始化和 WebGoat 的随机合成账号都在本机临时会话中完成，Cookie、Token、密码和响应正文不写入
工件；所有 HTTP 请求在发送前通过 `RuntimePolicy`，且不跟随重定向。

```powershell
python tools/run_local_regression.py --local-only --repeat-rounds 2 --json
# 只跑一个靶场或一个用例
python -m src_auto local-regression --local-only --lab dvwa --case dvwa-auth-boundary --json
```

历史本机回归结果为 18/18 次通过，`pass_rate=1.000000`；这只是回归通过率，不是漏洞检测准确率，
也不会产生 `submission_ready` 或自动提交。逐用例摘要、机器结果和 SHA-256 证据在本机运行时写入
`validation/autotest/local_regression/` 与各靶场的 `round_nn` 目录，默认不提交到仓库。

## 本地 OWASP Juice Shop 验证（仅 loopback）

下面的单靶场命令用于兼容 Juice Shop 历史工件；五靶场最终验收请使用上一节的
`local-validation` 入口。此分支只允许 `127.0.0.1`/`localhost:3000`，并强制使用本地 Ollama；
它不会访问公网、不会扩展外链，也不会启用远程 AI。当前 Docker Desktop 已由启动器管理，若
当前 PowerShell 没有 Docker 路径，先执行下面的 PATH 设置：

```powershell
$env:Path = "C:\Users\lenovo\AppData\Local\Programs\DockerDesktop\resources\bin;$env:Path"
docker version
python -m src_auto juice-shop-status --human
python -m src_auto juice-shop-baseline --human
python -m src_auto juice-shop-zap --confirm-local --human
```

`START_SYSTEM.ps1`（桌面快捷方式指向它）会在需要时启动 Docker Desktop，通过固定 Compose
启动五靶场并等待五个回环端口健康；以下命令只对 Juice Shop 历史单靶场工件运行基线。
`juice-shop-zap --confirm-local` 是单独的人工确认步骤，只允许这个 loopback 目标，输出
`POSSIBLE` 候选并等待人工复核。结果位于本机 `validation/juice-shop/`；如果依赖再次不可用，命令会输出
`BLOCKED_DEPENDENCY`，不会把未执行扫描算作通过。

## 人工启用的 DeepSeek V4 Flash 审阅

DeepSeek 只审阅已经落库的单个 Finding，不参与自动发现或自动回退。桌面一键启动每次都会先询问是否启用；选择否时设置会话级硬门 `remote_ai_disabled_for_session`，本次进程树不会发出远程请求。选择是也只允许人工 `remote-triage`，不会自动调用。API key 明文只存在于当前进程；项目可选择保存当前 Windows 用户绑定的 DPAPI 密文：

推荐先运行一次 DPAPI 隐藏保存工具；它只在指定 D 盘项目内生成当前 Windows 用户可解密的密文，并被 Git 排除：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\save_deepseek_key.ps1
```

以后启动时选择“是”会自动加载，选择“否”不会读取或解密。若不希望保存，也可以继续使用下面的当前会话环境变量方式：

```powershell
$env:DEEPSEEK_API_KEY = "<轮换后的新密钥>"
# 如果不通过桌面启动器，必须在当前 PowerShell 会话显式授权；默认仍是拒绝
$env:SRC_AUTO_REMOTE_AI_CONSENT = "enabled"
$env:SRC_AUTO_DEEPSEEK_CONSENT = "enabled"
python -m src_auto remote-status
$preview = python -m src_auto remote-preview --run-id <RUN_ID> --finding-id <FINDING_ID> --provider deepseek --scope config/targets/local-lab/scope_confirmed.yaml --json | ConvertFrom-Json
python -m src_auto remote-triage --run-id <RUN_ID> --finding-id <FINDING_ID> --provider deepseek --scope config/targets/local-lab/scope_confirmed.yaml --confirm-external --confirm-digest $preview.payload_digest
```

直接双击桌面快捷方式时，启动窗口会显示：

```text
是否启用 DeepSeek v4 Flash 远程 AI？输入 Y/是 启用，N/否/回车 禁用
```

选择 `N`、`否` 或直接回车会把 `SRC_AUTO_DEEPSEEK_CONSENT` 设为 `disabled`；即使
`DEEPSEEK_API_KEY` 存在，Provider 也会在建连前返回 `remote_ai_disabled_for_session`。
选择 `Y`/`是` 时只在当前启动进程树中临时允许 DeepSeek，关闭窗口后不会保存授权。
直接运行 Python 命令而不经过启动器时，不会弹出询问，且默认拒绝；只有操作者在当前会话
明确设置上面的两个 `CONSENT` 环境变量，才会打开同一硬门。不要把这两个变量写入脚本、
系统环境变量或配置文件。

`remote-preview` 不联网，只输出脱敏 payload 和 SHA-256 摘要；`remote-triage` 会重新构造 payload、再次校验 Scope 和摘要，最多发送一次非流式请求。远程结论写入独立的 `ai_reviews` 表，不会自动确认漏洞或提交补天。按照当前设计不设置金额或调用次数上限，只保留每次请求的输入/输出 token 限制并记录估算成本。

你在聊天中粘贴过的 key 已经暴露，实际联调前必须在 DeepSeek 控制台撤销并换新。ChatGPT Plus 登录态也不能作为 OpenAI API key；OpenAI 适配器默认关闭，需独立 Platform API key 和人工审查后再启用。

## 真实 SRC 的唯一人工步骤

把平台规则、测试时间、允许的根域/主机/端口、排除项和授权来源写入独立的 `scope_confirmed.yaml`，由人复核后将 `confirmed` 和 `allow_network_contact` 都设为 `true`。候选文件不能直接升级权限。之后仍需人工查看候选报告并在补天平台手动提交。

### 人工选择非本地目标（只审阅、不联网）

如果确实有平台授权的非本地目标，先用 `target-review` 手动选择并预览范围。它只读取项目根目录内的 Scope/人工计划，逐个调用 `ScopeGuard`，不启动 httpx、Katana、ZAP 或任何远程请求：

```powershell
python -m src_auto target-review `
  --scope config/targets/<id>/scope_confirmed.yaml `
  --plan config/live_plan.example.yaml `
  --human

# 人工看完目标主机、端口、Scope/计划摘要后，才确认“选择”这一步
python -m src_auto target-review `
  --scope config/targets/<id>/scope_confirmed.yaml `
  --plan config/live_plan.example.yaml `
  --confirm-selection --human
```

这一步返回 `awaiting_selection` 或 `selection_reviewed`，不等于执行授权；真正可能启动外部适配器的唯一入口仍是 `run-live --execute-live`，还必须同时通过 `allow_real_targets`、确认 Scope 和 `manual_execution_confirmed` 三道门。测试阶段对非本地 URL 只做 mock/离线审阅，不实际访问。

### 执行本机自动化验收计划

旧版单靶场编排器仍保留用于兼容历史工件；当前五靶场验收以 `run_local_lab_validation.py` 的本机输出为准。重复轮次会在重置后等待回环 HTTP 200，不会把旧 ZAP 工件当成新结果：

```powershell
python tools/run_autonomous_validation.py --local-only --repeat-rounds 2
```

本机生成的报告位于 `validation/autotest/`，包括 `LOCAL_LAB_TEST_REPORT.md`、`LOCAL_LAB_SCORE.json` 和
`local_labs/<lab>/round_nn/`；该目录被 Git 忽略。没有完整 Ground Truth 或人工裁决的指标保持 `null`/`NOT_TESTED`；
`AUTHORIZED_LOCAL_VALIDATION_READY` 只表示本地流程和安全门控完成，不代表已发现可获赏漏洞，
也不代表 `AUTHORIZED_PILOT_READY`。

## 受控外部计划（默认关闭）

外部适配器现在可以通过 `config/live_plan.example.yaml` 这一类人工审阅计划进入命令行，但 `config/policy.yaml` 的 `network.allow_real_targets` 默认是 `false`。只有在当前平台规则、授权来源、时间窗口和 Scope 都经人工核对后，才可以复制示例计划、填写目标和参数，并显式打开策略开关；每次执行仍需 `--execute-live`。桌面一键启动器永远只运行 local-lab。

```powershell
python -m src_auto run-live --run-id <REAL_RUN_ID> --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml
python -m src_auto run-live --run-id <REAL_RUN_ID> --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml --execute-live
```

第一条命令只做计划和策略检查；第二条才可能启动已列入计划的工具。计划不会自动发现目标、扩大 Scope 或提交补天报告。

## 重要限制

Nuclei 仍被端点安全软件阻止执行，BBOT/reconFTW 仍受 Windows/Python/Linux 运行环境限制；
不得关闭安全软件绕过。外部工具的安装、版本和平台规则见 `tools.lock.yaml`、
`IMPLEMENTATION_REPORT.md` 与 `KNOWN_ISSUES.md`。本地 ZAP 候选只能作为人工复核线索，
不保证漏洞成立、补天受理或获得赏金。

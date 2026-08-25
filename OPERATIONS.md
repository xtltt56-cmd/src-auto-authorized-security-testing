# 运维和操作速查

> 当前三期验收与图形界面说明以 [`docs/THREE_PHASE_USER_MANUAL.md`](docs/THREE_PHASE_USER_MANUAL.md) 和 [`docs/THREE_PHASE_UPGRADE_REPORT.md`](docs/THREE_PHASE_UPGRADE_REPORT.md) 为准；本页中的历史“三靶场”段落仅用于兼容旧命令。

## 第一次本地运行

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
$env:PYTHONIOENCODING = "utf-8"
python -m unittest discover -s tests -v
$json = python -m src_auto new --target-id local-lab --scope config/targets/local-lab/scope_confirmed.yaml --mode local --json
$run = ($json | ConvertFrom-Json).run_id
python -m src_auto run --run-id $run --scope config/targets/local-lab/scope_confirmed.yaml --local-lab --human
python -m src_auto findings --run-id $run --human
python -m src_auto reports --human
```

交互式终端默认显示简体中文；脚本管道和 `--json` 输出稳定的机器字段。`START.bat RUN_ID`
执行同样的前台本地流程，不会创建计划任务、服务、开机启动项或后台工作进程。

桌面快捷方式指向 `START_SYSTEM.ps1`，默认打开简体中文图形主菜单，不会启动 Docker 或访问目标。
点击“本地靶场检测”后才会以 `-RunLocalLab` 手动启动本地 Ollama 和 Docker Desktop，运行
local-lab 流程并显示 Findings/报告；永远不会进入真实目标流程。点击“新建授权目标”可录入补天项目
的 HTTPS 起始地址、允许/排除主机、端口和授权确认，并先生成草稿或进行离线 `target-review`。

启动器使用 UTF-8 BOM 兼容 Windows PowerShell 5.1，并设置
`$ProgressPreference = 'SilentlyContinue'`，避免 `Invoke-WebRequest` 的 `0......` 进度重绘覆盖中文文字。

## 人工启用远程 AI 审阅

DeepSeek V4 Flash 只审阅一个已经存在的 Finding，不参与自动发现或外部目标发现。桌面一键启动
每次先询问是否启用；选择否会在本次进程树设置 `SRC_AUTO_DEEPSEEK_CONSENT=disabled`，任何
远程 Provider 在建连前都返回 `remote_ai_disabled_for_session`。选择是也只开放人工
`remote-triage`，不会在本地一键启动中自动调用。OpenAI Responses provider 已保留但默认关闭。

推荐用一次性隐藏输入工具把已经轮换的新 Key 保存为当前用户 DPAPI 密文：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\save_deepseek_key.ps1
```

密文固定放在 `config\secrets\deepseek_api_key.dpapi` 并被 Git 排除。启动器选择“是”时才会
读取和解密；选择“否”时不读取、不解密、不调用。DPAPI 文件绑定当前电脑和当前 Windows 用户。

如果不希望保存，也可以只在当前 PowerShell 进程中设置；不要把明文 Key 写入脚本、SQLite、报告
或 Git：

```powershell
$env:DEEPSEEK_API_KEY = "<轮换后的新密钥>"
# 不经过桌面启动器时，必须显式授权本次 PowerShell 会话；默认拒绝
$env:SRC_AUTO_REMOTE_AI_CONSENT = "enabled"
$env:SRC_AUTO_DEEPSEEK_CONSENT = "enabled"
python -m src_auto remote-status --human
```

聊天中粘贴过的 Key 必须先撤销。`remote-status` 不联网，只显示对应环境变量是否非空。
如果选择桌面启动器中的“否”，不要执行上面的授权变量设置；保持启动器写入的
`disabled` 值即可确保本次进程树不会调用远程 API。直接运行 Python 命令没有交互询问，
未显式授权时默认拒绝。

预览和发送流程：

```powershell
$preview = python -m src_auto remote-preview --run-id <RUN_ID> --finding-id <FINDING_ID> --provider deepseek --scope config/targets/local-lab/scope_confirmed.yaml --json | ConvertFrom-Json
$preview.payload_digest
python -m src_auto remote-triage --run-id <RUN_ID> --finding-id <FINDING_ID> --provider deepseek --scope config/targets/local-lab/scope_confirmed.yaml --confirm-external --confirm-digest $preview.payload_digest --human
```

预览不联网，会去掉 URL 查询参数、片段、凭据和疑似密钥证据。发送命令会重新构造相同
payload，要求摘要完全匹配，检查 Scope 和 STOP 标记，最多发送一次非流式请求。不自动重试，
不自动回退；审阅写入独立的 `ai_reviews`，不会覆盖本地 Finding 状态。

远程审阅按设计没有金额或调用次数上限，但每次请求仍受 `2000` 输入 token、`256` 输出 token
限制，并记录使用量和估算成本。这不等于允许测试目标或向补天自动提交。

## STOP 和 RESUME

```powershell
STOP.bat RUN_ID
STATUS.bat --run-id RUN_ID --human
START.bat RUN_ID       # 看到 STOP 标记后保持停止
python -m src_auto resume --run-id RUN_ID --scope config/targets/local-lab/scope_confirmed.yaml --local-lab --human
```

只有 `resume` 会清除停止标记。进程中断后，SQLite 检查点和运行状态仍可查看。

## 工具状态

```powershell
python -m src_auto tool-status --human
```

该命令只验证版本和可用性。ProjectDiscovery 工具位于 `vendor\bin`，ZAP 位于 `vendor\zap`。
`unavailable` 或 `error` 是真实限制，不会被伪装成靶场结果。

## 本地 Juice Shop 流程

```powershell
python -m src_auto juice-shop-status --human
python -m src_auto juice-shop-baseline --human
python -m src_auto juice-shop-zap --confirm-local --human
```

目标严格为 `127.0.0.1:3000`/`localhost:3000`。基线只做 bounded preflight、httpx/katana
表面发现；ZAP 必须显式确认本机后运行，结果为 `POSSIBLE` 时必须人工复核。工件位于：

```text
D:\网络安全文件夹\SRC-Auto\validation\juice-shop
```

## 四靶场最终验收（当前 canonical 流程）

四个固定应用镜像由 `docker-compose.local-labs.yml` 管理，服务只发布到回环地址：Juice Shop
`127.0.0.1:3000`、DVWA `127.0.0.1:8081`、WebGoat `127.0.0.1:8082`、VAmPI
`127.0.0.1:8083`。DVWA 的 MariaDB
只在 Compose 网络内提供 `3306`，不发布宿主端口。生命周期和验证命令：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m src_auto local-labs status --json
foreach($lab in @('juice-shop','dvwa','webgoat','vampi')){ python -m src_auto local-labs start --lab $lab --human }
python -m src_auto local-validation --local-only --repeat-rounds 2
# 或：python tools/run_local_lab_validation.py --local-only --repeat-rounds 2
python -m src_auto local-regression --local-only --repeat-rounds 2 --json
# 或：python tools/run_local_regression.py --local-only --repeat-rounds 2 --json
foreach($lab in @('juice-shop','dvwa','webgoat','vampi')){ python -m src_auto local-labs stop --lab $lab --human }
```

`repeat-rounds 2` 表示每个靶场总计 3 轮。最终人读报告为
`validation\autotest\LOCAL_LAB_TEST_REPORT.md`，机器结果为
`validation\autotest\LOCAL_LAB_SCORE.json`，每轮文件位于
`validation\autotest\local_labs\<lab>\round_nn\`。

最终成绩（最新轮）见 `LOCAL_LAB_SCORE.json`：DVWA、Juice Shop、WebGoat 和 VAmPI 的 Precision /
Recall / F1 是本地控制项/表面发现基准，不是赏金漏洞评分；所有靶场
`bounty_ready_count=0`。独立回归最新结果为 2 轮、14/14 通过（`pass_rate=1.000000`），
见 `local_regression/LOCAL_REGRESSION_SCORE.json`。

四个应用靶场均为 `healthy`，HTTP 200；P0 安全计数均为 0：未越界、未接触外部目标、未调用远程
AI、未泄露密钥、未崩溃、未自动提交。官方 Juice Shop 116 条题目/67 条 scanner-detectable
元数据的完整 Ground Truth 回归尚未执行，官方 Precision/Recall 保持 `null`。

Windows Docker Desktop 本机对 `internal: true` 网络的已发布端口不可由宿主回环访问，因此
Compose 使用普通 bridge 网络；宿主 RuntimePolicy、ScopeGuard、发现器和 ZAP 仍强制只允许
这四个 `127.0.0.1` 端口。该调整只为本地可测，不扩大网络范围。

## 人工目标选择与外部执行门

对平台明确授权的非本地目标，先把 Scope 和人工计划放在项目根目录内，再做离线预览：

```powershell
python -m src_auto target-review --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml --human
python -m src_auto target-review --scope config/targets/<id>/scope_confirmed.yaml --plan config/live_plan.example.yaml --confirm-selection --human
```

`target-review` 只生成允许/拒绝清单、Scope/计划摘要和下一步提示，`network_contact` 始终为
`false`。确认选择后仍必须由人工检查平台规则，并在真正需要时使用
`run-live --execute-live`；默认 `allow_real_targets: false`、未确认 Scope 或未确认人工计划时
仍会失败关闭。本轮测试不执行任何非本地 URL。

## 旧版单靶场验收（兼容历史工件）

```powershell
python tools/run_autonomous_validation.py --local-only --repeat-rounds 2
```

旧脚本只调用 `127.0.0.1:3000`，仅用于历史工件和兼容性验证；本轮四靶场成绩不来自该脚本。

## 第一个真实 SRC 目标

1. 保存平台当前规则、时间窗口、明确根域/主机/端口、排除项和授权来源；
2. 运行 `python -m src_auto resolve-scope --snapshot <rules.json-or-yaml> --output-dir config\targets\<id>`；
3. 人工复核候选，另建 `scope_confirmed.yaml`，写入 `confirmed: true` 和 `allow_network_contact: true`；
4. 使用 `src_auto new --mode real` 创建运行并检查 Scope 摘要；
5. 复制 `config\live_plan.example.yaml`，填完占位内容，最终复核前保持 `manual_execution_confirmed: false`；
6. 默认 `config\policy.yaml` 的 `network.allow_real_targets` 为 `false`，先运行 dry gate，再由人工决定是否加 `--execute-live`；
7. 查看报告草稿，只有在补天项目规则允许时才人工提交。

桌面快捷方式永远不会进入这条真实目标路径。禁止未授权扫描、越界扩展、暴力破解、修改/删除数据、DoS、持久化、横向移动和批量收集个人信息。

## 数据位置

- SQLite：`data\src_auto.sqlite3`（Git 忽略）；
- 日志/检查点：SQLite 事件和 `logs\`；
- 最小证据：`evidence\<run_id>\`；
- 报告草稿：`reports\<run_id>.md`；
- Juice Shop 验证：`validation\juice-shop\`。
- 四靶场自动化验收：`validation\autotest\LOCAL_LAB_SCORE.json`、
  `validation\autotest\LOCAL_LAB_TEST_REPORT.md` 和 `validation\autotest\local_labs\`（不保存远程
  目标响应或 API 密钥）。

不要提交证据、凭据、Token、Cookie 或数据库文件。

# 测试报告

日期：2026-09-16（Asia/Shanghai）

> **当前开发验收基线：** 本报告顶部的“v0.11.1 Dashboard AI 会话复用修复验收（2026-09-16）”是当前工作区的最新结论；正式发布范围仍以 [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md) 为准。下方所有较早日期的段落均为历史追溯，不覆盖本轮功能、测试数量或运行结论。旧 ZAP 会话、扫描缓存和机器工件继续从 Git 发布内容中排除。

## 工作区稳定性升级验收（待发布，2026-09-17）

本轮针对“重复打开后任务长期显示运行中、关闭服务可能误杀进程、失联页面显示假停止状态、CI 未验证覆盖率”等问题完成了最小必要修复。状态日志采用原子替换和大小/字段校验，恢复只恢复可安全展示的历史元数据，绝不自动恢复任务。

| 检查项 | 实际结果 |
|---|---|
| Python 全量回归 | `327` 项：`326` 通过、`1` 条件跳过、`0` 失败 |
| Dashboard 前端测试 | `41/41` 通过 |
| Dashboard 覆盖率 | 语句 `75.66%`、分支 `75.08%`、函数 `73.25%`、行 `80.40%`；CI 门槛分别为 70/60/65/70 |
| PowerShell 解析 | 项目脚本 `175` 个解析通过 |
| TypeScript、Lint、生产构建 | 均通过；Vite 生产包成功生成 |
| API 真实进程边界 | 自定义允许来源、令牌、项目身份和安全关闭测试通过；Windows 停止脚本不会强制杀进程 |
| 网络接触 | 外部目标 `0`；远程 AI `0`；自动提交 `0` |

本轮不改变 `v0.11.1` 正式发布清单；完成提交、GitHub CI 和发布包验收后，才可把这段升级标记为新的正式版本。

## v0.11.1 Dashboard AI 会话复用修复验收（2026-09-16）

本轮修复重复启动 Dashboard 时可能沿用旧 API 云端 AI 授权状态的问题。健康接口现在公开本机进程 ID 和会话授权布尔值；启动器只复用与本次选择一致的 API。状态缺失或不一致时，会先检查是否存在运行任务，再核验监听进程的命令行确属 `src_auto.dashboard_server`，然后才安全重启；任一步无法确认都会失败关闭。网页服务会被识别并复用，不再重复启动后误报成功。

| 检查项 | 实际结果 |
|---|---|
| Python 全量回归 | `317` 项：`316` 通过、`1` 按环境条件跳过、`0` 失败 |
| 旧版 API 升级路径 | 无授权字段的空闲旧 API 被安全识别并重启为本次选择状态 |
| 同状态重复启动 | API PID 保持不变，确认安全复用 |
| 授权状态切换 | `禁用 → 允许 → 禁用` 均更换 API PID，健康状态依次为 `false → true → false` |
| 网页服务复用 | 现有 `4173` 服务被正确复用，没有重复启动或假成功 |
| 远程 AI 调用 | `0`；验收未执行连接测试 |
| 启动提示 | 已按允许/禁用状态显示准确的网络行为说明 |

## v0.11.0 发布修复验收（2026-09-16）

本轮修复了版本发布号与既有 `v0.10.0` 标签冲突的问题，并为 Dashboard 增加云端 AI 会话硬门。启动 Dashboard 时必须先明确选择是否允许云端 AI；拒绝时 API 进程记录为禁用状态，设置页仍可本地保存密钥，但任何远程连接测试都会被服务端拒绝（`403 remote_ai_disabled_for_session`）。即使浏览器端状态被篡改，服务端也不会解密或发送密钥。

| 检查项 | 实际结果 |
|---|---|
| 发布版本号 | `VERSION=0.11.0`；回退基线为既有 `v0.10.0` |
| Python 全量回归 | `316` 项：`315` 通过、`1` 按环境条件跳过、`0` 失败 |
| Dashboard 前端测试 | `41/41` 通过 |
| TypeScript / Lint / 生产构建 | 均通过 |
| Dashboard AI 硬门 | 拒绝会话的连接测试 `403`，供应商调用次数 `0`；允许会话仍需页面一次性联网确认 |

## Dashboard 真实本地检测工作流验收（2026-09-16）

本轮把固定回环靶场的真实检测执行器接入 Dashboard：操作者必须先人工启动靶场并等待健康状态为“就绪”，再人工点击“开始检测”。后端依次执行固定范围预检、只读可达性探测、有限同源表面发现、被动响应头候选检查、靶场专用业务/API 检查、结果入库和报告生成；停止请求在安全检查点生效。任务进度、计数、运行 ID 和报告 ID 都来自后端执行状态，不由前端定时器伪造。

| 检查项 | 实际结果 |
|---|---|
| Python 全量回归 | `314` 项执行：`313` 通过、`1` 按环境条件跳过、`0` 失败 |
| Dashboard 前端单元测试 | `40/40` 通过 |
| TypeScript / Lint / 生产构建 | 均通过；生产包成功生成 |
| 真实 Socket 集成 | 临时回环 HTTP 服务被实际访问，完成发现、候选入库和报告生成 |
| Chromium 页面闭环 | 页面真实提交 `business-api/start` 与 `business-api/detect`，HTTP 均返回 `202`；任务详情显示 8 个检测阶段、4 个候选和关联报告；控制台错误 `0` |
| 本机 Business API 实机结果 | 最新浏览器运行 `6c52fdd093414abd92cfbd8bb730e8bb` 完成，候选 `4`、错误 `0`；报告为人工复核草稿，靶场在验收后恢复为停止状态 |
| 外部目标 / 远程 AI / 自动提交 | `0 / 0 / 0` |

本轮“候选”只表示固定本地夹具上的最小、非破坏性观察。响应头缺失和对象授权矩阵结果仍需人工复核；它们不是已确认漏洞，不代表补天可提交性或赏金成绩。ZAP/Nuclei 等深度扫描器尚未统一接入此 Dashboard 检测按钮。

## 内置 AI 设置、报告阅读与依赖状态验收（2026-09-15）

本轮修复了 Dashboard 报告只能看到文件名、Docker 未就绪被误写成“靶场被阻止”，以及 AI 密钥必须跳转到密集独立窗口的问题。Dashboard 的 **系统设置** 现已内置 DeepSeek V4.1 Flash、智谱 GLM-5.3-Flash 和 OpenRouter 通用入口；保存操作不联网，连接测试必须由操作者单独勾选一次性许可。本轮自动化测试未调用远程 AI，也未访问任何真实目标。

| 检查项 | 实际结果 |
|---|---|
| Python 全量回归 | `302` 项执行：`301` 通过、`1` 按环境条件跳过、`0` 失败 |
| Dashboard 前端单元测试 | `34/34` 通过 |
| Chromium 真实交互 | `8/8` 通过；含报告内容预览、API 密钥加密保存、设置直达链接和移动端布局 |
| TypeScript / Lint / 生产构建 | 均通过 |
| PowerShell 解析 | 项目入口和 `tools` 脚本全部无语法错误 |
| 密钥行为 | 前端不回显；后端只向固定官方 HTTPS 地址加载对应 DPAPI 密钥；保存不联网 |
| 外部目标 / 远程 AI / 自动提交 | `0 / 0 / 0` |

五靶场健康检查在本轮前置实机验收中为 `5/5 healthy`，并在验收结束后恢复原先停止状态。本轮浏览器夹具刻意模拟 Docker 不可用，以验证页面显示“Docker 尚未就绪”而不是伪造靶场失败。

## 可视化本地靶场控制升级验收（2026-08-28）

本轮只验证本机回环控制和页面交互，没有访问任何真实补天目标，也没有调用远程 AI 或执行自动提交。

| 检查项 | 实际结果 |
|---|---|
| Python 全量回归 | `254/254` 通过 |
| 回环控制服务单元/接口测试 | `10/10` 通过；固定动作、重复操作、令牌、来源、请求大小和未知路由均失败关闭 |
| Dashboard 前端单元测试 | `28/28` 通过；含“启动中”状态文案与五靶场操作控件 |
| Chromium E2E | `7/7` 通过；含移动端五靶场卡片和按钮交互 |
| TypeScript/Lint/生产构建 | 均通过；Vite 仅代理 `/api` 到 `127.0.0.1:4174` |
| 启动器冒烟 | 4173 前端与 4174 API 均就绪，`/health` 正常，会话令牌可读取快照 |
| 真实页面点击 | Chromium 从侧栏进入本地靶场后，已完成 Juice Shop 的“停止 → 启动”闭环；页面状态刷新正常，5 个“打开页面”入口可见，浏览器外部请求 `0`、控制台错误 `0` |
| 外部目标/远程 AI/自动提交 | `0 / 0 / 0` |

本轮开始时 Docker Engine 未运行，已通过本机 Docker Desktop 恢复。随后经同一回环 API 启动全部靶场；当前 Juice Shop、DVWA、WebGoat、VAmPI 和 Business API 均为 `5/5 healthy`，端口只绑定 `127.0.0.1`。这仅证明本地靶场生命周期和页面控制闭环可用，**不代表已自动执行漏洞扫描，也不代表真实补天目标存在漏洞**。
页面冒烟截图：`validation/dashboard/live-lab-controls.png`；真实点击回归截图：`validation/dashboard/live-click-regression.png`。

## 三期严格计划验收（2026-08-26，历史记录）

本节是当前三期升级的有效状态；下方 2026-08-24 及更早内容均为历史记录。当前所有实际网络接触仍限定为固定的 `127.0.0.1` 本地靶场，未访问真实补天目标。

| 项目 | 当前结果 |
|---|---|
| 完整 Python 单元/集成测试 | `238/238` 通过（含报告文件单击预览的真实 WinForms 交互回归） |
| PowerShell 递归解析 | `12/12` 脚本无语法错误；关键中文脚本 UTF-8 BOM 检查通过 |
| Docker Compose 配置 | 通过（`docker compose ... config --quiet` 退出码 0） |
| Docker 引擎与五靶场 | Docker Desktop Linux engine 已恢复；当前 `5/5 READY`，五个健康检查均返回 200 |
| 五靶场本地验收 | `AUTHORIZED_LOCAL_VALIDATION_READY`，`target_count=5`，P0 全部为 0 |
| 五靶场独立回归 | `30/30` 通过（10 个用例 × 3 轮，`pass_rate=1.0`） |
| 业务 API 对象授权矩阵 | 进程内确定性验证完成；仅输出 `candidate_broken_object_authorization`，`confirmed=false`，必须人工复核 |
| 业务 API Docker 回归 | `9/9` 通过（修复 OpenAPI `x-src-auto.lab_id` 断言后） |
| 蓝队被动分析 | 4 条项目内合成 JSONL 事件完成导入、脱敏和聚合；自动处置 `0` |
| 桌面控制台 | 中文导航、目标/授权、会话/API、蓝队、靶场和审计入口的契约测试通过；停止按钮会实际写入项目 `STOP` 标记 |
| 远程 AI / 外部目标 / 自动提交 | `0 / 0 / 0` |

业务 API 使用 `127.0.0.1:8084`，因为原 VAmPI 已占用 `8083`；该端口偏差已同步到 Compose、清单、运行策略、回归用例、GUI 和手册。Figma V2 的信息架构与视觉稿清单保存在 `design/frontend-mockups/2026-08-26-figma-v2/`，界面视觉对照记录和本机截图保存在 `docs/design/src-auto-main-console-fidelity.md` 与 `validation/gui/`；生产界面采用本地 WinForms 实现，设计插件导出额度不足时不阻塞代码验收。

Docker Desktop 恢复后，应在项目目录重新执行：

```powershell
docker compose -f docker-compose.local-labs.yml up -d
python -m src_auto local-labs status --json
python -m src_auto local-validation --local-only --repeat-rounds 2 --json
python -m src_auto local-regression --local-only --repeat-rounds 2 --json
```

上述恢复命令已在 Docker Desktop 恢复后执行并生成当前五靶场工件。若 Docker 再次不可用，必须把状态重新标记为阻断，不得沿用旧成绩。

### 五靶场控制项成绩（2026-08-26，历史记录）

| 靶场 | 候选记录 | TP | FP | FN | 未验证 | Precision | Recall | F1 | 赏金就绪 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 业务 API | 3 | 3 | 0 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 | 0 |
| DVWA | 9 | 6 | 1 | 1 | 2 | 0.857143 | 0.857143 | 0.857143 | 0 |
| Juice Shop | 5 | 1 | 4 | 0 | 0 | 0.200000 | 1.000000 | 0.333333 | 0 |
| VAmPI | 2 | 2 | 0 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 | 0 |
| WebGoat | 1 | 1 | 0 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 | 0 |

这些是本地控制项和表面发现指标，不是漏洞可利用率、补天受理率或赏金收入；所有 `bounty_ready_count` 均为 0。

## 历史最终验收（2026-08-24）

以下是三期升级后最新一次实机结果，所有网络接触均限制在四个 `127.0.0.1` 本地靶场：

| 项目 | 结果 |
|---|---|
| 完整 Python 单元/集成测试 | `219/219` 通过 |
| PowerShell 递归解析和关键脚本 UTF-8 BOM | 通过 |
| 本地靶场 | 4/4 `READY` |
| 本地验收 | `AUTHORIZED_LOCAL_VALIDATION_READY`，P0 全部为 0 |
| 本地回归 | 14/14 通过，`pass_rate=1.0` |
| 远程 AI / 外部目标 / 自动提交 | `0 / 0 / 0` |

本地控制项基准：DVWA `0.875000/1.000000/0.933333`，Juice Shop `0.200000/1.000000/0.333333`，VAmPI `1.000000/1.000000/1.000000`，WebGoat `1.000000/1.000000/1.000000`。这些指标不是补天赏金漏洞命中率；四个靶场的 `bounty_ready_count` 均为 `0`。机器工件见 `validation/autotest/LOCAL_LAB_SCORE.json`，回归工件见 `validation/autotest/local_regression/LOCAL_REGRESSION_SCORE.json`。

以下内容为 2026-08-22 的历史测试记录，保留用于追溯，不覆盖本次最终验收结论。

## 自动化测试

`python -m unittest discover -s tests -v` —— **159 个测试通过，0 个失败**。

本轮三靶场最终验收命令：

```powershell
python tools/run_local_lab_validation.py --local-only --repeat-rounds 2
```

结果：三个应用 pinned-digest 容器均 `healthy`，各完成 3 轮；DVWA、Juice Shop、WebGoat 的
最新 Precision/Recall/F1 以机器工件为准，WebGoat 另有 1 个本地健康面控制项。三个靶场
`bounty_ready_count=0`，P0（scope escape、外部目标接触、远程 AI、密钥泄露、崩溃、自动提交）均为 0。
独立安全回归另有 6 个用例、3 轮共 18 次执行，18/18 通过。机器原始结果见
`validation/autotest/LOCAL_LAB_SCORE.json`，逐轮证据见 `validation/autotest/local_labs/`；回归结果见
`validation/autotest/local_regression/LOCAL_REGRESSION_SCORE.json` 和
`validation/autotest/local_regression/LOCAL_REGRESSION_REPORT.md`。

最新轮控制项指标：DVWA 候选 `9`，Precision/Recall/F1=`0.875000/1.000000/0.933333`；
Juice Shop 候选 `5`，Precision/Recall/F1=`0.200000/1.000000/0.333333`；WebGoat 候选 `0`，
健康面控制项 Precision/Recall/F1=`1.000000/1.000000/1.000000`。三个靶场均
`bounty_ready_count=0`；DVWA 的 2 个未知 ZAP 告警保持 `NOT_VERIFIED`，未被自动升级。

覆盖范围包括：

- 精确主机/子域名允许、排除项/第三方/默认拒绝、非法 URL/端口和越界重定向；
- 候选 Scope 不能授予权限；
- SQLite 运行、检查点、资产基线和增量差异；
- 稳定 Finding 指纹、去重以及每次运行的历史关联；
- 日/月预算门控、磁盘 80/90 GiB 模拟、资源暂停和人工 STOP/RESUME；
- Ollama JSON Provider、密钥/查询脱敏、模型输出校验和确定性启发式回退；
- SQLite 支出/提交审计持久化和一键启动器安全契约；
- 外部计划结构校验、Shell/危险参数拒绝、自定义序列/参数转发和默认实时策略门控；
- 越界适配器在进程启动前拒绝，以及缺少工具时的显式状态；
- 外部序列要求显式 `execute=True`，并在工具前后遵守人工 STOP 标记；
- 回环 HTTP 服务、流水线顺序、最小证据和人工补天报告草稿；
- DeepSeek V4 Flash 假传输、脱敏请求和稳定摘要；
- OpenAI Responses 假传输（`store: false`、无工具、严格 JSON Schema）；
- `remote-status`/`remote-preview` 的无网络行为、摘要/确认门控和独立 `ai_reviews` 持久化；
- Provider 缺少密钥、禁用或输出格式错误时失败关闭，不保存伪成功审阅；
- Provider 输入 Token 上限，以及在查找 Provider 前拒绝摘要不匹配；
- 精确本地运行策略（`127.0.0.1`/`localhost:3000`、并发不超过 5）、远程路由阻断和模型路由门控；
- Juice Shop 受限探测：外部主机接触前拒绝、响应体最小化、重定向复核、全 URL preflight，
  以及依赖阻断工件；
- Juice Shop CLI 状态/基线输出、项目根目录外输出拒绝、中文帮助和输出模式；
- 固定 Docker 候选发现、仅回环的 ZAP quick-scan 命令、外部 URL 过滤、ZAP 报告解析、
  扫描元数据保留和显式 `--confirm-local` 门控；
- 简体中文状态/原因映射、安全 `_zh` JSON 解释、TTY/管道自动输出选择、显式
  `--human`/`--json` 模式、不会泄露原始证据的人类 Finding 摘要和中文一键启动器；
- Windows PowerShell 5.1 的 UTF-8 BOM 解析回归，确保桌面快捷方式不会因中文脚本编码而出现
  `UnexpectedToken`；
- Windows PowerShell 进度流关闭回归，避免 `0......` 重绘造成中文重复；
- 简体中文 WinForms 主菜单、桌面启动器 GUI 分派、UTF-8 BOM 和目标录入表单的安全契约；
- WinForms 按钮事件分派、脚本作用域函数解析、目标表单和 AI 设置窗口的打开/关闭回归；
- WinForms 主页全部可见按钮的实际鼠标命中层级回归：按钮中心必须命中按钮本身，不能被卡片面板覆盖；
- WinForms 左侧六个导航入口的真实按钮、鼠标命中和功能路由回归，禁止再用无事件的标签伪装导航；
- WinForms 首页卡片说明文字与操作按钮的无重叠回归，确保按钮显示后文字仍清晰可读；
- WinForms 96-DPI 设计基线、整棵控件树的 200% 等比缩放、非兼容文本渲染和 UTF-8 BOM 回归，避免高缩放屏幕上的文字裁切、发虚或中文脚本乱码；
- 目标录入校验：HTTPS 清洁 URL、允许/排除主机、端口、项目目录边界和默认未确认状态；
- `target-review` 离线人工目标选择、Scope/计划项目根边界、非本地 mock 不联网、摘要门控和安全
  中文输出；
- 本机自动化验收编排器的回环 URL 硬门、敏感输出脱敏、工件路径边界、可观察发现指标和未知值
  保留为 `null`；
- 三靶场非破坏性安全回归：Juice Shop 公开面、DVWA 未登录边界/登录后 SQLi 页面/无害反射标记、
  WebGoat 未登录边界/合成账号登录后课程入口；18 次执行全部通过，响应正文、Cookie 和 Token
  未写入工件；
- Ground Truth 元数据解析、保守的业务逻辑/认证分类、Finding 状态归一化，以及零分母/未执行时
  保持空指标。

`python -m compileall -q src_auto tools tests` —— **通过**。

## 手工/本机验证

- CLI `new -> run --local-lab -> findings -> reports` —— **通过**；生成一个去重后的低严重度
  fixture 候选。
- CLI `stop -> run` —— **已停止**；CLI `resume --local-lab` —— **完成**。
- `httpx.exe -silent -u http://127.0.0.1:8765/` —— **通过**，仅回环。
- `katana.exe -silent -u http://127.0.0.1:8765/ -d 1` —— **通过**，仅回环。
- 未接触真实补天目标或任何第三方目标。
- 未发起实时远程 AI 调用；远程验证使用注入式假响应。DeepSeek 实时调用仍需操作者先撤销聊天中
  粘贴过的旧密钥、创建新密钥，并在本机设置 `DEEPSEEK_API_KEY`。
- 示例 `run-live` —— 按设计返回 `blocked_policy`，因为 `allow_real_targets` 仍为 `false`，
  没有启动外部进程。
- Docker Client/Server 29.7.2 —— **通过**；Docker 数据位于
  `D:\网络安全文件夹\DockerData\wsl`。
- `docker ps` —— **通过**；`juice-shop` 仅映射到 `127.0.0.1:3000`，重启策略为
  `unless-stopped`。
- `Invoke-WebRequest http://127.0.0.1:3000/` —— **HTTP 200**。
- `python -m src_auto juice-shop-status --human` —— **通过**；中文交互摘要、回环范围和 Docker
  状态均正确显示。
- `python -m src_auto juice-shop-baseline --human` —— **COMPLETED_DISCOVERY_ONLY**；保留 31 个
  本地 URL，排除 15 个外部 URL，控制层 preflight 计数为 1，远程 AI 为 0。
- `python -m src_auto juice-shop-zap --confirm-local --human` —— **POSSIBLE_FINDINGS**；本次
  工件包含 5 个未验证的本地候选，均保持 `POSSIBLE`，必须人工复核。
- `python -m src_auto juice-shop-status --json` —— **通过**；英文机器字段保持稳定，并附带
  `status_zh`/`reason_zh` 等中文解释。
- Windows PowerShell 5.1 直接执行 `START_SYSTEM.ps1` —— **通过解析/契约验证**；启动器包含三靶场
  Compose 健康检查、本机三轮验收、安全回归、Findings/报告展示和退出码汇总流程。
- `python tools/run_local_lab_validation.py --local-only --repeat-rounds 2` —— **通过编排**；
  生成三靶场九轮工件，P0 的 Scope Escape/External Targets/Remote AI Calls/Secret Leakage/Crash
  均为 0。逐轮 ZAP 候选数量存在波动，稳定性只作为观察值，未把它当成检测准确率。
- `python tools/run_local_regression.py --local-only --repeat-rounds 2` —— **18/18 通过**；
  只执行公开面、认证边界、登录后表面和无害反射标记，不发送破坏性 payload。
- `python -m src_auto target-review` —— **通过离线审阅**；本机与非本地 mock 均未产生网络请求，
  未确认选择返回 `awaiting_selection`，确认后仍提示 `run-live --execute-live`。

## 工具验证

- Subfinder v2.15.0 —— 已验证版本。
- httpx v1.10.0 —— 已验证版本，并完成回环调用。
- Katana v1.7.0 —— 已验证版本，并完成回环调用。
- Nuclei v3.11.1 —— 已验证 SHA-256，但端点安全软件阻止执行（不标记为通过）。
- OWASP ZAP 2.17.0 —— 已验证版本，仅对固定回环靶场执行；候选保持 `POSSIBLE` 或
  `NOT_VERIFIED`，均未自动升级为漏洞。
- BBOT 3.0.1 —— 当前 Python 3.8/Windows-only 环境不可运行；当前版本需要 Python >=3.10 和
  POSIX 依赖。
- reconFTW —— WSL 已安装，但尚未接入或在当前 Windows 工作流执行。

## 验收状态

控制层、本地 E2E 验收标准、三靶场生命周期、发现基线、本地控制项裁决和非破坏性安全回归均已通过验证。完整
官方 Juice Shop 检测回归仍为**未测试**（116 条题目元数据/67 条 scanner-detectable 尚未完整
执行），Nuclei 又受端点安全阻断，BBOT/reconFTW 需要不同的运行环境。未把任何候选宣称为已
确认漏洞，也未自动提交补天报告。

本机自动化最终工件见 `validation/autotest/LOCAL_LAB_TEST_REPORT.md` 和
`validation/autotest/LOCAL_LAB_SCORE.json`。`AUTHORIZED_LOCAL_VALIDATION_READY` 的含义仅是
控制层在两个回环靶场的安全流程可复核；官方 Ground Truth Precision/Recall 仍为
`null`/`NOT_TESTED`，不能据此声称已找到可获赏漏洞。

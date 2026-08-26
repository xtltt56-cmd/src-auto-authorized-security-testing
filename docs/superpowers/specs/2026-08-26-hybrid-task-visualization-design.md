# SRC-Auto 混合桌面任务可视化设计规格

## 1. 文档状态

- 日期：2026-08-26
- 状态：待用户书面复核后进入实现
- 适用平台：Windows 10/11 单机部署
- 项目根目录：`D:\网络安全文件夹\SRC-Auto`
- 正式定位：SRC-Auto 授权安全测试编排与候选漏洞研判平台

## 2. 目标

在保留桌面一键启动、人工录入目标、人工确认授权、人工最终裁决和人工补天提交的前提下，增加完整的任务过程可视化。操作者应能够看到任务当前阶段、最近动作、已耗时、工具状态、候选数量、被策略阻止的动作、报告生成情况，以及安全暂停、停止和恢复结果。

本设计同时覆盖：

1. 五个固定回环靶场的自动化验收；
2. 项目内 Scope 与计划文件的离线审阅；
3. 已人工确认授权目标的低风险、受控测试过程；
4. 候选 Finding、人工裁决与报告查看；
5. 本地任务历史、崩溃恢复和审计追踪。

## 3. 非目标

本次升级不实现以下行为：

- 自动选择补天项目或资产；
- 自动扩大目标范围；
- 无人工确认地启动真实目标测试；
- 爆破、拒绝服务、批量对象枚举或破坏性请求；
- 自动把扫描器告警认定为漏洞；
- 自动向补天或任何第三方平台提交报告；
- 把 Cookie、Token、密码、API Key 或完整敏感响应写入日志；
- 将控制台暴露到局域网或公网；
- 使用外部 CDN 加载界面脚本、字体或图标。

## 4. 设计原则

1. **单一状态源**：复用 `data/src_auto.sqlite3`，不创建互相竞争的第二套任务数据库。
2. **追加式事件**：阶段变化和重要动作写入不可变事件行，状态快照只作为快速读取缓存。
3. **失败关闭**：授权、范围、时间窗或依赖不满足时，任务进入 `blocked`，不能自动降级为继续执行。
4. **合作式停止**：暂停和取消在安全检查点生效，不直接粗暴杀死数据库、Docker 或浏览器进程。
5. **界面与执行解耦**：关闭界面不终止任务；任务服务退出后可从 SQLite 恢复历史。
6. **本地优先验收**：所有自动测试均在五个回环靶场和本地夹具中完成。
7. **兼容回退**：新控制台异常时，旧 WinForms 控制台和 CLI 仍可工作。
8. **全部落盘到 D 盘**：运行时、缓存、WebView2 用户数据、日志、数据库、前端产物和报告均位于项目目录或明确指定的 D 盘工具目录。

## 5. 总体架构

```text
桌面快捷方式
  └─ START_SYSTEM.ps1
       ├─ 检查项目专用 Python / WebView2 / 端口
       ├─ 启动本地任务服务（127.0.0.1 + 随机端口）
       └─ 启动 WebView2 桌面壳
             └─ 本地 Web 仪表盘
                  ├─ REST：任务、授权、暂停、恢复、报告
                  └─ SSE：实时任务事件

本地任务服务
  ├─ TaskEvent / TaskState 状态机
  ├─ Store（现有 SQLite，WAL 模式）
  ├─ TaskOrchestrator
  │    ├─ LocalLabAdapter
  │    ├─ OfflineReviewAdapter
  │    └─ AuthorizedTargetAdapter
  ├─ ScopeGuard + RuntimePolicy + LivePlan
  └─ 报告与 JSONL 审计导出

执行对象
  ├─ Juice Shop      127.0.0.1:3000
  ├─ DVWA            127.0.0.1:8081
  ├─ WebGoat         127.0.0.1:8082
  ├─ VAmPI           127.0.0.1:8083
  └─ Business API    127.0.0.1:8084
```

## 6. 技术选型

### 6.1 后端

- 项目专用 Python 3.12，安装到 D 盘，不替换系统 Python 3.8；
- 现有 `sqlite3` + WAL 作为状态存储；
- FastAPI 提供仅回环 REST API；
- `sse-starlette` 提供服务器发送事件；
- Uvicorn 只监听 `127.0.0.1`，端口由启动器动态选择；
- 现有 `unittest` 保持为主测试框架。

### 6.2 前端

- React + TypeScript；
- Vite 只用于构建，正常运行不需要 Node.js；
- Chart.js 只负责耗时、候选分布和阶段统计；
- 任务时间线、日志和表格使用本地组件实现；
- 所有依赖构建后复制到 `dashboard/dist/`，运行时不访问 CDN。

### 6.3 桌面壳

- C# WPF + Microsoft WebView2；
- 自包含发布到 `desktop/publish/`；
- WebView2 只允许导航到启动器生成的本地 URL；
- 浏览器模式作为明确的备用入口；
- WebView2 用户数据目录固定到 `runtime/webview2-data/`。

### 6.4 设计稿

前端编码前必须使用 Figma 插件完成页面和状态稿，并在项目内记录 Figma 链接、页面清单、导出 PNG 和设计令牌。未通过视觉稿确认，不进入 React 页面实现。

## 7. 目录设计

```text
SRC-Auto/
├─ dashboard/
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ src/
│  └─ dist/
├─ desktop/
│  ├─ SrcAuto.Desktop/
│  ├─ SrcAuto.Desktop.Tests/
│  └─ publish/
├─ runtime/
│  ├─ python312/
│  ├─ node/
│  ├─ webview2-data/
│  └─ locks/
├─ sessions/
│  └─ <run-id>/
│     ├─ events.jsonl
│     ├─ summary.json
│     ├─ logs/
│     └─ reports/
├─ src_auto/
│  ├─ task_events.py
│  ├─ task_orchestrator.py
│  ├─ task_adapters.py
│  ├─ authorization_gate.py
│  └─ dashboard/
│     ├─ app.py
│     ├─ api.py
│     ├─ security.py
│     └─ schemas.py
└─ data/
   └─ src_auto.sqlite3
```

`runtime/`、`sessions/` 和 `desktop/publish/` 属于运行产物或可重建产物，Git 策略由实施阶段明确：密钥、会话、数据库和 WebView2 用户数据必须忽略；源码、锁文件、设计稿和安装说明必须提交。

## 8. 任务数据模型

### 8.1 任务运行表

现有 `runs` 表继续作为任务身份和总状态。新增 `task_runtime` 表保存可视化快照：

```sql
CREATE TABLE IF NOT EXISTS task_runtime (
    run_id TEXT PRIMARY KEY,
    task_kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    state TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    network_contact TEXT NOT NULL DEFAULT 'none',
    pause_requested INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    last_event_id INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_code TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
```

### 8.2 任务事件

现有 `events` 表继续保存事件；结构化字段写入 `payload_json`。每个事件至少包含：

```json
{
  "schema_version": 1,
  "event_type": "stage_started",
  "stage": "surface_discovery",
  "state": "running",
  "progress": 35,
  "message_zh": "正在发现授权范围内的公开入口",
  "tool": "katana",
  "target_mode": "authorized",
  "network_contact": "authorized_target",
  "counters": {
    "processed": 18,
    "candidates": 2,
    "blocked": 0,
    "errors": 0
  },
  "error_code": "",
  "redacted": true
}
```

SQLite 自增事件 `id` 作为 SSE 事件序号和断线重连游标。

### 8.3 事件类型

- `task_created`
- `authorization_required`
- `authorization_confirmed`
- `stage_waiting`
- `stage_started`
- `stage_progress`
- `stage_completed`
- `stage_warning`
- `stage_blocked`
- `pause_requested`
- `task_paused`
- `resume_requested`
- `cancel_requested`
- `task_cancelled`
- `task_failed`
- `report_created`
- `task_completed`

### 8.4 状态机

```text
created
  ├─> waiting_authorization ──> queued
  ├─> blocked
  └─> queued

queued ──> running
running ──> pausing ──> paused ──> queued
running ──> cancelling ──> cancelled
running ──> completed
running ──> failed
running ──> blocked
```

非法状态迁移必须被拒绝并记录 `invalid_state_transition`，不能静默修正。

## 9. 阶段定义

统一阶段顺序如下：

1. `policy_check`：运行策略、模式和资源检查；
2. `authorization_check`：授权证据、Scope、时间窗和 live plan；
3. `dependency_check`：Docker、工具、代理和本地模型；
4. `target_health`：目标可达性和固定健康端点；
5. `surface_discovery`：入口、API、公开静态资源和响应头；
6. `controlled_validation`：允许的低风险验证；
7. `normalize`：统一扫描器输出；
8. `deduplicate`：按指纹去重；
9. `candidate_triage`：候选解释和优先级；
10. `human_adjudication`：等待人工裁决；
11. `report_generation`：生成摘要、证据索引和提交草稿；
12. `completed`：任务结束，不代表发现可提交漏洞。

本地靶场可以自动通过授权检查；授权目标必须停留在 `waiting_authorization`，直到人工确认。

## 10. 任务适配器

### 10.1 LocalLabAdapter

封装现有 `tools/run_local_lab_validation.py`，把五靶场生命周期、每轮发现、ZAP 候选、API Schema 检查、业务对象矩阵、裁决和评分转换为统一事件。原有 JSON/Markdown 工件继续保留。

### 10.2 OfflineReviewAdapter

封装现有离线范围审阅；`network_contact` 永远为 `none`。任务进度只表示文件解析和策略检查，不得显示为目标扫描。

### 10.3 AuthorizedTargetAdapter

复用 `ScopeGuard`、`RuntimePolicy` 和 `validate_live_plan()`。适配器只接收已经通过 `AuthorizationGate` 的不可变任务快照；运行中发现的新主机或重定向必须再次经过 ScopeGuard。

## 11. 授权闸门

授权目标开始前必须同时满足：

- `scope_confirmed.yaml` 存在且 `confirmed=true`；
- `allow_network_contact=true`；
- `live_plan.yaml` 校验通过；
- 授权时间窗覆盖当前时间；
- 当前目标主机和端口位于允许范围；
- 自动化测试许可被明确记录；
- 操作者在当前会话点击确认；
- 任务请求方法、请求上限、并发和阶段符合计划。

授权快照保存哈希而不是敏感原文；任务运行过程中 Scope 文件变化时进入 `blocked_scope_changed`，要求重新确认。

## 12. API 设计

### 12.1 只读接口

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{run_id}`
- `GET /api/v1/tasks/{run_id}/events?after_id=<id>`
- `GET /api/v1/tasks/{run_id}/stream`
- `GET /api/v1/tasks/{run_id}/reports`
- `GET /api/v1/tasks/{run_id}/reports/{report_id}`
- `GET /api/v1/labs/status`
- `GET /api/v1/tools/status`

### 12.2 修改接口

- `POST /api/v1/tasks/local-lab`
- `POST /api/v1/tasks/offline-review`
- `POST /api/v1/tasks/authorized`
- `POST /api/v1/tasks/{run_id}/authorize`
- `POST /api/v1/tasks/{run_id}/pause`
- `POST /api/v1/tasks/{run_id}/resume`
- `POST /api/v1/tasks/{run_id}/cancel`

所有修改接口要求启动器生成的随机会话令牌；授权接口还要求任务级确认 nonce。服务拒绝跨域请求、无令牌请求、重复 nonce 和非回环 Host 头。

## 13. 界面信息架构

### 13.1 页面

1. 总览仪表盘；
2. 新建任务与授权范围；
3. 实时任务详情；
4. 五靶场运行视图；
5. 候选 Finding 人工研判；
6. 报告详情；
7. 任务历史与恢复；
8. AI 人工审阅设置；
9. 系统依赖与扫描器状态；
10. 安全停止和异常恢复。

### 13.2 实时任务详情布局

- 顶部：任务名称、模式、目标摘要、安全状态、已耗时；
- 左侧：阶段时间线；
- 中部：实时事件日志，可按等级、阶段和工具筛选；
- 右侧：入口、API、候选、阻止和错误计数；
- 底部：安全暂停、停止、打开报告和导出脱敏日志；
- 授权目标额外显示 Scope 哈希、授权期限、允许方法、请求上限和并发。

### 13.3 视觉状态

- 蓝色：进行中；
- 绿色：已完成；
- 黄色：等待人工或有警告；
- 红色：失败或安全阻止；
- 灰色：尚未执行或不适用。

颜色之外必须同时提供文字、图标和可访问标签，不能只靠颜色表达状态。

## 14. 暂停、停止和恢复

- `pause` 设置请求标志；当前网络请求或工具安全单元完成后进入 `paused`；
- `cancel` 设置取消标志；适配器关闭子进程输入并在超时后终止该任务拥有的子进程树；
- Docker Compose 服务不因取消单个验证任务而默认删除；
- 后端每五秒刷新心跳；超过 30 秒且进程不存在时标记 `interrupted`；
- 恢复授权任务前重新验证 Scope 哈希、时间窗和当前会话确认；
- 不支持从破坏性或不可重放步骤中间恢复；本设计默认不提供此类步骤。

## 15. 日志与脱敏

事件消息不得包含：

- `Authorization`、`Cookie`、`Set-Cookie` 值；
- API Key、密码、会话令牌；
- 完整个人信息字段；
- 未经限制的响应正文；
- 可被直接复制为越界批量攻击的命令。

日志保存工具名、版本、阶段、状态码类别、响应大小、指纹和经过允许的路径摘要。每次写入前通过统一 `redact_event_payload()`。

## 16. 本地服务安全

- 监听地址固定为 `127.0.0.1`；
- 使用操作系统分配的随机空闲端口；
- 启动器通过受限权限文件传递 256 位随机令牌；
- 服务启动成功后删除明文令牌文件，桌面壳只在内存保存；
- `Origin`、`Host` 和 `Sec-Fetch-Site` 必须符合本地应用策略；
- CSP 禁止远程脚本、远程字体、插件和任意 iframe；
- WebView2 禁止新窗口、下载、外部导航和非本地 URL；
- 调试工具只在开发构建启用；
- 报告 HTML 仍作为只读文本或经过消毒的静态预览，不直接执行脚本。

## 17. 兼容与迁移

迁移按以下顺序执行：

1. 为 Store 和 Pipeline 增加结构化事件，不改变现有输出；
2. 五靶场接入事件流，CLI 和旧 GUI 继续可用；
3. 完成本地 Web 仪表盘并先用 Chrome 验证；
4. 完成 WebView2 桌面壳和浏览器回退；
5. 把桌面快捷方式切换为新控制台；
6. 离线审阅接入；
7. 授权目标只在本地模拟授权目标上通过全部测试后接入；
8. 旧 WinForms 入口保留至少一个稳定版本周期。

## 18. 测试策略

### 18.1 单元测试

- 状态迁移；
- 事件序号和脱敏；
- Store 迁移和断线游标；
- 授权快照和过期；
- 非法 Host、Origin、令牌和 nonce；
- 安全暂停、停止和恢复。

### 18.2 集成测试

- 五靶场完整事件顺序；
- 一个靶场失败时其余靶场状态保持真实；
- SSE 断线后从 `Last-Event-ID` 恢复；
- 服务重启后历史任务可查看；
- 报告点击和内容预览；
- Chrome 模式和 WebView2 模式显示相同状态。

### 18.3 安全测试

- 外部 Host 头被拒绝；
- 过期令牌被拒绝；
- 路径穿越被拒绝；
- 报告脚本不执行；
- 授权范围变化导致任务阻止；
- 取消不会影响非任务拥有的进程；
- 测试期间外部目标接触计数为 0；
- 远程 AI 调用计数为 0，除非单独人工启用 AI 审阅测试。

### 18.4 UI 测试

- 所有主要按钮真实可点击；
- 进度不阻塞主线程；
- 125%、150%、175% DPI 不截断；
- 1366×768 和 1920×1080 均可操作；
- 中文无乱码；
- 任务日志超过 10,000 条时使用虚拟列表或窗口化渲染；
- 断线、失败、等待人工和安全阻止具有不同可读状态。

## 19. 验收标准

只有同时满足以下条件，任务可视化升级才可宣称完成：

1. 五靶场一次完整运行的阶段和事件在界面中实时出现；
2. GUI 在整个本地验收过程中保持可点击和可关闭；
3. 任务暂停、取消和恢复均有自动化证据；
4. SSE 断线重连不丢失已持久化事件；
5. 服务或界面崩溃后历史任务仍可查看；
6. 所有任务状态与最终 JSON/Markdown 报告一致；
7. 授权目标未确认前没有网络请求；
8. 授权过期、Scope 变化和越界重定向都进入阻止状态；
9. 所有测试只使用本地靶场和本地夹具；
10. 外部目标接触、自动提交、密钥泄漏和未经同意的远程 AI 调用均为 0；
11. 新旧入口都有清晰回退说明；
12. 完整 Python、PowerShell、前端、桌面壳和本地验收测试全部通过。

## 20. 发布与回退

发布采用双入口：

- `桌面快捷方式`：默认启动新混合控制台；
- `START_SYSTEM.ps1 -LegacyGui`：启动旧 WinForms 控制台。

新控制台启动失败、健康检查超时或 WebView2 不可用时，启动器显示中文原因并提供“使用浏览器打开”和“启动旧控制台”两个按钮。回退不修改数据库，不删除任务历史，也不改变授权配置。

## 21. 分期计划

本规格拆为四个独立实施计划：

1. `2026-08-26-task-event-core.md`：事件、状态机、Store 和五靶场接入；
2. `2026-08-26-realtime-dashboard.md`：Figma、FastAPI/SSE 和 React 控制台；
3. `2026-08-26-webview2-desktop-shell.md`：WebView2 桌面壳、一键启动和回退；
4. `2026-08-26-authorized-target-progress.md`：授权目标闸门、可视化和本地模拟验收。

每个计划都必须独立产出可运行、可测试、可回退的软件，不允许跨期提前启用真实目标。

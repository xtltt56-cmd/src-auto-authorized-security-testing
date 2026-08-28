# SRC-Auto 阶段 0 基线记录

记录日期：2026-08-26（Asia/Shanghai）
工作区：`D:\网络安全文件夹\SRC-Auto`
分支：`codex/task-visualization-current`
文档锚点提交：`5d7d7af90879d22bc27b97888a1d2b512a77cdfe`
工作区快照：基线记录时另有 227 条预先存在的未提交变更；本次没有重置、覆盖或提交这些用户变更。

## 记录目的

本文件冻结升级前的可复现事实。它不是漏洞报告，也不代表任何真实目标已被访问。所有网络活动均限制在 Docker 本地回环靶场，真实补天目标、外部站点和补天提交均未执行。靶场容器在验收结束后已收拢，未留下后台服务。

## 环境基线

| 项目 | 结果 |
|---|---|
| 操作系统 | Windows 10.0.26200 |
| PowerShell | 7.6.4 |
| 默认 Python | 3.8.10 |
| 可用 Python 3.12 | `C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe` |
| Docker 客户端/服务端 | 29.7.2 / 29.7.2 |
| Docker Compose | 5.4.0 |
| WebView2 Runtime | 151.0.4129.107 |
| Node.js | 未安装到项目运行时 |
| 远程 AI 调用 | 0 |
| 自动补天提交 | 0 |

## Python 回归

执行命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -p 'test_*.py'
```

实际结果：

```text
Ran 238 tests in 27.530s
OK
```

测试期间没有保留 Python 进程，且使用 `PYTHONDONTWRITEBYTECODE=1` 防止生成缓存污染 worktree。

## 本地靶场回归

执行命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python tools/run_local_lab_validation.py --local-only --repeat-rounds 2
```

实际总结果：

```text
EXIT_CODE=0
STATUS=AUTHORIZED_LOCAL_VALIDATION_READY
MODE=local-only
TARGET_COUNT=5
EXTERNAL_TARGETS_CONTACTED=0
REMOTE_AI_CALLS=0
AUTO_SUBMISSION=NO_AUTO_SUBMISSION
```

应用靶场结果：

| 应用靶场 | 地址 | 结果 | 三轮发现数 | TP / FP / FN / 未验证 | Precision / Recall / F1 | 网络范围 |
|---|---|---:|---:|---:|---:|---|
| 业务 API | `http://127.0.0.1:8084/` | READY | 0 / 0 / 0 | 3 / 0 / 0 / 0 | 1.000 / 1.000 / 1.000 | 本地回环 |
| DVWA | `http://127.0.0.1:8081/` | READY | 9 / 8 / 9 | 7 / 1 / 0 / 2 | 0.875 / 1.000 / 0.933 | 本地回环 |
| Juice Shop | `http://127.0.0.1:3000/` | READY | 5 / 5 / 5 | 1 / 4 / 0 / 0 | 0.200 / 1.000 / 0.333 | 本地回环 |
| VAmPI | `http://127.0.0.1:8083/` | READY | 0 / 0 / 0 | 2 / 0 / 0 / 0 | 1.000 / 1.000 / 1.000 | 本地回环 |
| WebGoat | `http://127.0.0.1:8082/` | READY | 0 / 0 / 0 | 1 / 0 / 0 / 0 | 1.000 / 1.000 / 1.000 | 本地回环 |

说明：三轮发现数依次对应 `round_00`、`round_01`、`round_02`。TP/FP/FN/未验证是本地控制项和发现面裁判结果，不是漏洞成立率；所有记录 `submission_ready=false`，本轮赏金就绪数为 0。

Compose 健康状态（验收期间）：

```text
dvwa       running / healthy / 127.0.0.1:8081->80/tcp
db         running / healthy / internal infrastructure for DVWA
juice-shop running / healthy / 127.0.0.1:3000->3000/tcp
vampi      running / healthy / 127.0.0.1:8083->5000/tcp
webgoat    running / healthy / 127.0.0.1:8082->8080/tcp
business-api running / healthy / 127.0.0.1:8084->8084/tcp
```

验收期间共有 5 个应用靶场和 1 个 DVWA 数据库基础设施；数据库没有宿主端口。验收结束后执行了 `docker compose -f docker-compose.local-labs.yml down`（未使用 `--remove-orphans`、未删除卷），当前不保留后台容器。

## 已确认的基线问题

1. 个别历史 JSON/控制台入口仍需做一次中文编码回归，不能仅凭本轮汇总输出宣称全部历史产物已修复。
2. VAmPI 的只读 OpenAPI smoke 在本轮报告了 `POSSIBLE_SCHEMA_CONTRACT_ISSUES`；它被记录为人工复核候选，不是漏洞结论，也没有自动提交。
3. Figma 设计门禁尚未完成。仓库已有任务可视化文字交接稿，但缺少经 Figma 创建并批准的任务总览、实时详情、靶场矩阵、授权确认、阻断说明、报告查看器、恢复和 DPI 状态页面。
4. 项目尚未提供项目内 Node.js 运行时，实时仪表盘阶段需要先部署 D 盘项目本地运行时。
5. 当前默认 Python 是 3.8.10；升级后的服务依赖应在项目本地 Python 3.12 中验证，同时保持核心安全模块的 3.8 兼容性。

## 安全结论

本次基线没有访问任何真实目标，没有执行破坏性请求，没有执行自动补天提交，没有调用远程 AI。五个应用靶场的 Findings 只属于本地训练/控制项结果，不得直接当作赏金漏洞提交。`scope_escape=0`、`external_targets_contacted=0`、`remote_ai_calls=0`、`secret_leakage=0`、`crash=0`。

## 阶段 0 后续门禁

- [x] 建立 D 盘隔离 worktree。
- [x] 记录环境和当前提交。
- [x] 完成 238 项 Python 回归。
- [x] 完成五应用靶场三轮本地回归。
- [x] 补齐第五个应用靶场（业务 API）并纳入清单、健康检查和验收矩阵。
- [ ] 完成并批准 Figma 页面设计包。
- [ ] 形成可恢复的发布/回滚记录。
- [ ] 通过 G0 后进入任务事件核心实现。

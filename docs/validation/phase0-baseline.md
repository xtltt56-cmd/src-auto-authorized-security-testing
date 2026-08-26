# SRC-Auto 阶段 0 基线记录

记录日期：2026-08-26（Asia/Shanghai）
工作区：`D:\网络安全文件夹\SRC-Auto\.worktrees\task-visualization`
分支：`codex/task-visualization`
基线提交：`c5fbdc942a1fd1bf2c70d32c721574befaa779f8`

## 记录目的

本文件冻结升级前的可复现事实。它不是漏洞报告，也不代表任何真实目标已被访问。所有网络活动均限制在 Docker 本地回环靶场，真实补天目标、外部站点和补天提交均未执行。

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
Ran 219 tests in 23.694s
OK
```

测试期间没有保留 Python 进程，且使用 `PYTHONDONTWRITEBYTECODE=1` 防止生成缓存污染 worktree。

## 本地靶场回归

执行命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python tools/run_local_lab_validation.py --local-only --repeat-rounds 0
```

实际总结果：

```text
EXIT_CODE=0
STATUS=AUTHORIZED_LOCAL_VALIDATION_READY
MODE=local-only
TARGET_COUNT=4
EXTERNAL_TARGETS_CONTACTED=0
REMOTE_AI_CALLS=0
AUTO_SUBMISSION=NO_AUTO_SUBMISSION
```

应用靶场结果：

| 应用靶场 | 地址 | 结果 | 发现数 | 网络范围 |
|---|---|---|---:|---|
| Juice Shop | `http://127.0.0.1:3000/` | READY | 5 | 本地回环 |
| DVWA | `http://127.0.0.1:8081/` | READY | 9 | 本地回环 |
| WebGoat | `http://127.0.0.1:8082/` | READY | 0 | 本地回环 |
| VAmPI | `http://127.0.0.1:8083/` | READY | 0 | 本地回环 |

Compose 健康状态：

```text
dvwa       running / healthy / 127.0.0.1:8081->80/tcp
db         running / healthy / internal infrastructure for DVWA
juice-shop running / healthy / 127.0.0.1:3000->3000/tcp
vampi      running / healthy / 127.0.0.1:8083->5000/tcp
webgoat    running / healthy / 127.0.0.1:8082->8080/tcp
```

## 重要差异：四个应用靶场，不是五个

当前 `config/labs/local_labs.json` 的 `target_count` 为 4。Docker Compose 虽然显示 5 个健康服务，但 `db` 是 DVWA 数据库基础设施，不是独立测试应用。因此当前事实是：

```text
可测试应用靶场 = 4
数据库基础设施 = 1
真实目标访问 = 0
```

升级计划中的“第五个应用靶场”尚未实现。后续应增加一个固定、可复现、仅回环发布的业务 API 训练靶场，并将它加入清单、健康检查、任务事件和验收矩阵；在此之前不能报告“五个应用靶场已通过”。

## 已确认的基线问题

1. `tools/run_local_lab_validation.py --help` 和历史 JSON 报告中存在中文乱码，说明控制台或历史产物仍有编码链路需要修复。
2. 当前清单只有四个应用靶场，和升级计划的五个应用靶场目标不一致。
3. Figma 设计门禁尚未完成。仓库只有一个主页概念 PNG，缺少任务总览、实时详情、靶场矩阵、授权确认、阻断说明、报告查看器、恢复和 DPI 状态等页面。
4. 项目尚未提供项目内 Node.js 运行时，实时仪表盘阶段需要先部署 D 盘项目本地运行时。
5. 当前默认 Python 是 3.8.10；升级后的服务依赖应在项目本地 Python 3.12 中验证，同时保持核心安全模块的 3.8 兼容性。

## 安全结论

本次基线没有访问任何真实目标，没有执行破坏性请求，没有执行自动补天提交，没有调用远程 AI。四个应用靶场的 Findings 只属于本地训练/控制项结果，不得直接当作赏金漏洞提交。

## 阶段 0 后续门禁

- [x] 建立 D 盘隔离 worktree。
- [x] 记录环境和当前提交。
- [x] 完成 219 项 Python 回归。
- [x] 完成一次本地四应用靶场回归。
- [ ] 补齐第五个应用靶场的设计与实现。
- [ ] 完成并批准 Figma 页面设计包。
- [ ] 形成可恢复的发布/回滚记录。
- [ ] 通过 G0 后进入任务事件核心实现。

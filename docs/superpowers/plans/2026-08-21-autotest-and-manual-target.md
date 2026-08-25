# SRC-Auto 本机验收与人工目标入口执行计划

> **执行方式：**按任务顺序在当前工作区直接执行；每项代码改动遵循测试先行、最小修改、证据优先。

## 目标与硬边界

- 修复 Windows PowerShell/Windows Terminal 启动器的中文重复和 `0......` 进度重绘。
- 提供 `target-review` 人工选择与 Scope 预览入口；该命令只读文件、校验和输出摘要，不联网、不启动扫描器。
- 只对 `http://127.0.0.1:3000` Juice Shop 执行本轮自动化测试；非本地 URL 只能在 mock/Scope Guard 测试中出现。
- 远程 AI、补天提交、暴力破解、凭据尝试、破坏性写入/删除、DoS、持久化和横向移动均保持关闭。
- 所有项目文件、日志和工件写入 `D:\网络安全文件夹\SRC-Auto`；不修改 Ground Truth 或指标评估器来改善结果。

## 任务 1：启动器重绘回归修复（TDD）

- [x] 在 `tests/test_launcher.py` 增加断言：`START_SYSTEM.ps1` 含 `$ProgressPreference = 'SilentlyContinue'`。
- [x] 运行 `python -m unittest tests.test_launcher -v`，记录新增断言在修复前失败。
- [x] 在 `START_SYSTEM.ps1` 的 `$ErrorActionPreference` 后加入 `$ProgressPreference = 'SilentlyContinue'`，保留 UTF-8 BOM、回环绑定和既有门控。
- [x] 重新运行启动器聚焦测试；用 Windows PowerShell 5.1 Parser API 解析脚本；实际执行一次本地启动器并确认 Docker/健康检查/本地基线流程结束且不访问外部地址。

## 任务 2：人工目标选择与 Scope 预览入口（TDD）

- [x] 新增 `tests/test_target_review.py`，覆盖本机计划、非本地 mock 计划、未确认选择、越界目标、Scope/计划路径越出项目根、无网络调用证明和 JSON/人类输出安全性。
- [x] 运行新增聚焦测试，确认实现前失败。
- [x] 新增纯离线模块 `src_auto/target_review.py`：读取并验证项目根内 Scope/计划；调用 `ScopeGuard.decide()`；返回状态、目标类型、主机/端口、Scope 摘要和计划摘要；不创建 HTTP 客户端、不调用子进程。
- [x] 在 `src_auto/cli.py` 增加 `target-review --scope --plan [--confirm-selection]`，接入现有 `--json/--human` 输出和中文状态映射；人类输出不显示命令参数、凭据或响应内容。
- [x] 未确认返回 `awaiting_selection`；已确认只返回 `selection_reviewed` 并提示下一步仍需 `run-live --execute-live`；任何越界或未确认 Scope 均失败关闭。
- [x] 重新运行新增测试和既有 CLI/Scope/Live Plan 测试，确认 `run-live` 的原有双重执行门控不被绕过。

## 任务 3：本机自动化验收编排器（TDD）

- [x] 新增 `tests/test_autonomous_validation.py`，只测试纯函数和拦截的命令构造：回环 URL 校验、敏感值脱敏、指标中未知项为 `null`、工件路径均在项目根、远程 AI 计数恒为 0。
- [x] 运行聚焦测试确认实现前失败。
- [x] 新增 `tools/run_autonomous_validation.py`，`--local-only` 为默认且唯一可执行模式；所有子进程使用固定参数数组、项目根 `cwd`、超时和有限输出，不使用 shell 拼接。
- [x] 生成 `PRECHECK_REPORT.md`、`validation/autotest/baseline_source_state.json`、`validation/autotest/round_00_baseline/`、`DISCOVERY_METRICS.json`、`AI_ABLATION_REPORT.md`、稳定性和最终 `AUTONOMOUS_VALIDATION_REPORT.md`。
- [x] 预检仅检查 Python/Git/Java/Ollama(回环)/httpx/katana/ZAP/Docker/Juice Shop、配置和磁盘；不访问公网。
- [x] 执行既有 `juice-shop-status`、`juice-shop-baseline` 和 `juice-shop-zap --confirm-local`；只接受回环目标，外链记录为排除项；ZAP 候选保持 `POSSIBLE/NOT_VERIFIED`，不得伪造真阳性。
- [x] 发现指标只从扫描工件可证明的 URL/HTML/JS/API/参数/客户端路由统计；未执行或无法裁决的值用 `null`/`NOT_TESTED`。
- [x] 本地 AI 开关对照仅在本地模型可用时运行，否则明确 `NOT_TESTED`；远程调用数和远程成本恒为 0。
- [x] 进行至少两轮本地重复回归并报告稳定性；第二靶场只有已有回环适配器时运行，否则 `NOT_TESTED`；不自动拉取外部镜像。
- [x] 报告 P0：Scope Escape=0、Remote AI Calls=0、Secret Leakage=0、Crash=0；其余指标按证据标为 `PASS/PARTIAL/NOT_TESTED/FAIL`，最终最高判定 `LOCAL_LAB_READY`。

## 任务 4：文档与操作说明

- [x] 更新 `USER_MANUAL.md`、`OPERATIONS.md`、`README.md`、`KNOWN_ISSUES.md`、`IMPLEMENTATION_REPORT.md`、`TEST_REPORT.md`，说明进度重绘修复、`target-review` 用法、两道外部执行门、仅本地验收和诚实限制。
- [x] 补充本地验证工件路径、人工审阅示例和“不得把候选 Finding 当作已确认漏洞”的说明；不写入任何 API 密钥。

## 任务 5：最终验收证据

- [x] 运行完整 `python -m unittest discover -s tests -v`，记录精确通过/失败数量。
- [x] 运行 `python -m compileall -q src_auto lab tests tools`、项目 JSON 解析、`git diff --check` 和敏感值扫描。
- [x] 运行 Windows PowerShell 5.1 Parser API 及一次真实启动器本机冒烟；确认桌面快捷方式仍指向 `START_SYSTEM.ps1`。
- [x] 运行 `python tools/run_autonomous_validation.py --local-only`；检查所有新工件位于 D 盘项目目录、远程计数为 0、Docker 端口绑定仍为 `127.0.0.1:3000`。
- [x] 汇总失败或未测试项，不以“脚本能运行”替代漏洞验证，不自动提交补天。

## 完成定义

只有当任务 1--5 的测试和工件均有命令输出证据，且不存在未解释的失败，才报告“本轮本地验收完成”。即使完成，也只表示本机靶场流程可复核，不表示已发现可获赏漏洞或具备生产/公网扫描授权。

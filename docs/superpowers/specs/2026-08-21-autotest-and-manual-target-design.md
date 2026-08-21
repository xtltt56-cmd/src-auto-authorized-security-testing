# SRC-Auto 本机验收与人工目标入口设计

日期：2026-08-21  
范围：`D:\网络安全文件夹\SRC-Auto`

## 目标

本次工作解决两个问题：

1. 修复桌面一键启动器在 Windows PowerShell 5.1/Windows Terminal 中的中文重复、进度条
   重绘和可见阻塞感；
2. 把现有“人工编写外部计划 + Scope Guard + `--execute-live`”流程补成一个可以人工选择
   非本地目标、先查看范围摘要、再决定是否执行的明确入口，同时本轮所有测试只接触本机靶场
   或 mock/interceptor。

本次不把代码存在、工具启动、URL 发现或候选 Finding 直接当成漏洞发现能力合格；验收报告必须
区分 `PASS`、`PARTIAL`、`NOT_TESTED` 和 `FAIL`。

## 不可突破的边界

- 实际测试目标只允许操作者本机启动的 `http://127.0.0.1:3000` Juice Shop；
- 任何外部 URL 在本轮只能被 Scope Guard/mock 拒绝，不能发送探测请求；
- 远程 AI 运行时保持 `AI_PROVIDER=local`、`LOCAL_LLM_ONLY=true`、`ALLOW_REMOTE_LLM=false`；
- 远程 AI 请求数和成本必须为 0；
- 不执行暴力破解、凭据测试、破坏性写入/删除、DoS、持久化、横向移动、批量个人数据收集；
- 不自动提交补天报告；
- Ground Truth 只在扫描结束后进入评估，不能驱动扫描器输入，也不能修改分母来提高指标；
- 项目创建的脚本、日志、报告和测试工件全部写入 D 盘项目目录；Docker/WSL 系统组件继续遵守
  已批准的系统例外。

## 启动器修复

`START_SYSTEM.ps1` 保持 UTF-8 BOM，保证 Windows PowerShell 5.1 能识别中文脚本。脚本顶部增加：

```powershell
$ProgressPreference = 'SilentlyContinue'
```

这样 `Invoke-WebRequest` 的进度流不会在 Windows Terminal 中重绘启动提示。该修复不改变
目标、端口、Docker 参数、扫描器或 AI 门控；测试必须包含：

- 文件以 UTF-8 BOM 开头；
- Windows PowerShell 5.1 解析器无错误；
- 启动器实际完成本机健康检查、基线和 local-lab 运行；
- 启动器文本包含本机安全警告且不包含公网绑定。

## 人工目标选择入口

新增命令 `target-review`，职责仅限“选择和审阅”，不启动任何外部工具、不联网：

```powershell
python -m src_auto target-review `
  --scope config/targets/<id>/scope_confirmed.yaml `
  --plan config/live_plan.example.yaml `
  --confirm-selection `
  --human
```

行为：

1. 只读取项目根目录内的 Scope 和人工计划；
2. 校验 Scope 的 `confirmed`、`allow_network_contact`、主机、端口、排除项和摘要；
3. 校验人工计划的操作人、授权说明、目标 URL、工具序列、命令参数和计划摘要；
4. 逐个调用 `ScopeGuard.decide()`，只生成允许/拒绝清单，不发请求；
5. 没有 `--confirm-selection` 时返回 `awaiting_selection`；
6. 有 `--confirm-selection` 时返回 `selection_reviewed`，并显示 Scope/计划摘要、目标数量、
   目标主机和“下一步仍需 `run-live --execute-live`”提示；
7. 任何失败返回 `blocked_scope`、`blocked_plan` 或 `blocked_selection`，并保持失败关闭；
8. `run-live` 仍是唯一可能启动外部适配器的入口，且继续要求策略开关、Scope 确认、人工计划
   `manual_execution_confirmed: true` 和 `--execute-live`。

该入口使操作者可以手动选择非本地 Scope，但不会把选择动作等同于授权，也不会在本轮测试中
实际接触非本地目标。

## 验收编排

新增 D 盘工具 `tools/run_autonomous_validation.py`，只允许 `--local-only`（默认）模式，按下列
顺序产生可审计工件：

1. `PRECHECK_REPORT.md`：Python、Git、Java、Ollama、模型、httpx、katana、ZAP、Docker、
   Juice Shop、磁盘、项目配置、Scope 和 Remote LLM Gate；
2. `validation/autotest/baseline_source_state.json`：HEAD、status、diff 摘要、关键配置摘要和
   Ground Truth SHA-256；
3. 本机状态、发现基线和 ZAP quick scan；只保留回环 URL，外链记为 out-of-scope；
4. `DISCOVERY_METRICS.json`：HTML、JavaScript、URL、API、参数、客户端路由等可由当前工件
   证明的数量，不能用未执行阶段填 0；
5. `validation/autotest/round_00_baseline/`：原始/归一化 Finding、verification、证据、
   false-positive/false-negative、metrics、资源和变更摘要；未裁决内容标记为 `NOT_TESTED`
   或 `INCONCLUSIVE`；
6. `AI_ABLATION_REPORT.md`：本地 AI 开启/关闭的对照；远程 AI 始终为 0；
7. 至少两次 reset 后的本机回归和一次稳定性汇总；不能达到阈值时必须输出根因分类，不能隐藏
   FP/FN；
8. `AUTONOMOUS_VALIDATION_REPORT.md`：安全、基线、最佳回归、稳定性、AI 对照、成本、修复轮次、
   剩余限制和最终 `LOCAL_LAB_READY`/`NOT_READY` 判定。

第二靶场只有在本机已有并能明确绑定回环端口时才可执行 zero-shot；若没有可用 WebGoat/DVWA
镜像或适配器，报告必须写 `NOT_TESTED`，不为了“完成表格”而拉取或接触外部服务。

## 验收判定

冻结的 P0 指标：

- Scope Escape = 0；
- Remote AI Calls = 0；
- Secret Leakage = 0；
- Crash = 0。

Precision、Scanner Detectable Recall、Verification Success Rate、稳定性和第二靶场指标只有在
完成合法 Ground Truth 裁决后才可计算；没有足够证据时输出 `NOT_TESTED`，最终最高只能是
`LOCAL_LAB_READY`，不能输出 `AUTHORIZED_PILOT_READY` 或 `PRODUCTION_READY`。

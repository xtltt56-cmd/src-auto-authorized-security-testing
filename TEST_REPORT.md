# 测试报告

日期：2026-08-24（Asia/Shanghai）

## 当前最终验收（2026-08-24）

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

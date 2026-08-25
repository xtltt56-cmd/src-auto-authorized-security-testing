# 本地靶场覆盖与可审计评分实施计划

> 本文是前一阶段的实施草案，已由 `2026-08-22-owasp-regression-lab-expansion.md` 和当前验收工件替代。当前实际配置为三靶场（Juice Shop、DVWA、WebGoat）；未勾选项保留作历史记录，不表示当前实现尚未完成。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在完全本地、默认拒绝外部请求的前提下，把 SRC-Auto 从 Juice Shop 表面发现扩展为可重置的双靶场、受限浏览器/API 发现、独立裁决和可计算的本地验收体系。

**Architecture:** 靶场生命周期由项目内 Python 编排器和固定 digest 的 Docker Compose 配置管理；Juice Shop 与 DVWA 均只发布到回环地址，并通过健康检查、ScopeGuard 和请求拦截器形成三层边界。发现、验证、裁决和评分分离，Ground Truth 只在扫描后用于评价，不反向驱动发现。

**Tech Stack:** Python 3.8 stdlib、Docker Compose、现有 ZAP/httpx/katana 适配器、可选 Playwright（不可用时退化为受限 HTTP/脚本资源发现）、unittest。

---

### Task 1: 固定靶场清单和运行策略

**Files:**
- Create: `config/labs/local_labs.json`
- Create: `docker-compose.local-labs.yml`
- Modify: `config/validation/local_only.json`
- Test: `tests/test_local_labs.py`

- [ ] 先写失败测试：验证两个靶场的 host/port、digest、健康 URL、reset 策略和外部目标拒绝。
- [ ] 运行 `python -m unittest tests.test_local_labs -v`，确认新接口缺失导致失败。
- [ ] 添加 Juice Shop 与 DVWA 固定 digest 配置、回环端口和内部网络 Compose；不使用 `latest`、Host 网络或 privileged。
- [ ] 扩展本地运行时端口 allowlist 为 3000、8081，并保持远程 AI 关闭。
- [ ] 运行该测试并确认通过。

### Task 2: 实现靶场生命周期管理

**Files:**
- Create: `src_auto/local_labs.py`
- Modify: `src_auto/cli.py`
- Test: `tests/test_local_labs.py`

- [ ] 先写 start/status/reset/stop 的命令契约测试，确保所有 Docker 参数固定且输出路径位于项目根目录。
- [ ] 实现 `local-labs status|start|reset|stop`，只接受配置内 lab_id，启动后等待健康 URL，记录 image digest 和容器 ID。
- [ ] 对 Docker 不可用、端口冲突、健康检查超时和 digest 不匹配返回明确阻塞状态，不复用旧报告。
- [ ] 运行生命周期测试和真实本机双靶场启动/重置测试。

### Task 3: 受限浏览器/API 发现

**Files:**
- Create: `src_auto/local_discovery.py`
- Modify: `tools/run_autonomous_validation.py`
- Test: `tests/test_local_discovery.py`

- [ ] 先写失败测试：外部 URL 在请求前被拒绝；本地页面中的 XHR/API、JS 字符串和查询参数被去重记录；Cookie/Authorization 被脱敏。
- [ ] 优先使用可用的 Playwright 捕获本地页面请求；不可用时使用 stdlib 获取本地 HTML/JS 并做静态 URL 提取，状态明确写成降级模式。
- [ ] 捕获并记录实际 XHR/Fetch/表单请求的路径、方法、参数名和认证需求，但不保存完整响应体。
- [ ] 所有请求通过 RuntimePolicy/ScopeGuard；外部资源只记录为 excluded，不执行。
- [ ] 运行本地发现测试，确认 API-like、client route 和 auth surface 不再凭空为 0/null。

### Task 4: 本地账户夹具与独立裁决

**Files:**
- Create: `validation/local-labs/adjudication_schema.json`
- Create: `src_auto/adjudication.py`
- Modify: `src_auto/validation.py`
- Test: `tests/test_adjudication.py`

- [ ] 先写失败测试：裁决状态只能是 TRUE_POSITIVE/FALSE_POSITIVE/POSSIBLE/NOT_VERIFIED；缺少基线、影响或复现证据不得成为 TRUE_POSITIVE。
- [ ] 为每个候选生成最小证据包，保留请求摘要、响应摘要、差异和人工结论，自动脱敏。
- [ ] 在 Juice Shop 与 DVWA 中使用虚构账户/角色夹具，测试前重置，禁止在报告中写入密码和 Token。
- [ ] 由人工裁决文件驱动 TP/FP/FN/Precision/Recall/F1/验证成功率计算；未裁决继续保持 null。
- [ ] 运行裁决单元测试和本地双靶场裁决演练。

### Task 5: 双靶场多轮验收和文档

**Files:**
- Modify: `tools/run_autonomous_validation.py`
- Modify: `USER_MANUAL.md`
- Modify: `KNOWN_ISSUES.md`
- Create: `validation/autotest/LOCAL_LAB_SCORE.json`
- Test: `tests/test_autonomous_validation.py`

- [ ] 先写失败测试：双靶场缺失、健康检查失败、外部请求数非零或旧工件复用时不得判定通过。
- [ ] 编排三轮 Juice Shop 与三轮 DVWA，分别记录发现、候选、裁决、稳定性和资源工件。
- [ ] 运行本地模型有无参与的对照，但不自动调用远程 AI；远程调用和成本保持 0。
- [ ] 运行全量 `python -m unittest discover -s tests -v`、编译、配置/密钥扫描、PS5 解析和桌面启动器冒烟测试。
- [ ] 只有新鲜证据满足所有强制门槛时，才写入 `AUTHORIZED_LOCAL_VALIDATION_READY`；否则准确写明阻塞项和 null 指标。

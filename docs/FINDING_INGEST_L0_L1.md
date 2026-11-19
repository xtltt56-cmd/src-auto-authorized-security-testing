# L0/L1 落地报告：工具输出治理与 ZAP Finding 入库闭环

日期：2026-11-18　分支：`agent/controlled-upgrade`（基线 HEAD `acf4574`，Release v0.14.2）
范围：仅 L0（输出治理 + 数据层候选入库）与 L1（juice-shop-zap 解析结果入库 → 证据 → 补天草稿）。
L2-L4 未开工。本次不提交 git；用户既有的 5 个文档改动保持原样。

## 1. 背景

v0.14.2 的真实断点：`PipelineRunner.run_external` 绕过阶段机，外部工具原始 stdout/stderr 全量进
`events` 表（凭据泄漏风险），且解析结果从不进 `findings` 表——`juice-shop-zap` 分支虽已调用
`parse_zap_report`，却只写 `zap_findings.json` 工件，平台永远"无 Finding"。本次补齐这两段。

## 2. 改动清单

| 文件 | 类型 | 内容 |
| --- | --- | --- |
| `src_auto/redaction.py` | 新增 | `redact_tool_output(value, limit=16000)`：掩码 authorization/cookie/set-cookie/token/secret/password/api_key 与 URL query 值，超长截断加 `[TRUNCATED]`；`decode_tool_bytes(raw, cap=1MiB)`：强制 UTF-8 replace 解码（不再走 Windows GBK _locale），字节上限截断 |
| `src_auto/finding_ingest.py` | 新增 | `ingest_zap_candidates(store, root, run_id, scope_guard, parsed, scanner_version)`：逐条重过 `ScopeGuard.decide`，出界丢弃并记 `finding_out_of_scope` 事件；入库候选 + `EvidencePackager` 最小证据；返回 inserted/merged/skipped/finding_count/fingerprints |
| `src_auto/store.py` | 修改 | `_migrate_findings()` 幂等加列（vuln_type/scanner/template_id/matched_at/confidence/cwe/cvss/sources_json）；新增 `insert_candidate()`：指纹 = stable_hash{vuln_type, 规范化 URL(去 query/fragment), parameter 小写}，冲突合并 sources_json（去重、上限 20）、severity/confidence 取最大、finding_runs upsert。**旧 `insert_finding` 一字未动** |
| `src_auto/adapters.py` | 修改 | `SafeToolAdapter.run` 去掉 `text=True`，stdout/stderr 经 `decode_tool_bytes`；TimeoutExpired 分支同样解码部分输出 |
| `src_auto/pipeline.py` | 修改 | `run_external` 事件 payload 形状不变（`{"tool","result"}`），result 内 stdout/stderr 截断脱敏 16000、detail 2000 后再入 events |
| `src_auto/cli.py` | 修改 | `juice-shop-zap` 成功分支：create_run(mode="juice-shop-zap") → ingest → `ButianReportGenerator` 草稿 → set_run_status("completed")；`--json` 新增 run_id/butian_report_path/ingest，finding_count 改为入库计数；原 artifact、report_path（ZAP json）、zh 字段不变 |
| `tests/test_finding_ingest.py` | 新增 | 18 个测试：迁移幂等与旧行保留、候选合并/分离/query 不分裂指纹、cvss 往返与来源上限 20、合并保留更高严重度、空 run_id、规范化 URL 回退与端口、旧 insert_finding 行为不变、脱敏/截断/解码/无主机与非法 URL/文本输入、适配器真实 subprocess 非法字节容错、ZAP ingest 端到端（出界丢弃/证据/报告/非映射条目）、CLI mock 端到端 |
| `tests/test_local_application_workflow.py` | 修改 | 仅 `wait_run`：增加 `not self.service.active` 条件，修复 HEAD 既存竞态（见 §6） |

`run-live`（run_external）返回值与失败即中止策略**保持不变**，避免破坏既有契约；
"工具失败部分完成也入库"与默认 sequence 裁剪推迟到 L2。

## 3. 数据迁移与回退

- 迁移在 `Store._init_schema` 内幂等执行：只加列、不改旧行、不删数据；重复打开无副作用（有测试）。
- 改动前备份：`data/backups/src_auto-20261118-094011.sqlite3`（278,528 字节，`PRAGMA integrity_check=ok`，79 条 findings）。
  备份早于任何真实库迁移；回退 = 停平台后用该文件覆盖 `data/src_auto.sqlite3`。
- 真实库 `data/src_auto.sqlite3` 尚未被新代码打开迁移；下次启动平台时自动加列。

## 4. 入库语义

- 指纹键：vuln_type（标题 slug）+ 规范化 URL（scheme/host/port/path，去 query 与 fragment）+ parameter（小写）。
  同一漏洞被两个扫描器报出 → 合并为一行，sources_json 保留全部来源；query 值变化不分裂指纹。
- 状态固定 `candidate`，triage.confirmed=false、submission_ready=false；**不自动提交补天**（POLICY 人工提交不变）。
- 出界 endpoint 在 ingest 层二次拒绝（parse_zap_report 已按 runtime policy 过滤一次），丢弃并留审计事件。
- 证据：每条新候选生成最小证据包（标题/URL/严重度/截断证据摘要），不含原始响应正文。

## 5. 验证证据（新鲜命令输出）

项目根目录执行，官方命令不带 `-t`：

| 命令 | 结果 |
| --- | --- |
| `py -3.12 -m unittest tests.test_finding_ingest` | Ran 18 tests — OK |
| `py -3.8 -m unittest tests.test_finding_ingest` | Ran 18 tests — OK |
| `py -3.12 -m coverage run -m unittest discover -s tests`（改动后全量） | Ran 604 tests in 138.838s — OK (skipped=1)，RUN_EXIT=0 |
| `py -3.8 -m unittest discover -s tests`（改动后全量） | Ran 604 tests in 135.855s — OK (skipped=1)，EXIT=0 |
| `py -3.12 -m coverage report`（pyproject 门禁 fail_under=68） | TOTAL 75%，REPORT_EXIT=0；finding_ingest 100%、redaction 100%、store 94%（剩余未覆盖行均为旧代码） |
| `py -3.12 -m unittest tests.test_local_application_workflow -v` | Ran 19 tests in 12.771s — OK |
| 基线（改动前，新测试暂移开）`py -3.12 -m unittest discover -s tests` | Ran 586 tests in 184.150s — errors=1, skipped=1（既存失败，见 §6） |

604 = 586 旧 + 18 新；唯一 skip 为 Windows symlink 条件跳过，与版本门禁一致。

覆盖率测量方式：本机 Python 3.12 的 user site 被禁用（`site.ENABLE_USER_SITE=False`），
`pip --user` 安装不可见；改为 `pip install --target <workspace>\pylibs coverage` 隔离安装，
仅测量进程设置 `PYTHONPATH` 与 `COVERAGE_FILE`（数据文件留在 workspace，不污染项目）。
首次 `--user` 误装入禁用 user site 的 coverage 目录已清理，其余用户包未动。

## 6. HEAD 既存失败与修复（与本次功能无关）

- 现象：`test_agent_passive_recipe_is_required_before_finish` 抛 `RuntimeError: agent_operation_conflict`
  （`local_application_workflow.py:329`）。
- 证明既存：`git worktree add --detach <临时目录> HEAD`（acf4574）单跑该测试同样失败；临时 worktree 已清理。
- 根因：测试 `wait_run` 只等 `reportId` 落盘，而 worker 线程清 `current_id` 在其后；循环内第二次
  `start` 撞上残留 `active`。属测试同步竞态，非生产逻辑缺陷。
- 修复：仅改测试 `wait_run`，加 `not self.service.active` 条件；修复后该测试类 19/19 OK，双版本全量绿。

## 7. 边界与推迟项（L2 起）

- 工具失败"部分完成也入库"策略、默认 sequence 裁剪、live_plan ALLOWED_TOOLS 中 reconftw 登记清理：L2。
- surface-plan 执行化 + httpx/katana → assets 快照/diff（复用 attack_surface 现成框架）：L2。
- nuclei 解析与 Docker runner（本机原生被端点安全阻止，不绕过）：L2，前置 Docker 状态检查。
- 报告增强/提交队列/Dashboard 字段：L3；真实目标出站/审批/会话：L4（需单独批准）。
- 本次未 commit；是否提交、以及用户 5 个文档改动的处置由用户决定。

## 8. 复现命令

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
py -3.12 -m unittest discover -s tests
py -3.8  -m unittest discover -s tests
py -3.12 -m unittest tests.test_finding_ingest -v
# 本地靶场闭环（需 Docker 与 pinned ZAP 就绪，仅 loopback）：
py -3.12 -m src_auto.cli juice-shop-zap --json
```
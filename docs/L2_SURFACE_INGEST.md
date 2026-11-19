# L2 落地报告：资产测绘入库、nuclei 候选、部分入库与 surface-plan 执行桥

日期：2026-11-18　分支：`agent/controlled-upgrade`（L0/L1 之后）
范围：L2 五个子项。L3/L4 未开工。本次不提交 git；用户既有文档改动保持原样。

## 1. 背景与改动清单

L0/L1 之后仍缺的：httpx/katana 侦察输出只进 events 不沉淀资产；nuclei 登记了却从不执行也无解析；
一个工具失败整轮作废；surface-plan 与 live-plan 之间缺三字段桥；reconftw 已禁用却仍在允许清单。

| 文件 | 类型 | 内容 |
| --- | --- | --- |
| `src_auto/surface_ingest.py` | 新增 | `parse_httpx_assets`/`parse_katana_assets`（JSONL→有界资产）、`parse_nuclei_candidates`（JSONL→候选）、`ingest_tool_output`（统一入口：仅 completed 工具入库；httpx/katana→save_asset_snapshot，nuclei→ingest_nuclei_candidates；出界丢弃+审计；无 parser 工具跳过） |
| `src_auto/finding_ingest.py` | 修改 | 提炼共享核心 `_ingest_candidates`（ScopeGuard 重检+insert_candidate+最小证据）；`ingest_zap_candidates` 行为/返回结构不变（L1 测试锁定）；新增 `ingest_nuclei_candidates` |
| `src_auto/pipeline.py` | 修改 | `run_external` 每个 completed 工具立即 ingest（聚合 assets/inserted/merged/skipped）；**失败改 `partial_tools`**：已完成工具结果保留入库，run 标记 partial_tools；`completed_tools`、默认序列常量、blocked_adapter、事件形状均不变 |
| `src_auto/nuclei_runner.py` | 新增 | `NucleiDockerRunner`：fail-closed。docker.exe 缺失/CLI 哈希不匹配/daemon 未就绪/镜像未 pin 或漂移 → blocked 不起容器；固定 `--pull never --cap-drop ALL`；容器自清理 rm -f；不绕过端点安全 |
| `src_auto/attack_surface.py` | 修改 | `AttackSurfacePlan` 增加 operator/authorization_note/manual_execution_confirmed（默认空/False）；`to_mapping` 输出三字段，使 surface-plan JSON 可直接喂 `validate_live_plan` |
| `src_auto/cli.py` | 修改 | `surface-plan` 新增 `--operator`/`--authorization-note`/`--manual-execution-confirmed`；声明确认时必须同时给 operator+note，否则 BLOCKED |
| `src_auto/live_plan.py` | 修改 | `ALLOWED_TOOLS` 移除 reconftw（lock 中 intentionally-disabled） |
| `tests/test_surface_ingest.py` | 新增 | 13 个测试：三解析器、出界丢弃、证据、跨扫描器合并、run_external 成功/部分入库、plan 桥接 validate、reconftw 拒绝、runner fail-closed 与固定容器 argv+自清理 |

## 2. 关键语义

- **跨扫描器归一**：nuclei 的 matcher-name 是匹配器不是注入参数，不进指纹 parameter（置空，留在 evidence），
  否则同一漏洞 ZAP/nuclei 无法合并。合并后 sources_json 同时含 nuclei 与 zap，严重度取最大。
- **部分入库**：只有 completed 工具的输出被 ingest；失败/超时工具不 ingest，但此前 completed 工具的资产/候选保留，
  run=partial_tools，逐工具状态在 stages。ingest 自身异常不丢工具结果，记 tool_ingest_failed。
- **执行门不变**：三字段桥只是让 surface-plan 输出能被 live-plan 消费；`validate_live_plan` 仍只校验类型，
  真正执行仍需 policy allow_real_targets、confirmed scope、manual_execution_confirmed=True 与 `--execute-live` 四道门。
- **资产差异**：复用 store.snapshot_assets/diff_assets；`render_asset_diff_report(previous,current)` 输出 added/removed/unchanged 与 manual_review_required 判定。

## 3. Docker 前置（未满足，如实披露）

实测 `docker version`/`docker info` 均失败：Docker Desktop 未启动（npipe 不存在）。按 AGENTS「START 人工、不建后台守护」
约定，未自行启动。nuclei runner 因此在真实环境会 fail-closed 返回 blocked（docker_not_ready / docker_binary_missing），
解析与 argv/自清理逻辑已用 mock 测试验证，**真实容器执行未验证**，需人工启动 Docker Desktop 后复测。

## 4. 验证证据（新鲜命令输出）

项目根目录执行：

| 命令 | 结果 |
| --- | --- |
| `py -3.12 -m unittest tests.test_surface_ingest -v` | Ran 13 tests — OK（初跑 12/13，跨扫描器合并失败后修 parameter 语义转绿） |
| `py -3.12 -m unittest tests.test_surface_ingest tests.test_finding_ingest tests.test_live_plan tests.test_failures tests.test_attack_surface tests.test_upgrade_cli` | Ran 49 tests — OK |
| `py -3.12 -m coverage run -m unittest discover -s tests`（全量） | 见 §5 最终值 |
| `py -3.8 -m unittest discover -s tests`（全量） | 见 §5 最终值 |

## 5. 全量回归与覆盖率（最终值）

| 项 | 结果 |
| --- | --- |
| 3.12 全量（带覆盖率） | **Ran 617 tests in 113.962s — OK (skipped=1)**，RUN_EXIT=0 |
| 3.8 全量 | **Ran 617 tests in 98.171s — OK (skipped=1)**，EXIT=0 |
| 覆盖率门禁 fail_under=68 | **TOTAL 75%**，REPORT_EXIT=0 |
| 新增/改动模块覆盖率 | finding_ingest **100%**、surface_ingest **90%**、pipeline 88%、nuclei_runner 74%（未覆盖行均为真实 Docker 异常分支，mock 不到，见 §3） |

617 = L0/L1 后 604 + L2 新增 13。唯一 skip 为 Windows symlink 条件跳过。

## 6. 边界与推迟项

- run-live 的 ZAP 输出仍走 juice-shop-zap 独立闭环，不在 run_external 重复 ingest（no_parser 跳过）。
- 真实外部目标出站、审批、会话属 L4，未开工；报告增强/提交队列/Dashboard 字段属 L3。
- 资产 diff 报告需两次 run 的 run_id；自动选取"上一次同目标 run"未做（显式传参）。
- 本次未 commit；是否提交由用户决定。

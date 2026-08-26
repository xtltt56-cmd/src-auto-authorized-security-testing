# Hybrid Task Visualization Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan phase-by-phase, and load each linked detailed plan before changing code.

**Goal:** Upgrade SRC-Auto into a dependable Chinese desktop platform where a user can enter and approve a target, observe every automated stage in real time, review evidence and reports locally, and retain human control over final vulnerability confirmation and 补天 submission.

**Architecture:** Keep the security engine, scope controls, local labs, and report assets as the system of record. Add a durable typed task-event layer, expose it through a loopback-only FastAPI/SSE service, render it in a code-first React dashboard governed by local visual tokens and browser acceptance, and host that dashboard in a locked-down WebView2 WPF shell. Local-lab workflows are migrated and accepted before the separately gated authorized-target workflow is enabled.

**Tech Stack:** Project-local Python 3.12, FastAPI, SSE, SQLite + JSONL, React/TypeScript/Vite, Chart.js, Playwright, .NET 8 WPF, WebView2, pytest, xUnit, Pester, existing Docker local labs and scanner adapters.

---

## 1. Final product boundary

The upgraded product is named:

> **SRC-Auto 授权安全测试编排与候选漏洞研判平台**

It is not a fully autonomous bounty bot. Its controlled workflow is:

```text
人工录入目标与补天规则
        ↓
人工确认授权范围、时间窗、自动化许可和请求预算
        ↓
系统自动编排获准的低风险检测与证据整理
        ↓
实时展示计划、执行、阻断、发现、日志和报告
        ↓
人工复核候选漏洞、影响和证据
        ↓
人工登录补天并提交
```

Local labs remain the default and the only acceptance-test destination. Real targets are never contacted during development or automated testing.

## 2. Design authority and source documents

Implementation must follow these documents in order:

1. [Hybrid visualization design specification](../specs/2026-08-26-hybrid-task-visualization-design.md)
2. [Task event core plan](2026-08-26-task-event-core.md)
3. [Realtime dashboard plan](2026-08-26-realtime-dashboard.md)
4. [WebView2 desktop shell plan](2026-08-26-webview2-desktop-shell.md)
5. [Authorized target progress plan](2026-08-26-authorized-target-progress.md)

If a detailed plan conflicts with the design specification, stop implementation, update the specification through review, and then update every affected plan. Do not silently choose one interpretation.

## 3. Code-first visual package before frontend implementation

The user explicitly asked to abandon the Figma freeze and start the visual upgrade. No new React page may be implemented until the code-first specification and component inventory are recorded in `docs/superpowers/specs/2026-08-26-code-first-visual-upgrade.md`. Existing Figma/PNG files remain visual references only. The local package covers these desktop screens and states:

1. **任务总览** — active/history tasks, type, state, stage, progress, elapsed time, counters.
2. **本地五靶场启动** — lab health, selected validations, resource status, clear local-only badge.
3. **任务实时详情** — overall progress, stage rail, event timeline, live logs, finding counters, controls.
4. **靶场矩阵** — five lab cards, individual state, duration, findings, report link.
5. **授权目标录入** — project/rules, URL, hosts, ports, exclusions, window, methods, budgets.
6. **授权确认** — immutable summary, digest suffix, risk notice, explicit consent action.
7. **阻断与边界解释** — blocked URL/action, policy reason, next safe action; no bypass button.
8. **结果与报告** — candidates, scanner evidence, independent verdict, report file viewer.
9. **任务历史与恢复** — interrupted tasks, recovery decision, event export, audit trail.
10. **设置** — local/remote AI opt-in, key status without value, runtime status, storage locations.
11. **桌面启动/错误/重试** — backend startup, WebView2 missing, browser fallback, legacy fallback.
12. **DPI/minimum-window variants** — 100%, 125%, 150%, 200% and the minimum supported window.

The component-to-code map, tokens, fixture data, and comparison screenshots must be recorded under `docs/design` and `docs/validation`. No key, target, finding, or real report data may be placed in a visual artifact.

## 4. Phase 0 — Baseline, backups, and design approval

**Purpose:** Freeze the current evidence before changing runtime or UI behavior.

**Actions:**

1. Record branch, commit, dirty-worktree inventory, Python/Docker/WebView2 versions, and five-lab availability.
2. Run the existing unit suite and canonical local five-lab validation without changing target configuration.
3. Export current launcher and GUI screenshots at 100%, 125%, 150%, and 200% scaling.
4. Create a project-local recovery bundle containing source-controlled files, dependency manifests, fixture hashes, and restore instructions; exclude secrets, databases, reports, and generated evidence.
5. Complete and record the code-first package described above. Figma synchronization is optional and does not block implementation.
6. Create `codex/task-visualization` from a clean, reviewed checkpoint or use an isolated worktree under the D-drive project tree.

**Gate G0:**

- baseline results and known failures are recorded;
- no secret or user report is staged;
- code-first visual package is recorded and its local interaction gate is approved;
- rollback command and legacy launcher are documented;
- implementation branch/worktree is explicit.

No production code changes may begin before G0 passes.

## 5. Phase 1 — Durable task and event core

Execute [2026-08-26-task-event-core.md](2026-08-26-task-event-core.md) completely.

**Primary outputs:**

- typed `TaskState` and `TaskEvent` models;
- SQLite `task_runtime` records and ordered event cursors;
- append-only redacted JSONL event export;
- one orchestrator for pause, resume, cancel, recovery, and terminal states;
- a five-lab adapter around the current canonical validator;
- a CLI proving the event flow independently of any UI.

**Gate G1:**

```text
event_sequence_gaps = 0
terminal_state_count_per_task = 1
secrets_in_event_artifacts = 0
external_targets_contacted = 0
existing_regression_failures = 0 beyond recorded baseline
```

Do not start the dashboard until G1 passes.

## 6. Phase 2 — Loopback API and realtime browser dashboard

Execute [2026-08-26-realtime-dashboard.md](2026-08-26-realtime-dashboard.md) completely.

**Primary outputs:**

- project-local Python 3.12 and Node runtime under `runtime`;
- FastAPI REST and resumable SSE service bound only to a random loopback port;
- session authentication and origin validation;
- code-first Chinese React dashboard matching the recorded visual tokens and reference mockups;
- live task timeline, stages, counters, logs, five-lab matrix, history, recovery, and report viewer;
- Playwright coverage for primary and failure journeys.

**Gate G2:**

- backend and frontend tests pass;
- SSE reconnect resumes from the last event cursor without duplicate state transitions;
- all report links open through a safe allowlisted file-view endpoint;
- browser console has no unhandled errors;
- frontend makes zero third-party requests;
- local five-lab task is visible from creation to terminal state;
- screenshots pass the local visual ledger and minimum-window checks.

Do not make the browser dashboard the default launcher until G2 passes.

## 7. Phase 3 — WebView2 one-click desktop shell

Execute [2026-08-26-webview2-desktop-shell.md](2026-08-26-webview2-desktop-shell.md) completely.

**Primary outputs:**

- self-contained WPF/WebView2 shell;
- secure backend process supervision and session handshake;
- exact-origin navigation policy and disabled downloads/new windows;
- browser and legacy GUI fallback paths;
- updated desktop shortcut;
- DPI, crash recovery, orphan-process, and packaging evidence.

**Gate G3:**

```text
successful_launch_exit_cycles = 5/5
orphan_backend_processes = 0
external_navigation_attempts_allowed = 0
secret_values_in_process_or_url = 0
dpi_primary_controls_clipped = 0
browser_fallback = pass
legacy_fallback = pass
```

Only after G3 may the WebView2 shell become the default desktop experience.

## 8. Phase 4 — Human-gated authorized target progress

Execute [2026-08-26-authorized-target-progress.md](2026-08-26-authorized-target-progress.md) completely.

**Primary outputs:**

- immutable authorization snapshot and hash;
- save-without-network target draft flow;
- short-lived single-use human confirmation;
- exact scope/window/method/budget checks before every request and redirect;
- Chinese authorization, progress, block, and evidence screens;
- loopback Business API simulation of the full authorized workflow;
- safety matrix for expiry, scope drift, redirect escape, pause/cancel, and restart.

**Gate G4:**

```text
draft_network_side_effects = 0
scope_checks_before_requests = 100%
redirect_checks_before_follow = 100%
external_targets_contacted = 0
destructive_actions_executed = 0
automatic_submissions = 0
unredacted_secrets_in_artifacts = 0
```

G4 proves the workflow using local fixtures; it does not authorize testing a real target.

## 9. Phase 5 — Stabilization, documentation, and release candidate

**Files:**

- Create: `tools/run_release_acceptance.ps1`
- Create: `docs/validation/release-acceptance.md`
- Create: `docs/部署与恢复手册.md`
- Modify: `docs/使用手册.md`
- Modify: `README.md`

**Step 1: Add one release acceptance command**

It must run, in order:

1. secret and forbidden-artifact scan;
2. Python lint/type/unit/integration suites;
3. frontend type/component/build/Playwright suites;
4. .NET unit/build tests;
5. PowerShell launcher/package tests;
6. canonical five-lab validation;
7. local authorized-target simulation;
8. five launch/exit cycles;
9. report/evidence link verification;
10. machine-readable acceptance summary generation.

**Step 2: Run acceptance from a fresh project-local runtime**

```powershell
.\tools\run_release_acceptance.ps1 -RecreateRuntime
```

Do not reuse developer caches as proof of reproducibility.

**Step 3: Verify restoration**

Restore into a separate D-drive test directory from the repository plus documented runtime/bootstrap steps. Prove that the launcher, dashboard, five local labs, reports, and local authorized simulation work without copying the original runtime state or secrets.

**Step 4: Complete the manuals**

The final documentation must cover:

- installation and D-drive directory layout;
- one-click startup and all fallbacks;
- local five-lab training flow;
- authorized target transcription and confirmation;
- live progress, pause/cancel/recovery, report viewing, and event export;
- AI provider opt-in rules and secure key storage;
- manual candidate review and 补天 submission;
- backup, GitHub restore, local runtime recreation, and emergency rollback;
- known limitations and explicitly unsupported actions.

**Gate G5:**

- all automated suites pass or every baseline exception is explicitly documented and accepted;
- five-lab validation produces exact reproducible per-lab results;
- restore test succeeds in a clean D-drive directory;
- no secret, database, user report, target configuration, or generated evidence is committed;
- default launcher is the new desktop shell and both fallback modes remain usable;
- final acceptance report is reviewed by the user before any real authorized target is entered.

## 10. Dependency and reuse policy

Before implementing each subsystem, verify the current primary repository and release status of the selected dependency. Prefer these mature building blocks:

- Microsoft WebView2 official WPF sample and NuGet package for desktop embedding;
- FastAPI official response/security patterns and `sse-starlette` for event streaming;
- React/Vite and Chart.js for the local dashboard;
- Playwright for browser journeys;
- the existing SRC-Auto `Store`, `ScopeGuard`, `runtime_policy`, `live_plan`, and five-lab validator;
- existing ZAP/Nuclei-compatible adapters only through argument-safe wrappers and the common scope gate.

Vendored source copies require license review, pinned commit/tag, hash, and update procedure. Do not copy an entire third-party platform into the repository merely to reuse one component. New dependencies must be recorded with version, license, source URL, hash or lockfile, and purpose.

## 11. Acceptance matrix

| Capability | Unit | Integration | UI/E2E | Safety proof | Release evidence |
|---|---:|---:|---:|---:|---:|
| Task state/events | Yes | Yes | Yes | Redaction/order | JSONL + DB summary |
| Five local labs | Adapter | Five-lab runner | Dashboard | Loopback only | Per-lab exact results |
| Pause/resume/cancel | State machine | Process adapter | Controls | No post-stop actions | Timeline export |
| Report viewer | Path policy | File endpoint | Click/open | Project-root allowlist | Link audit |
| SSE reconnect | Cursor logic | Restart/reconnect | Browser | No cross-session stream | Reconnect log |
| Desktop shell | Policy/service | Startup/crash | DPI/manual | Exact origin | Five-cycle report |
| Authorized draft | Validation | API | Form | Zero network | Spy assertion |
| Human confirmation | Nonce/hash | Session binding | Dialog | Replay rejected | Audit event |
| Request enforcement | Scope/budgets | Local simulator | Progress | Every request/redirect | Safety matrix |
| AI opt-in | Config | Provider stub | Settings | Disabled means zero calls | Network assertion |
| Submission boundary | N/A | N/A | No control | Always manual | Manual statement |

## 12. Rollback strategy

Every gate ends with a commit and an evidence document. If a later phase fails:

1. stop the new local backend and desktop shell;
2. launch `START_SYSTEM.ps1 -LegacyGui`;
3. retain the new database tables but do not delete or rewrite old data;
4. disable the new entry point through configuration, not by deleting code;
5. diagnose on the implementation branch/worktree;
6. rerun the prior gate before resuming.

Never use `git reset --hard`, delete the workspace, or overwrite user-generated reports as a rollback mechanism.

## 13. Final definition of done

The overall upgrade is complete only when all five gates pass and the evidence proves:

- the UI is clear, fully clickable, high-DPI safe, and Chinese-first;
- the task process is observable at stage, event, log, finding, and report levels;
- local five-lab workflows are reproducible and report exact results;
- authorized target drafts are inert until a human confirms the exact scope;
- every permitted network action is bounded and visible;
- pause, cancel, recovery, and failure paths are reliable;
- remote AI remains opt-in per session and makes zero calls when disabled;
- secrets and sensitive artifacts remain local and uncommitted;
- the user performs final vulnerability confirmation and 补天 submission manually;
- the project can be restored from GitHub plus documented D-drive bootstrap steps.

# SRC-Auto Three-Phase Platform Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved three-phase SRC-Auto upgrade with curated tools, business-logic assistance, defensive monitoring, upgraded local labs, a polished Simplified Chinese desktop console, and verified documentation.

**Architecture:** Keep SRC-Auto as a fail-closed Python control plane and call mature tools only through small adapters. Store all dependencies and artifacts below the project root, normalize all outputs before persistence, and keep real-target execution behind the existing human-confirmed scope and plan gates.

**Tech Stack:** Python 3.8-compatible standard library, SQLite, Windows PowerShell 5.1 WinForms, Docker Compose local labs, ProjectDiscovery tools, OWASP ZAP, BBOT, Schemathesis, unittest.

---

### Task 1: Freeze the baseline and define curated tool profiles

**Files:**
- Create: `src_auto/tool_profiles.py`
- Create: `config/integrations/tool_profiles.json`
- Modify: `src_auto/adapters.py`
- Modify: `src_auto/cli.py`
- Test: `tests/test_tool_profiles.py`

- [ ] Write failing tests proving every profile has a fixed identifier, safe role, invocation mode, allowed capabilities, and project-local command path.
- [ ] Run `python -m unittest tests.test_tool_profiles -v` and confirm the missing module/profile failure.
- [ ] Implement `ToolProfile`, `load_tool_profiles()`, `project_tool_search_paths()` and status normalization; add BBOT, Schemathesis and testssl without treating discovery tools as vulnerability scanners.
- [ ] Run the focused tests and the existing adapter tests.
- [ ] Record version/source/checksum/status in `tools.lock.yaml` without changing verified existing hashes.

### Task 2: Install and verify mature tools under vendor

**Files:**
- Create: `tools/install_curated_tools.ps1`
- Create: `vendor/README.md`
- Modify: `tools.lock.yaml`
- Test: `tests/test_curated_tool_installer.py`

- [ ] Write failing contract tests requiring project-local cache/temp paths, pinned packages, checksum verification for release archives, and no antivirus/firewall bypass.
- [ ] Run the installer contract tests and confirm failure.
- [ ] Implement the installer for Nuclei, BBOT, Schemathesis and testssl.sh; prefer official release/archive or isolated venv and retain Docker as Nuclei fallback when endpoint protection blocks the executable.
- [ ] Execute the installer, capture actual versions and hashes, and never report an unavailable tool as installed.
- [ ] Run `python -m src_auto tool-status --json` and persist the fresh status report under `validation/tools/`.

### Task 3: Add phase-one attack-surface planning and snapshot reports

**Files:**
- Create: `src_auto/attack_surface.py`
- Modify: `src_auto/store.py`
- Modify: `src_auto/cli.py`
- Test: `tests/test_attack_surface.py`

- [ ] Write failing tests for domain normalization, authorization-required plans, safe template/tag allowlists, request-rate ceilings, redirect scope checks and asset diffs.
- [ ] Confirm the tests fail because the module and commands do not exist.
- [ ] Implement `AttackSurfaceTarget`, `AttackSurfacePlan`, `build_attack_surface_plan()`, `save_asset_snapshot()` and `render_asset_diff_report()`.
- [ ] Add CLI commands `surface-plan`, `surface-snapshot` and `surface-diff`; plan generation remains offline and execution requires the existing explicit live confirmation.
- [ ] Verify against loopback fixtures only and run all scope/store tests.

### Task 4: Add phase-two encrypted sessions and authorization comparison

**Files:**
- Create: `src_auto/session_vault.py`
- Create: `src_auto/business_logic.py`
- Modify: `src_auto/cli.py`
- Test: `tests/test_session_vault.py`
- Test: `tests/test_business_logic.py`

- [ ] Write failing tests for DPAPI-bound encrypted session storage, redacted listings, project-path enforcement and deletion of individual profiles.
- [ ] Write failing tests for GET/HEAD-only defaults, explicit mutation blocking, no sequential ID generation, normalized JSON comparison, role matrices and candidate-only verdicts.
- [ ] Implement `SessionVault`, `RequestTemplate`, `ResponseSnapshot`, `AuthorizationCase`, `compare_responses()` and `evaluate_authorization_matrix()`.
- [ ] Add offline CLI commands for session metadata, API request import, response comparison and matrix report generation; no command may print credentials.
- [ ] Validate the response-comparison workflow with local deterministic fixtures.

### Task 5: Add Schemathesis integration and safe local API lab

**Files:**
- Create: `lab/business-api/app.py`
- Create: `lab/business-api/openapi.json`
- Modify: `docker-compose.local-labs.yml`
- Modify: `src_auto/local_labs.py`
- Create: `config/labs/business-api.json`
- Test: `tests/test_business_api_lab.py`

- [ ] Write failing tests for a loopback-only fourth lab, fixed image/build context, health check, documented test accounts, intentional horizontal-authorization fixture and safe reset behavior.
- [ ] Implement a small deterministic local API fixture with account-owned objects and OpenAPI documentation; bind it only to `127.0.0.1:8084` because the existing VAmPI lab occupies `127.0.0.1:8083`.
- [ ] Add the lab to lifecycle/status code and add a Schemathesis smoke-plan that targets only its OpenAPI document.
- [ ] Start Docker, validate health, and run only bounded local tests; do not run aggressive RESTler fuzzing.
- [ ] Save ground truth and comparison evidence under `validation/business-api/`.

### Task 6: Add phase-three owned-asset and defensive log analysis

**Files:**
- Create: `src_auto/defense.py`
- Create: `src_auto/log_analysis.py`
- Modify: `src_auto/cli.py`
- Test: `tests/test_defense.py`
- Test: `tests/test_log_analysis.py`

- [ ] Write failing tests proving an entered domain remains pending until authorization/ownership evidence exists and that third-party redirects never enter the plan.
- [ ] Write failing tests for bounded Nginx/Wazuh/Zeek/Suricata JSON import, path containment, credential redaction, event aggregation and recommendation-only responses.
- [ ] Implement `OwnedAssetProfile`, `build_defensive_plan()`, `AssetChange`, `DefensiveEvent`, `parse_defensive_log()` and `summarize_defensive_events()`.
- [ ] Add offline CLI commands `defense-register`, `defense-plan`, `defense-import-log` and `defense-report`.
- [ ] Validate with project-local synthetic logs only.

### Task 7: Redesign and connect the Simplified Chinese desktop console

**Files:**
- Modify: `tools/src_auto_gui.ps1`
- Modify: `START_SYSTEM.ps1`
- Create: `docs/design/src-auto-main-console-fidelity.md`
- Modify: `tests/test_desktop_gui.py`
- Test: `tests/test_desktop_workflows.py`

- [ ] Write failing GUI contract tests for the eight navigation labels, three primary actions, tool health, business-logic window, defensive-domain form, local-lab status view and help entry.
- [ ] Add automatic click probes proving every primary navigation button resolves its handler and opens a closable window.
- [ ] Implement the design system from `docs/design/src-auto-main-console-concept-v1.png`: true-white workspace, navy navigation, cobalt actions, explicit health/warning states and readable Chinese typography.
- [ ] Connect forms to offline CLI/status commands; keep real-target execution absent from the home screen.
- [ ] Launch the GUI, capture an actual screenshot, inspect it with the concept, and record at least five fidelity comparisons.

### Task 8: Upgrade local-lab guidance and one-click acceptance

**Files:**
- Modify: `tools/src_auto_gui.ps1`
- Modify: `tools/run_local_lab_validation.py`
- Modify: `tools/run_local_regression.py`
- Modify: `START_SYSTEM.ps1`
- Test: `tests/test_local_lab_dashboard.py`

- [ ] Write failing tests for per-lab status, start/stop/open/validate actions, progress text, clear explanations and fourth-lab inclusion.
- [ ] Implement a local-lab dashboard that never asks for target domains and only opens fixed loopback URLs.
- [ ] Make validation output summarize environment readiness, discovery, controlled findings, adjudication and stability without claiming bounty success.
- [ ] Run two repeat rounds and save exact scores and blockers.

### Task 9: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `OPERATIONS.md`
- Modify: `USER_MANUAL.md`
- Modify: `KNOWN_ISSUES.md`
- Modify: `TEST_REPORT.md`
- Create: `THREE_PHASE_UPGRADE_REPORT.md`

- [ ] Update the complete Simplified Chinese manual with first-run, target authorization, business-logic, defense, local-lab, AI-consent, troubleshooting and safe-stop workflows.
- [ ] Run the full unittest suite, PowerShell parser checks, UTF-8/BOM checks, tool status, Docker Compose configuration, lab health, local validation and local regression.
- [ ] Compare every approved design requirement with implementation evidence and list any environment-dependent capability honestly.
- [ ] Save exact commands, exit codes, test counts, tool versions, lab scores and screenshot paths in the final report.

## Current execution status (2026-08-26)

The implementation follows the plan's control boundaries and has completed the code-level work for Tasks 1–8 plus the documentation and verification work in Task 9. The deterministic business API was added as a fifth fixed loopback lab on port `8084` (the plan's original `8083` was already occupied by VAmPI). The phase-three owned-asset registration and defensive JSONL analysis are recommendation-only and keep authorization pending until a human supplies evidence. The desktop console exposes the planned Chinese navigation, target/authorization, session/API review, local-lab, defensive-observation and audit-stop workflows; it never starts a real-target scan from the home screen.

The current verification evidence is `238/238` Python tests, `12/12` PowerShell scripts parsed without errors, a successful Docker Compose configuration check, five healthy loopback labs, `AUTHORIZED_LOCAL_VALIDATION_READY`, and `30/30` independent local-regression checks across three rounds. The GUI suite now includes a real WinForms report-selection preview regression. A transient Docker engine outage was recorded and recovered; the history and recovery commands are retained in `validation/business-api/DOCKER_RUNTIME_BLOCKER.md`. The business API OpenAPI contract also received the stable `x-src-auto.lab_id=business-api` marker required by the regression assertion. No remote AI call, external target contact or automatic submission occurred in this round.

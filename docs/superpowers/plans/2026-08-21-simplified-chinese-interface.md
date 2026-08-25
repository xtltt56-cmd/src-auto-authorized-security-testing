# Simplified Chinese Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the operator-facing SRC-Auto interface and documentation Simplified Chinese-first while preserving existing English machine fields, exit codes, and security gates.

**Architecture:** Add a small `src_auto/i18n.py` mapping/formatting module. The CLI will keep JSON as the automatic output when stdout is piped or `--json` is selected, and show a Chinese human summary when attached to an interactive terminal or when `--human` is selected. JSON documents gain optional `status_zh`/`reason_zh` fields without renaming existing keys. The PowerShell launcher and documentation will use fixed Chinese text; third-party tool stdout/stderr remains bounded and redacted.

**Tech Stack:** Python 3.8 standard library (`argparse`, `json`, `sys`, `os`), PowerShell 5+, existing `unittest` suite, Markdown documentation.

---

### Task 1: Add failing localization contract tests

**Files:**
- Create: `tests/test_i18n.py`
- Modify: `tests/test_juice_shop_cli.py`
- Modify: `tests/test_launcher.py`

- [x] **Step 1: Write the failing tests**

Add tests that define the public behavior before the implementation exists:

```python
from src_auto.i18n import reason_zh, status_zh, with_zh_fields

def test_known_status_and_reason_have_simplified_chinese_text():
    assert status_zh("reachable") == "可访问"
    assert reason_zh("confirm_local_required") == "需要明确确认本机靶场"

def test_unknown_values_fall_back_without_changing_machine_value():
    assert status_zh("future_status") == "future_status"
    assert reason_zh("future_reason") == "future_reason"

def test_zh_fields_preserve_machine_fields():
    document = with_zh_fields({"status": "POSSIBLE_FINDINGS", "reason": "manual_verification_required"})
    assert document["status"] == "POSSIBLE_FINDINGS"
    assert document["status_zh"] == "存在待人工复核的可能项"
    assert document["reason_zh"] == "需要人工复核后才能确认"
```

Extend the CLI tests with one interactive human-output case that patches `sys.stdout.isatty` to return `True`, calls `cli.main(["juice-shop-status"])` with the existing probe/dependency fakes, and asserts the output contains `本地 OWASP Juice Shop` and `状态：可访问`. Extend the launcher contract test to require Chinese phrases such as `仅本机回环靶场` and `正在执行本地发现基线` while still requiring `127.0.0.1:3000` and rejecting `-p 0.0.0.0`.

- [x] **Step 2: Run the focused tests and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_i18n tests.test_juice_shop_cli tests.test_launcher -v
```

Expected result: import failure for `src_auto.i18n` and/or assertion failures for the new Chinese output checks. Existing unrelated tests should not be changed to accommodate the failure.

### Task 2: Implement the localization module

**Files:**
- Create: `src_auto/i18n.py`
- Test: `tests/test_i18n.py`

- [x] **Step 1: Implement minimal mappings and safe document enrichment**

Implement these public functions with Python 3.8-compatible typing:

```python
def status_zh(value: Any) -> str:
    """Translate a known machine status; return the original value when unknown."""

def reason_zh(value: Any) -> str:
    """Translate a known machine reason; return the original value when unknown."""

def message(key: str, **values: Any) -> str:
    """Format a fixed operator message and fall back to the key when unmapped."""

def with_zh_fields(document: Any) -> Any:
    """Copy a mapping/list and add status_zh/reason_zh without changing machine fields."""
```

Include the existing states and reasons used by `cli.py`, Juice Shop, remote AI, and the launcher (`reachable`, `unreachable`, `blocked_scope`, `POSSIBLE_FINDINGS`, `COMPLETED_DISCOVERY_ONLY`, `BLOCKED_DEPENDENCY`, `SCAN_FAILED`, `NOT_RUN`, `created`, `completed`, `stopped`, `blocked_confirmation`, `blocked_runtime`, `blocked_output`, `blocked_policy`, `blocked_plan`, `blocked_provider`, `error`, `failed`, `manual_verification_required`, `vulnerability_scanners_not_run`, `juice_shop_unreachable`, `confirm_local_required`, `remote_llm_disabled_by_runtime`, `allow_real_targets_is_false`, and `stop_requested`). Unknown values must remain visible in English so a new status cannot silently look successful.

- [x] **Step 2: Run the focused localization tests**

Run:

```powershell
python -m unittest tests.test_i18n -v
```

Expected result: all localization tests pass.

### Task 3: Add CLI output modes and Chinese summaries

**Files:**
- Modify: `src_auto/cli.py`
- Modify: `tests/test_juice_shop_cli.py`
- Modify: `tests/test_remote_cli.py`

- [x] **Step 1: Add failing mode/compatibility tests**

Add tests asserting that `build_parser()` accepts `--json` and `--human` after a subcommand, that a captured/non-TTY invocation remains valid JSON with `status_zh`/`reason_zh`, and that an interactive invocation prints Chinese text without changing its exit code. Add a regression assertion that `remote-status --json` remains parseable JSON and still reports `network_contact: false`.

- [x] **Step 2: Verify the new CLI tests fail**

Run:

```powershell
python -m unittest tests.test_juice_shop_cli tests.test_remote_cli -v
```

Expected result: argparse rejects the new flags or the expected Chinese fields/summary are absent.

- [x] **Step 3: Implement the smallest compatible output layer**

Add `--json` and `--human` to every subparser through one helper. Resolve mode in `main()` as follows: explicit `--json` wins; explicit `--human` wins next; otherwise use human mode only when `sys.stdout.isatty()` is true, and JSON mode when stdout is piped/captured. This keeps `START_SYSTEM.ps1 | ConvertFrom-Json` and existing tests safe.

Update `_json()` to enrich mapping results with `with_zh_fields()` before serializing in JSON mode. Add a command-aware `human_summary(command, value)` in `src_auto/i18n.py` that only prints safe fields: target, status, status_zh, reason_zh, counts, artifact/report paths, provider/model names, and sanitized Finding titles/endpoints. Never print raw API keys, cookies, tokens, passwords, or unbounded tool stdout in a human summary.

Use Chinese argparse descriptions and help for all existing commands, while retaining command names and flags. Preserve every existing exit code and the original English JSON keys/enum values.

- [x] **Step 4: Run the CLI tests and the complete suite**

Run:

```powershell
python -m unittest tests.test_juice_shop_cli tests.test_remote_cli -v
python -m unittest discover -s tests -v
```

Expected result: focused tests and all existing tests pass; captured output remains valid JSON and interactive output includes Chinese summaries.

### Task 4: Localize the desktop launcher

**Files:**
- Modify: `START_SYSTEM.ps1`
- Test: `tests/test_launcher.py`

- [x] **Step 1: Replace operator-facing fixed strings with Simplified Chinese**

Translate startup, Docker readiness, Juice Shop reachability, baseline, Ollama, run creation, Findings/report display, success, failure, and close prompts. Keep executable paths, Docker arguments, target URL, and `-NoExit` behavior unchanged. Add a visible warning that the mode is “仅本机回环靶场，不接触真实目标”.

- [x] **Step 2: Verify the launcher contract**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected result: Chinese safety phrases are present, the exact loopback mapping remains, and no public bind is introduced.

### Task 5: Update Chinese documentation and examples

**Files:**
- Modify: `README.md`
- Modify: `USER_MANUAL.md`
- Modify: `JUICE_SHOP_VALIDATION_REPORT.md`
- Modify: `IMPLEMENTATION_REPORT.md`
- Modify: `KNOWN_ISSUES.md`
- Modify: `TEST_REPORT.md`

- [x] **Step 1: Add a Chinese feature and command guide**

Document the platform modules, normal workflow, local-only safety boundary, status meanings, artifacts, model options, manual DeepSeek flow, STOP/RESUME, common failures, and the distinction between `POSSIBLE`, `CONFIRMED`, `NOT_RUN`, and `BLOCKED_*`. Show both the desktop shortcut and direct PowerShell commands. State clearly that ZAP candidates are not automatically bounty submissions.

- [x] **Step 2: Document output compatibility**

Explain that interactive terminals show Chinese summaries, while piped output or `--json` remains machine-readable JSON with stable English fields plus optional `_zh` fields. Keep the current D-drive paths and C-drive system-component exception accurate.

- [x] **Step 3: Check documentation for stale English-only instructions**

Search the six files for old “Docker unavailable”, “ZAP version-only”, and “WSL not installed” claims; preserve historical snapshots only where they are explicitly labelled as historical.

### Task 6: Final verification and handoff

**Files:**
- Verify: `src_auto/i18n.py`, `src_auto/cli.py`, `START_SYSTEM.ps1`, all tests and documentation above

- [x] **Step 1: Run full verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src_auto lab tests
$errors = @(); Get-ChildItem -Recurse -File -Filter '*.json' | Where-Object { $_.FullName -notlike '*\vendor\zap\ZAP_2.17.0\data\reports\*' } | ForEach-Object { try { Get-Content -Raw $_.FullName | ConvertFrom-Json | Out-Null } catch { $errors += $_.FullName } }; if($errors.Count){ $errors; exit 1 }
git diff --check
```

Expected result: all tests pass, compilation succeeds, project JSON artifacts parse, and `git diff --check` reports no new whitespace errors.

- [x] **Step 2: Run the real local smoke checks**

Run:

```powershell
$env:Path = "C:\Users\lenovo\AppData\Local\Programs\DockerDesktop\resources\bin;$env:Path"
python -m src_auto juice-shop-status --human
python -m src_auto juice-shop-baseline --human
python -m src_auto juice-shop-zap --confirm-local --human
```

Expected result: Simplified Chinese summaries, HTTP 200 on `127.0.0.1:3000`, baseline `COMPLETED_DISCOVERY_ONLY`, ZAP `POSSIBLE_FINDINGS`, remote AI calls 0, and artifacts under `D:\网络安全文件夹\SRC-Auto\validation\juice-shop`.

- [x] **Step 3: Report the final behavior**

State exactly which interface paths are Chinese, which machine fields remain English, the test count, local smoke results, and remaining manual adjudication limits. Do not claim a confirmed vulnerability or bounty result.

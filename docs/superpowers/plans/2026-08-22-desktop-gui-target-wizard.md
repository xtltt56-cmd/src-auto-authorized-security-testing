# Desktop Chinese GUI and Authorized Target Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the desktop shortcut's immediate console-only launch with a concise Simplified Chinese Windows Forms menu that can start the local labs and create/review authorized target configuration without making network requests.

**Architecture:** `START_SYSTEM.ps1` becomes a thin dispatcher: the default path opens `tools\src_auto_gui.ps1`, while `-RunLocalLab` preserves the existing local-only console runner. The GUI delegates target validation and JSON/YAML-compatible file creation to focused functions in `tools\target_config.ps1`, then invokes the existing offline `target-review` command. No GUI path invokes `run-live --execute-live`, scanners, crawlers, or remote AI.

**Tech Stack:** Windows PowerShell 5.1, System.Windows.Forms/System.Drawing, existing Python 3.8 CLI, `unittest`, UTF-8 BOM for PowerShell files.

---

### Task 1: Add failing GUI and target-config contract tests

**Files:**
- Create: `tests/test_desktop_gui.py`
- Create: `tests/test_target_config_ps1.py`

- [ ] **Step 1: Write tests that define the public contract**

`test_desktop_gui.py` must assert that `tools\src_auto_gui.ps1` and `tools\target_config.ps1` exist with UTF-8 BOM; the GUI contains `System.Windows.Forms`, the Chinese labels `本地靶场检测`, `新建授权目标`, `离线审阅目标范围`, `AI 模型与密钥设置`, and `D:\网络安全文件夹`-independent project-root usage; it must not contain `run-live --execute-live`, `Invoke-WebRequest`, `httpx`, `katana`, or `zap`.

The same test must assert `START_SYSTEM.ps1` declares `-RunLocalLab`, dispatches to `tools\src_auto_gui.ps1` when the switch is absent, and preserves the local-loopback text.

`test_target_config_ps1.py` must execute PowerShell functions in `tools\target_config.ps1` with a temporary project root and assert:

```text
valid HTTPS URL + matching allowed host -> accepted
HTTP URL -> rejected with target_url_must_use_https
URL host not in allowed_hosts -> rejected with target_host_not_allowed
credential/query/fragment URL -> rejected with target_url_must_be_clean
invalid target id -> rejected with target_id_invalid
valid draft -> writes scope_confirmed.yaml and live_plan.yaml inside project root
written files contain confirmed=false when the human confirmation checkbox is false
```

- [ ] **Step 2: Run focused tests and verify the expected red state**

Run:

```powershell
python -m unittest tests.test_desktop_gui tests.test_target_config_ps1 -v
```

Expected result: failures because the new GUI and target-config scripts do not exist.

### Task 2: Implement pure target configuration functions

**Files:**
- Create: `tools\target_config.ps1`
- Test: `tests/test_target_config_ps1.py`

- [ ] **Step 1: Implement path and field validation**

Add `Assert-TargetProjectPath`, `ConvertTo-SafeTargetId`, `Test-TargetDraft`, `New-ScopeDocument`, `New-LivePlanDocument`, and `Write-TargetConfig`.

Rules:

- all output paths must remain below the supplied project root;
- target IDs must match `^[a-z0-9][a-z0-9_-]{1,39}$`;
- allowed hosts must be explicit, non-empty hostnames without scheme, credentials, path, query, or wildcard;
- target URLs must be `https`, have no username/password/query/fragment, and their host must be in `allowed_hosts` and not in `excluded_hosts`;
- ports must be integers from 1 through 65535;
- `confirmed` and `allow_network_contact` are true only when the two independent human checkboxes are true;
- no function performs network I/O.

- [ ] **Step 2: Write JSON documents with YAML-compatible `.yaml` names**

Write UTF-8 JSON text to:

```text
config\targets\<target_id>\scope_confirmed.yaml
config\targets\<target_id>\live_plan.yaml
```

The scope document must include `target_id`, `vendor`, `authorization_source`, `root_domains`, `allowed_hosts`, `excluded_hosts`, `allowed_ports`, `test_window`, `confirmed`, and `allow_network_contact`. The live plan must include `name`, `operator`, `authorization_note`, `manual_execution_confirmed=false`, `target_urls`, `sequence=[]`, and empty `commands` until a separate approved plan is written.

- [ ] **Step 3: Run the target-config tests**

Run:

```powershell
python -m unittest tests.test_target_config_ps1 -v
```

Expected result: all target validation and path containment tests pass.

### Task 3: Implement the Chinese WinForms menu and target wizard

**Files:**
- Create: `tools\src_auto_gui.ps1`
- Test: `tests/test_desktop_gui.py`

- [ ] **Step 1: Build a concise main window**

Use `System.Windows.Forms` and `System.Drawing` with a fixed, centered layout: cyan title, small status banner, two-column button grid, and a bottom safety note. Buttons:

```text
本地靶场检测
新建授权目标
选择已有目标
离线审阅目标范围
查看 Findings 和报告
AI 模型与密钥设置
退出
```

The main form must say “默认仅本机回环靶场；真实目标不会自动执行” and keep all paths relative to the project root.

- [ ] **Step 2: Add local-lab and report actions**

`本地靶场检测` starts a new visible PowerShell process with `START_SYSTEM.ps1 -RunLocalLab -NoExit` (or the equivalent argument order) and never starts a scanner against a non-loopback URL. `查看 Findings 和报告` opens the project reports directory using `explorer.exe` only after resolving the path below the project root.

- [ ] **Step 3: Add the authorized-target form**

The form must provide Simplified Chinese labels for target ID, vendor, authorization source, starting URL, root domain, allowed hosts, excluded hosts, allowed ports, test window, operator, and the two independent checkboxes `已人工核对补天规则` and `平台明确允许低频自动化测试`.

Buttons:

```text
保存草稿
保存并离线审阅
取消
```

`保存草稿` writes `confirmed=false` and never contacts the network. `保存并离线审阅` requires both checkboxes, writes the files, then starts only:

```powershell
python -m src_auto target-review --scope <scope> --plan <plan> --confirm-selection --human
```

in a visible console. It must not invoke `run-live`, `--execute-live`, httpx, Katana, ZAP, or remote AI.

- [ ] **Step 4: Add existing-target selection**

Use a project-root-bound `OpenFileDialog` filtered to `scope_confirmed.yaml`, display the selected target ID and paths, and offer only the same offline review action. Reject files outside `config\targets`.

- [ ] **Step 5: Add AI settings action**

Display current local/remote provider state without printing any key. Provide buttons to launch the existing DPAPI GUI savers for DeepSeek and OpenRouter, plus a note that enabling a provider is still a per-session decision. Do not call a provider from the menu.

### Task 4: Make the desktop shortcut dispatch to the GUI

**Files:**
- Modify: `START_SYSTEM.ps1`
- Modify: `tests/test_launcher.py`

- [ ] **Step 1: Add a switch-preserving dispatcher**

Declare `param([switch]$RunLocalLab)` before existing statements. If the switch is absent, invoke `tools\src_auto_gui.ps1` and return its exit code. If present, run the existing local-only flow unchanged. Keep the existing loopback checks, DeepSeek consent gate, Docker/Ollama startup, local validation and reports.

- [ ] **Step 2: Extend launcher tests**

Assert the dispatcher appears before the old local flow, that the GUI path is project-root-bound, and that `-RunLocalLab` remains present. Continue rejecting public bind addresses and external execution flags.

### Task 5: Verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `USER_MANUAL.md`
- Modify: `OPERATIONS.md`
- Modify: `TEST_REPORT.md`

- [ ] **Step 1: Document the GUI workflow**

Explain the seven menu buttons, draft versus confirmed scope, offline review, local-lab behavior, DPAPI key buttons, and the fact that the desktop GUI never runs real-target execution automatically.

- [ ] **Step 2: Run fresh verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src_auto
$errors=@(); Get-ChildItem -Recurse -File -Filter '*.ps1' | ForEach-Object { $tokens=$null; $parseErrors=$null; [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$parseErrors) | Out-Null; if($parseErrors.Count){$errors += $_.FullName} }; if($errors.Count){$errors; exit 1}
$hits=Get-ChildItem -Recurse -File -Include '*.ps1','*.py','*.md' | Select-String -Pattern '锟|�|莠|鐥' -SimpleMatch; if($hits){$hits; exit 1}
git diff --check
```

Expected result: all tests pass, compilation and PowerShell parsing succeed, no mojibake hits are found, and no whitespace errors are introduced.

- [ ] **Step 3: Run a local GUI smoke check**

Launch `START_SYSTEM.ps1` without `-RunLocalLab`, verify the menu appears in Simplified Chinese, open and cancel the target form, create a synthetic `local-gui-test` draft inside a temporary project-root test directory, run offline review, and verify no non-loopback network request is made.

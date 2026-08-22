# 离线审阅目标范围选择器改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让离线审阅可以从 `config\targets` 或任意已允许的上级目标文件夹开始选择，并能在一个界面中定位、预览和批量审阅多个已确认目标，同时保持严格的本地路径边界和“只离线、不访问网络”约束。

**Architecture:** 保留现有 `python -m src_auto target-review --scope ... --plan ...` 单目标命令作为唯一审阅执行入口，在 GUI 前增加一个纯本地的目标发现与选择层。选择层将用户输入的目录规范化到项目 `config\targets` 根目录内，递归发现成对的 `scope_confirmed.yaml` 与 `live_plan.yaml`，由 GUI 显示目标列表；批量选择只是在 GUI 中逐个调用现有离线审阅命令并汇总结果，不合并不同目标的授权范围。

**Tech Stack:** Windows PowerShell 5.1、WinForms、Python 3.8 标准库、现有 `src_auto.target_review` 和 `unittest`。

---

### Task 1: 固化当前问题并定义安全的目录发现接口

**Files:**
- Create: `src_auto/offline_scope_picker.py`
- Test: `tests/test_offline_scope_picker.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
import tempfile
import unittest

from src_auto.offline_scope_picker import discover_review_targets


class OfflineScopePickerTests(unittest.TestCase):
    def test_discovers_nested_confirmed_scope_only_when_plan_is_present(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            valid = root / "group" / "juice-shop"
            missing_plan = root / "group" / "missing-plan"
            valid.mkdir(parents=True)
            missing_plan.mkdir(parents=True)
            (valid / "scope_confirmed.yaml").write_text("target: juice-shop\n", encoding="utf-8")
            (valid / "live_plan.yaml").write_text("plan: offline\n", encoding="utf-8")
            (missing_plan / "scope_confirmed.yaml").write_text("target: draft\n", encoding="utf-8")

            found = discover_review_targets(root, root)

            self.assertEqual([item.scope_path for item in found], [valid / "scope_confirmed.yaml"])
            self.assertEqual(found[0].plan_path, valid / "live_plan.yaml")

    def test_rejects_a_directory_outside_targets_root(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "config" / "targets"
            outside = Path(raw) / "elsewhere"
            root.mkdir(parents=True)
            outside.mkdir()

            with self.assertRaises(ValueError):
                discover_review_targets(outside, root)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python -m unittest tests.test_offline_scope_picker -v`

Expected: FAIL because `src_auto.offline_scope_picker` and `discover_review_targets` do not yet exist.

- [ ] **Step 3: Implement the minimal resolver**

Define an immutable result with `scope_path`, `plan_path`, `target_dir`, and `relative_name`. Canonicalize both the requested directory and the allowed root with `Path.resolve()`. Reject a requested directory unless it is the root itself or a descendant of the root. Recursively inspect only files named exactly `scope_confirmed.yaml`; include a result only when its sibling `live_plan.yaml` exists. Do not read or merge YAML in this layer, and do not follow a path outside the canonical root.

- [ ] **Step 4: Run the focused test and the existing target-review tests**

Run: `python -m unittest tests.test_offline_scope_picker tests.test_target_review -v`

Expected: all tests PASS, with no network process started.

- [ ] **Step 5: Commit the isolated resolver change**

```powershell
git add src_auto/offline_scope_picker.py tests/test_offline_scope_picker.py
git commit -m "feat: discover offline review targets under allowed root"
```

### Task 2: Replace the single-file picker with a folder-first WinForms selector

**Files:**
- Modify: `tools/src_auto_gui.ps1` at `Select-ExistingTarget` and the main-menu action for `离线审阅目标范围`
- Test: `tests/test_desktop_gui.py`

- [ ] **Step 1: Add source-level regression tests before changing PowerShell**

Add assertions that the GUI source contains `FolderBrowserDialog` or the new folder-first picker function, a visible path input, `config\\targets`, `scope_confirmed.yaml`, `live_plan.yaml`, an upper-level navigation action, and a call to the Python offline-review command. Also assert that the source still rejects paths outside the project target root and contains no `run-live` or `--execute-live` flag.

- [ ] **Step 2: Run the GUI test to verify the new behavior is absent**

Run: `python -m unittest tests.test_desktop_gui -v`

Expected: FAIL on the new folder-first assertions while the existing GUI assertions continue to pass.

- [ ] **Step 3: Implement folder-first navigation with safe root handling**

Add a `Show-OfflineReviewPicker` function with these controls:

1. A read-only or validated editable path box, initialized to `D:\网络安全文件夹\SRC-Auto\config\targets`.
2. Buttons for `项目目标根`, `上一级`, `选择文件夹`, and `刷新`.
3. A list view showing folder name, relative path, Scope 状态, Plan 状态, and whether it is directly reviewable.
4. A checkbox per discovered target and a `全选当前结果` action.
5. A status line explaining that the operation is offline and will not send requests.
6. `开始离线审阅` and `取消` actions.

Selecting a high-level directory runs the resolver from Task 1 and displays all descendant targets. Double-clicking a folder narrows the view to that folder. Selecting a folder with a matching scope/plan pair selects that single target; selecting `config\\targets` or a group folder shows all valid descendants. A missing `live_plan.yaml` is displayed as `不可审阅` and cannot be checked.

The picker must canonicalize every path and enforce the `config\\targets` boundary before listing or opening files. It must never invoke a network command and must invoke the existing offline command only with `--confirm-selection --human` after the user presses `开始离线审阅`.

- [ ] **Step 4: Run the focused GUI tests and PowerShell parser check**

Run: `python -m unittest tests.test_desktop_gui -v`

Run: `$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('D:\网络安全文件夹\SRC-Auto\tools\src_auto_gui.ps1', [ref]$null, [ref]$errors) | Out-Null; if($errors.Count){ $errors | Format-List; exit 1 }`

Expected: all focused tests PASS and the parser reports no errors.

- [ ] **Step 5: Commit the picker change**

```powershell
git add tools/src_auto_gui.ps1 tests/test_desktop_gui.py
git commit -m "feat: add folder-first offline review picker"
```

### Task 3: Add batch execution and result aggregation without changing authorization semantics

**Files:**
- Modify: `tools/src_auto_gui.ps1`
- Test: `tests/test_desktop_gui.py`
- Test: `tests/test_target_review.py`

- [ ] **Step 1: Write the failing aggregation tests**

Test that two selected target records produce two separate `target-review` invocations, each with its own scope and plan, and that an unselected or missing-plan record is never invoked. Test that a cancellation produces no invocation. Test that the generated summary distinguishes `通过`, `阻止`, and `需要人工复核` without printing tokens or response bodies.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_desktop_gui tests.test_target_review -v`

Expected: FAIL because the picker has no batch runner or summary model.

- [ ] **Step 3: Implement a sequential, fail-closed batch runner**

Run the existing offline review command once per selected target, sequentially, with no live flags. Stop on a missing or invalid path, show a local error, and leave already-produced offline reports intact. Never combine target scopes, never pass candidate scope files, and never auto-run a network adapter. Display a final local summary with target name, scope path, plan path, exit status, and report path.

- [ ] **Step 4: Run focused tests and inspect command construction**

Run: `python -m unittest tests.test_desktop_gui tests.test_target_review -v`

Expected: PASS; assertions must prove separate arguments and absence of live-execution flags.

- [ ] **Step 5: Commit the batch behavior**

```powershell
git add tools/src_auto_gui.ps1 tests/test_desktop_gui.py tests/test_target_review.py
git commit -m "feat: review selected offline targets independently"
```

### Task 4: End-to-end acceptance and documentation

**Files:**
- Modify: `USER_MANUAL.md`
- Modify: `README.md`
- Test: `tests/test_offline_scope_picker.py`

- [ ] **Step 1: Add acceptance fixtures**

Create temporary nested fixtures in the test itself for: one valid target, one confirmed scope without a plan, one candidate-only target, and one path outside `config\\targets`. Assert that only the valid confirmed pair is actionable.

- [ ] **Step 2: Run the complete test and encoding checks**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Run: `python -m compileall -q src_auto tests`

Run: `$strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true); Get-ChildItem 'D:\网络安全文件夹\SRC-Auto' -Recurse -File -Include *.py,*.ps1,*.md | ForEach-Object { [void]$strictUtf8.GetString([IO.File]::ReadAllBytes($_.FullName)) }; $bytes=[IO.File]::ReadAllBytes('D:\网络安全文件夹\SRC-Auto\tools\src_auto_gui.ps1'); if(-not ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)){ throw 'GUI BOM missing' }`

Expected: the full suite passes, Python compiles, and all project text/script files retain the existing UTF-8/BOM convention.

- [ ] **Step 3: Document the new workflow**

Explain that the user can paste or browse to `config\\targets`, select a group folder, review the discovered confirmed targets, and start offline review. Explicitly state that `scope_candidate.yaml` is never actionable, `live_plan.yaml` is required, selection is restricted to the project target root, and the process does not access target websites.

- [ ] **Step 4: Perform a manual local smoke test**

Open the desktop shortcut, choose `离线审阅目标范围`, paste/select `D:\网络安全文件夹\SRC-Auto\config\targets`, verify that nested local lab targets appear, select one, start review, and confirm that the resulting report is written under the project directory with no network process or external URL request.

- [ ] **Step 5: Commit documentation and final verification**

```powershell
git add USER_MANUAL.md README.md tests/test_offline_scope_picker.py
git commit -m "docs: explain folder-first offline review workflow"
```

## Recommendation

Implement Tasks 1-4 in order. The key usability improvement is the folder-first selector with a validated path box and group-level discovery; the key safety property is that group selection expands to separate confirmed target entries instead of merging authorization scopes. Keep the existing single-target CLI unchanged so the change remains low-risk and reversible.

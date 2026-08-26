# WebView2 Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reliable, high-DPI Windows desktop shell that launches the local SRC-Auto service, embeds the approved Web dashboard through WebView2, and preserves the existing launcher as a reversible fallback.

**Architecture:** A small WPF application owns the desktop window and a `BackendSupervisor`. The supervisor starts the project-local Python service, receives its randomly selected loopback port and one-time session token through a startup contract, then navigates WebView2 to the exact loopback origin. Navigation, downloads, new windows, developer tools, and external origins are denied by policy. The existing PowerShell launcher remains available through `-LegacyGui` until the new shell passes final acceptance.

**Tech Stack:** .NET 8 WPF, Microsoft.Web.WebView2, xUnit, project-local .NET runtime under `D:\网络安全文件夹\SRC-Auto\runtime`, PowerShell launcher.

---

## Safety and storage constraints

- Do not write application artifacts outside `D:\网络安全文件夹\SRC-Auto`, except the explicitly requested desktop shortcut.
- Bind the backend only to `127.0.0.1`; never bind to `0.0.0.0` or a LAN address.
- Do not place API keys or task data in command-line arguments, browser URLs, logs, or crash messages.
- Accept navigation only to the exact origin emitted by the current backend process.
- Preserve `START_SYSTEM.ps1 -LegacyGui` until the new shell passes the complete local acceptance suite.
- Desktop UI tests may run only against the local five-lab environment and test doubles.

## Task 1: Add a project-local .NET runtime contract

**Files:**

- Create: `desktop/global.json`
- Create: `desktop/runtime-manifest.json`
- Create: `desktop/runtime-lock.json` (generated from verified Microsoft release metadata, then committed)
- Create: `tools/install_desktop_runtime.ps1`
- Create: `tests/desktop_runtime_contract.Tests.ps1`

**Step 1: Write the failing contract test**

```powershell
Describe 'desktop runtime contract' {
    It 'keeps every downloaded artifact under the project runtime directory' {
        $manifest = Get-Content "$PSScriptRoot\..\desktop\runtime-manifest.json" -Raw |
            ConvertFrom-Json
        $manifest.installRoot | Should -Be 'runtime/dotnet'
        $manifest.cacheRoot | Should -Be 'runtime/download-cache'
    }

    It 'pins an SDK major version compatible with the desktop project' {
        $global = Get-Content "$PSScriptRoot\..\desktop\global.json" -Raw |
            ConvertFrom-Json
        $global.sdk.version | Should -Match '^8\.'
    }
}
```

**Step 2: Run the test and confirm failure**

Run:

```powershell
Invoke-Pester .\tests\desktop_runtime_contract.Tests.ps1 -Output Detailed
```

Expected: failure because the manifest and `global.json` do not exist.

**Step 3: Implement the pinned runtime metadata**

`desktop/runtime-manifest.json` must contain only relative project paths and the official release-metadata source for the pinned SDK:

```json
{
  "sdkVersion": "8.0.408",
  "installRoot": "runtime/dotnet",
  "cacheRoot": "runtime/download-cache",
  "architecture": "win-x64",
  "releaseMetadataUrl": "https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/8.0/releases.json"
}
```

The installer must:

1. resolve the project root from `$PSScriptRoot`;
2. reject any resolved install/cache path outside the project root;
3. load the official Microsoft release metadata and select the exact pinned SDK version plus `win-x64` archive;
4. reject missing, ambiguous, or non-128-hex SHA-512 metadata;
5. download to `runtime/download-cache` and verify the published SHA-512 before extraction;
6. write the resolved archive URL and verified hash to `desktop/runtime-lock.json`;
7. extract to `runtime/dotnet` without modifying the machine-wide `PATH`.

**Step 4: Run the test and installer dry run**

Run:

```powershell
Invoke-Pester .\tests\desktop_runtime_contract.Tests.ps1 -Output Detailed
.\tools\install_desktop_runtime.ps1 -WhatIf
```

Expected: tests pass; dry run lists only paths under the project root.

**Step 5: Commit**

```powershell
git add desktop/global.json desktop/runtime-manifest.json desktop/runtime-lock.json tools/install_desktop_runtime.ps1 tests/desktop_runtime_contract.Tests.ps1
git commit -m "build: pin project-local desktop runtime"
```

## Task 2: Create the minimal WPF and WebView2 shell

**Files:**

- Create: `desktop/SrcAuto.Desktop/SrcAuto.Desktop.csproj`
- Create: `desktop/SrcAuto.Desktop/App.xaml`
- Create: `desktop/SrcAuto.Desktop/App.xaml.cs`
- Create: `desktop/SrcAuto.Desktop/MainWindow.xaml`
- Create: `desktop/SrcAuto.Desktop/MainWindow.xaml.cs`
- Create: `desktop/SrcAuto.Desktop.Tests/SrcAuto.Desktop.Tests.csproj`
- Create: `desktop/SrcAuto.Desktop.Tests/ShellContractTests.cs`

**Step 1: Write the failing shell contract test**

```csharp
[Fact]
public void ShellStartsOnAStatusScreenBeforeNavigation()
{
    var state = ShellState.Starting("正在启动本地服务……");
    Assert.Equal(ShellPhase.Starting, state.Phase);
    Assert.Equal("正在启动本地服务……", state.Message);
    Assert.Null(state.DashboardUri);
}
```

**Step 2: Run the test and confirm failure**

Run:

```powershell
.\runtime\dotnet\dotnet.exe test .\desktop\SrcAuto.Desktop.Tests
```

Expected: compile failure because `ShellState` does not exist.

**Step 3: Implement the smallest shell**

Use the official `Microsoft.Web.WebView2` NuGet package. `MainWindow.xaml` must contain:

- a Chinese startup/status panel;
- a retry button;
- an “在浏览器中打开” fallback button;
- one WebView2 control initially hidden;
- no scanner or authorization logic inside the desktop process.

The state model must remain independent from WPF so it can be unit tested:

```csharp
public enum ShellPhase { Starting, Ready, Failed, Stopped }

public sealed record ShellState(
    ShellPhase Phase,
    string Message,
    Uri? DashboardUri)
{
    public static ShellState Starting(string message) =>
        new(ShellPhase.Starting, message, null);
}
```

**Step 4: Run unit tests and build**

```powershell
.\runtime\dotnet\dotnet.exe test .\desktop\SrcAuto.Desktop.Tests
.\runtime\dotnet\dotnet.exe build .\desktop\SrcAuto.Desktop\SrcAuto.Desktop.csproj -c Release
```

Expected: zero failures and a successful Release build.

**Step 5: Commit**

```powershell
git add desktop/SrcAuto.Desktop desktop/SrcAuto.Desktop.Tests
git commit -m "feat: add minimal WebView2 desktop shell"
```

## Task 3: Supervise the local backend without leaking secrets

**Files:**

- Create: `desktop/SrcAuto.Desktop/Services/BackendSupervisor.cs`
- Create: `desktop/SrcAuto.Desktop/Services/BackendStartupMessage.cs`
- Create: `desktop/SrcAuto.Desktop/Services/IProcessRunner.cs`
- Create: `desktop/SrcAuto.Desktop.Tests/BackendSupervisorTests.cs`
- Modify: `src_auto/dashboard/app.py`
- Create: `tests/test_dashboard_startup_contract.py`

**Step 1: Write failing Python and C# contract tests**

The Python test must prove the startup payload contains only:

```json
{"status":"ready","host":"127.0.0.1","port":49152,"session_token_file":"runtime/session/current.token"}
```

The C# test must prove that malformed output, non-loopback hosts, missing token files, and early process exit all produce `ShellPhase.Failed`.

**Step 2: Run both test suites and confirm failure**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_dashboard_startup_contract.py -q
.\runtime\dotnet\dotnet.exe test .\desktop\SrcAuto.Desktop.Tests
```

Expected: failures because the startup contract and supervisor are absent.

**Step 3: Implement a JSON-line startup handshake**

`BackendSupervisor` must use `ProcessStartInfo.ArgumentList`, not a concatenated shell command:

```csharp
var startInfo = new ProcessStartInfo(pythonExecutable)
{
    UseShellExecute = false,
    RedirectStandardOutput = true,
    RedirectStandardError = true,
    CreateNoWindow = true,
    WorkingDirectory = projectRoot
};
startInfo.ArgumentList.Add("-m");
startInfo.ArgumentList.Add("src_auto.dashboard.app");
startInfo.ArgumentList.Add("--startup-json");
```

Requirements:

- backend chooses an available high loopback port;
- backend writes a random session token into `runtime/session/current.token` with current-user-only ACL;
- token value never appears in stdout, stderr, URL, logs, or screenshots;
- desktop reads the token file after validating it is under project root;
- desktop deletes the token file after backend termination;
- a health check must pass before WebView2 navigation begins.

**Step 4: Run tests**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_dashboard_startup_contract.py -q
.\runtime\dotnet\dotnet.exe test .\desktop\SrcAuto.Desktop.Tests
```

Expected: all startup and failure-path tests pass.

**Step 5: Commit**

```powershell
git add src_auto/dashboard/app.py tests/test_dashboard_startup_contract.py desktop/SrcAuto.Desktop desktop/SrcAuto.Desktop.Tests
git commit -m "feat: supervise loopback control service"
```

## Task 4: Enforce WebView2 navigation and browser containment

**Files:**

- Create: `desktop/SrcAuto.Desktop/Security/NavigationPolicy.cs`
- Modify: `desktop/SrcAuto.Desktop/MainWindow.xaml.cs`
- Create: `desktop/SrcAuto.Desktop.Tests/NavigationPolicyTests.cs`

**Step 1: Write the failing policy tests**

```csharp
[Theory]
[InlineData("http://127.0.0.1:49152/", true)]
[InlineData("http://127.0.0.1:49152/tasks/abc", true)]
[InlineData("http://127.0.0.1:49153/", false)]
[InlineData("http://localhost:49152/", false)]
[InlineData("https://example.com/", false)]
[InlineData("file:///C:/Windows/win.ini", false)]
public void AllowsOnlyTheExactBackendOrigin(string value, bool expected)
{
    var policy = new NavigationPolicy(new Uri("http://127.0.0.1:49152/"));
    Assert.Equal(expected, policy.Allows(new Uri(value)));
}
```

**Step 2: Run the test and confirm failure**

```powershell
.\runtime\dotnet\dotnet.exe test .\desktop\SrcAuto.Desktop.Tests --filter NavigationPolicy
```

Expected: compile failure because `NavigationPolicy` does not exist.

**Step 3: Implement containment**

Wire the policy to WebView2 events:

- cancel `NavigationStarting` for any non-exact origin;
- cancel every `NewWindowRequested` event;
- cancel every `DownloadStarting` event;
- disable default context menus, autofill, password saving, and release-mode developer tools;
- set WebView2 user-data directory to `runtime/webview2-data`;
- inject the session header through same-origin API calls, never through a query parameter;
- show a Chinese blocked-navigation notice without opening an external browser automatically.

**Step 4: Run tests and inspect settings in a smoke build**

```powershell
.\runtime\dotnet\dotnet.exe test .\desktop\SrcAuto.Desktop.Tests
.\runtime\dotnet\dotnet.exe build .\desktop\SrcAuto.Desktop\SrcAuto.Desktop.csproj -c Release
```

Expected: all policy tests pass; Release build succeeds.

**Step 5: Commit**

```powershell
git add desktop/SrcAuto.Desktop desktop/SrcAuto.Desktop.Tests
git commit -m "security: contain desktop web navigation"
```

## Task 5: Integrate the one-click launcher with rollback

**Files:**

- Modify: `START_SYSTEM.ps1`
- Create: `tools/start_desktop_shell.ps1`
- Create: `tests/start_system_shell.Tests.ps1`
- Modify: `tools/create_desktop_shortcut.ps1`

**Step 1: Write failing launcher tests**

Tests must assert:

- default mode launches the new shell;
- `-LegacyGui` invokes the existing WinForms path;
- `-BrowserFallback` launches the backend and opens its loopback URL;
- missing WebView2 Runtime produces a Chinese actionable error and offers browser fallback;
- all resolved executables and scripts remain inside the project root or trusted Windows locations.

**Step 2: Run and confirm failure**

```powershell
Invoke-Pester .\tests\start_system_shell.Tests.ps1 -Output Detailed
```

Expected: failures because the new modes do not exist.

**Step 3: Implement explicit launcher modes**

The default path must be:

```text
desktop shortcut -> START_SYSTEM.ps1 -> start_desktop_shell.ps1 -> WPF shell
```

Fallback paths must remain user-selectable and must never contact a real target automatically. Do not remove or rewrite the legacy UI during this phase.

**Step 4: Run tests and regenerate the shortcut**

```powershell
Invoke-Pester .\tests\start_system_shell.Tests.ps1 -Output Detailed
.\tools\create_desktop_shortcut.ps1
```

Expected: tests pass; the shortcut target is `START_SYSTEM.ps1`, not a folder.

**Step 5: Commit**

```powershell
git add START_SYSTEM.ps1 tools/start_desktop_shell.ps1 tools/create_desktop_shortcut.ps1 tests/start_system_shell.Tests.ps1
git commit -m "feat: switch one-click launcher to WebView2 shell"
```

## Task 6: Publish a self-contained desktop build under D drive

**Files:**

- Create: `tools/publish_desktop.ps1`
- Create: `desktop/publish-manifest.json`
- Create: `tests/publish_desktop.Tests.ps1`
- Modify: `.gitignore`

**Step 1: Write the failing publish tests**

Tests must assert that publish output is `desktop/publish/win-x64`, excludes token files, databases, reports, keys, and WebView2 user data, and includes a generated file-hash manifest.

**Step 2: Run and confirm failure**

```powershell
Invoke-Pester .\tests\publish_desktop.Tests.ps1 -Output Detailed
```

**Step 3: Implement deterministic publishing**

Publish with:

```powershell
.\runtime\dotnet\dotnet.exe publish `
  .\desktop\SrcAuto.Desktop\SrcAuto.Desktop.csproj `
  -c Release -r win-x64 --self-contained true `
  -o .\desktop\publish\win-x64
```

Generate SHA-256 hashes for shipped files. The publish script must stop if it detects `.env`, `*.token`, `*.db`, `secrets`, `reports`, or user-generated target data in the output.

**Step 4: Run tests and publish**

```powershell
Invoke-Pester .\tests\publish_desktop.Tests.ps1 -Output Detailed
.\tools\publish_desktop.ps1
```

Expected: publish succeeds and forbidden-data scan returns zero matches.

**Step 5: Commit**

```powershell
git add tools/publish_desktop.ps1 desktop/publish-manifest.json tests/publish_desktop.Tests.ps1 .gitignore
git commit -m "build: publish self-contained desktop shell"
```

## Task 7: Run desktop reliability and DPI acceptance

**Files:**

- Create: `tests/desktop_shell_acceptance.Tests.ps1`
- Create: `docs/validation/desktop-shell-acceptance.md`
- Modify: `docs/使用手册.md`

**Step 1: Encode the acceptance matrix**

Automate checks for:

- 100%, 125%, 150%, and 200% scaling without clipped primary controls;
- backend crash -> visible Chinese error -> successful retry;
- desktop close -> backend child process exits;
- stale token file -> rejected and replaced;
- external navigation, download, and new-window attempts -> blocked;
- browser fallback works without a real target;
- legacy fallback still opens;
- five consecutive launch/exit cycles leave no orphan backend processes.

**Step 2: Run the acceptance suite**

```powershell
Invoke-Pester .\tests\desktop_shell_acceptance.Tests.ps1 -Output Detailed
```

Expected: all automated assertions pass. DPI screenshot checks at all four scale factors are attached to `docs/validation/desktop-shell-acceptance.md`.

**Step 3: Run local-only end-to-end smoke verification**

```powershell
.\START_SYSTEM.ps1
```

From the UI, start one five-lab validation task, observe events, pause/resume once, open a report, and exit. Confirm:

```text
external_targets_contacted = 0
automatic_submissions = 0
orphan_backend_processes = 0
```

**Step 4: Update the manual**

Document the normal launcher, browser fallback, legacy fallback, recovery flow, D-drive storage locations, and how to read a failed startup message.

**Step 5: Commit**

```powershell
git add tests/desktop_shell_acceptance.Tests.ps1 docs/validation/desktop-shell-acceptance.md docs/使用手册.md
git commit -m "test: accept WebView2 desktop shell"
```

## Completion gate

This plan is complete only when:

- the desktop shell passes unit, launcher, packaging, security-policy, DPI, crash-recovery, and process-cleanup tests;
- the dashboard is reachable only through the exact loopback origin created for that session;
- no secret is present in process arguments, browser URLs, stdout, stderr, reports, screenshots, or Git history;
- the existing `-LegacyGui` and browser fallback paths are still operational;
- the one-click desktop shortcut starts the new shell;
- a local five-lab task can be observed end to end without contacting any external target.

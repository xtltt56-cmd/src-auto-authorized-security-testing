# SRC-Auto Real-Time Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a polished Simplified Chinese local dashboard that visualizes persisted task events in real time and safely controls local tasks.

**Architecture:** A FastAPI service bound only to `127.0.0.1` reads the existing Store, exposes token-protected REST endpoints, and streams persisted events over SSE. A locally built React/TypeScript frontend consumes those endpoints; closing the page does not stop tasks.

**Tech Stack:** Project-local Python 3.12, FastAPI, Uvicorn, sse-starlette, React, TypeScript, Vite, Chart.js, Playwright, existing unittest, all dependencies and build outputs under `D:\网络安全文件夹\SRC-Auto`.

---

### Task 1: Produce and approve the Figma dashboard specification

**Files:**
- Create: `docs/design/task-visualization-figma.md`
- Create: `design/task-visualization/dashboard-overview.png`
- Create: `design/task-visualization/task-detail.png`
- Create: `design/task-visualization/authorization-gate.png`
- Create: `design/task-visualization/findings-review.png`
- Create: `design/task-visualization/task-history.png`
- Create: `design/task-visualization/system-status.png`

- [ ] **Step 1: Use the Figma plugin before writing frontend code**

Create desktop frames at 1440×900 and responsive references at 1280×720. Use real Simplified Chinese content, not lorem ipsum. Include default, loading, waiting-human, running, warning, blocked, failed, paused, cancelled, completed, empty, and disconnected states.

- [ ] **Step 2: Define and export design tokens**

Record exact tokens in `docs/design/task-visualization-figma.md`:

```json
{
  "color": {
    "nav": "#0D3052",
    "primary": "#1E88E5",
    "success": "#1A7F52",
    "warning": "#B56D14",
    "danger": "#C62828",
    "canvas": "#F6F9FC",
    "surface": "#FFFFFF",
    "text": "#14304A",
    "muted": "#5C6A78",
    "border": "#DAE4EE"
  },
  "font": "Microsoft YaHei UI, Segoe UI, sans-serif",
  "radius": {"card": 10, "button": 6},
  "spacing": [4, 8, 12, 16, 24, 32]
}
```

- [ ] **Step 3: Review required workflows in the Figma file**

The exported pages must show: start a five-lab task, follow per-lab progress, reconnect after a page refresh, request pause, cancel safely, open a report, inspect a blocked authorized task, and resume an interrupted task.

- [ ] **Step 4: Obtain user approval of the exported images**

No React component work begins until the user explicitly approves or requests changes to the images.

- [ ] **Step 5: Commit only approved design artifacts**

```powershell
git add -- docs/design/task-visualization-figma.md design/task-visualization
git commit -m "design: approve task visualization dashboard"
```

### Task 2: Add project-local runtime manifests and reproducible installers

**Files:**
- Create: `runtime/README.md`
- Create: `runtime/locks/python-dashboard-requirements.txt`
- Create: `runtime/locks/frontend-package-lock.sha256`
- Create: `tools/install_dashboard_runtime.ps1`
- Modify: `.gitignore`
- Test: `tests/test_dashboard_runtime_installer.py`

- [ ] **Step 1: Write failing installer contract tests**

```python
def test_installer_uses_only_project_local_destinations(self):
    script = INSTALLER.read_text(encoding="utf-8-sig")
    self.assertIn("runtime\\python312", script)
    self.assertIn("runtime\\node", script)
    self.assertNotIn("setx PATH", script.lower())
    self.assertNotIn("Program Files", script)
    self.assertIn("Get-FileHash", script)
```

- [ ] **Step 2: Verify the contract test fails**

Run: `python -m unittest tests.test_dashboard_runtime_installer -v`

Expected: missing installer failure.

- [ ] **Step 3: Implement the installer with explicit roots**

The script must resolve:

```powershell
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot 'runtime'
$PythonRoot = Join-Path $RuntimeRoot 'python312'
$NodeRoot = Join-Path $RuntimeRoot 'node'
$CacheRoot = Join-Path $RuntimeRoot 'cache'
```

Download only official Python and Node distributions, verify SHA-256 values stored in a reviewed lock file, and never modify machine/user PATH. Install Python packages into a project venv and run `npm ci` using the portable Node executable.

- [ ] **Step 4: Add runtime exclusions**

Ignore extracted runtimes, caches, venvs, WebView2 data, session tokens, database WAL files, and `dashboard/node_modules`; keep lock files and `dashboard/dist` release artifacts according to the repository release policy.

- [ ] **Step 5: Run installer contract and dry-run checks**

Run: `python -m unittest tests.test_dashboard_runtime_installer -v`

Expected: pass without downloading anything during tests.

- [ ] **Step 6: Commit installer and manifests**

```powershell
git add -- .gitignore runtime/README.md runtime/locks tools/install_dashboard_runtime.ps1 tests/test_dashboard_runtime_installer.py
git commit -m "build: define project-local dashboard runtime"
```

### Task 3: Implement the loopback service security boundary

**Files:**
- Create: `src_auto/dashboard/__init__.py`
- Create: `src_auto/dashboard/security.py`
- Create: `src_auto/dashboard/schemas.py`
- Test: `tests/test_dashboard_security.py`

- [ ] **Step 1: Write failing token, host, origin, and nonce tests**

```python
def test_non_loopback_host_is_rejected(self):
    response = self.client.get("/api/v1/health", headers={"Host": "example.com"})
    self.assertEqual(response.status_code, 400)

def test_mutation_requires_session_token(self):
    response = self.client.post("/api/v1/tasks/local-lab", json={"display_name": "测试"})
    self.assertEqual(response.status_code, 401)

def test_confirmation_nonce_is_single_use(self):
    nonce = self.security.issue_confirmation_nonce("run-1")
    self.security.consume_confirmation_nonce("run-1", nonce)
    with self.assertRaises(PermissionError):
        self.security.consume_confirmation_nonce("run-1", nonce)
```

- [ ] **Step 2: Verify the security module is missing**

Run: `python -m unittest tests.test_dashboard_security -v`

Expected: missing module failure.

- [ ] **Step 3: Implement constant-time token checks and one-time nonces**

```python
class LocalSessionSecurity:
    def __init__(self, token: str, allowed_port: int):
        self._token = token
        self._allowed_hosts = {"127.0.0.1:{}".format(allowed_port), "localhost:{}".format(allowed_port)}
        self._nonces = {}

    def verify_token(self, supplied: str) -> None:
        if not hmac.compare_digest(self._token, supplied or ""):
            raise PermissionError("invalid_session_token")
```

Implement bounded nonce storage with expiry, exact Host matching, local Origin matching, no wildcard CORS, and safe response headers.

- [ ] **Step 4: Define Pydantic request/response schemas**

Schemas must reject unknown fields for mutation requests, cap display names and filter lengths, and represent states using the same string values as `TaskState`.

- [ ] **Step 5: Run security tests**

Run: `python -m unittest tests.test_dashboard_security -v`

Expected: all pass.

- [ ] **Step 6: Commit security boundary**

```powershell
git add -- src_auto/dashboard tests/test_dashboard_security.py
git commit -m "security: protect loopback dashboard service"
```

### Task 4: Add task REST endpoints

**Files:**
- Create: `src_auto/dashboard/api.py`
- Create: `src_auto/dashboard/app.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_list_tasks_returns_runtime_and_latest_counters(self):
    response = self.client.get("/api/v1/tasks", headers=self.auth_headers)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["items"][0]["run_id"], self.run_id)

def test_local_task_endpoint_never_accepts_arbitrary_url(self):
    response = self.client.post(
        "/api/v1/tasks/local-lab",
        headers=self.auth_headers,
        json={"display_name": "本地验收", "url": "https://example.com"},
    )
    self.assertEqual(response.status_code, 422)
```

- [ ] **Step 2: Verify endpoints are missing**

Run: `python -m unittest tests.test_dashboard_api -v`

Expected: import or 404 failures.

- [ ] **Step 3: Implement read-only task, lab, tool, and report endpoints**

Keep route functions thin: validate input, call task service, convert to schema, return. Report IDs map to server-side allowlisted paths and never accept a filesystem path from the browser.

- [ ] **Step 4: Implement token-protected local task controls**

```python
@router.post("/tasks/{run_id}/cancel")
def cancel_task(run_id: str, request: Request):
    require_local_session(request)
    task_service.request_cancel(run_id)
    return {"status": "cancel_requested", "run_id": run_id}
```

Add equivalent pause and resume handlers. Do not add authorized-target creation in this phase.

- [ ] **Step 5: Run API, Store, and task tests**

Run: `python -m unittest tests.test_dashboard_api tests.test_store tests.test_task_orchestrator -v`

Expected: all pass.

- [ ] **Step 6: Commit the REST API**

```powershell
git add -- src_auto/dashboard tests/test_dashboard_api.py
git commit -m "feat: expose local task dashboard API"
```

### Task 5: Stream persisted events with resumable SSE

**Files:**
- Create: `src_auto/dashboard/stream.py`
- Modify: `src_auto/dashboard/api.py`
- Test: `tests/test_dashboard_sse.py`

- [ ] **Step 1: Write failing resume and terminal-close tests**

```python
def test_stream_resumes_after_last_event_id(self):
    response = self.client.get(
        "/api/v1/tasks/{}/stream".format(self.run_id),
        headers={**self.auth_headers, "Last-Event-ID": str(self.first_event_id)},
    )
    self.assertNotIn('"id":{}'.format(self.first_event_id), response.text)
    self.assertIn('"id":{}'.format(self.second_event_id), response.text)

def test_terminal_task_stream_emits_final_event_and_closes(self):
    self.assert_stream_closes_after("task_completed")
```

- [ ] **Step 2: Verify the stream route is missing**

Run: `python -m unittest tests.test_dashboard_sse -v`

Expected: 404 or missing module.

- [ ] **Step 3: Implement a database-backed async event generator**

```python
async def stream_task_events(store_factory, run_id: str, after_id: int):
    cursor = after_id
    while True:
        with store_factory() as store:
            events = store.list_task_events(run_id, after_id=cursor, limit=200)
            runtime = store.get_task_runtime(run_id)
        for event in events:
            cursor = event["id"]
            yield {"id": str(cursor), "event": "task-event", "data": json.dumps(event, ensure_ascii=False)}
        if runtime["state"] in TERMINAL_STATES and not events:
            return
        await asyncio.sleep(0.5)
```

Use a new short-lived Store connection per polling cycle or an explicitly thread-safe connection; do not share the request thread's SQLite connection across event-loop threads.

- [ ] **Step 4: Add heartbeat comments and disconnect handling**

Send an SSE comment no more often than every 15 seconds when no events arrive. Stop promptly when `request.is_disconnected()` becomes true.

- [ ] **Step 5: Run SSE tests**

Run: `python -m unittest tests.test_dashboard_sse -v`

Expected: reconnect receives every persisted event after the cursor exactly once.

- [ ] **Step 6: Commit SSE transport**

```powershell
git add -- src_auto/dashboard/stream.py src_auto/dashboard/api.py tests/test_dashboard_sse.py
git commit -m "feat: stream resumable task events"
```

### Task 6: Scaffold the approved React dashboard

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/package-lock.json`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/styles/tokens.css`
- Create: `dashboard/src/types/task.ts`
- Create: `dashboard/src/api/client.ts`
- Test: `dashboard/src/App.test.tsx`

- [ ] **Step 1: Add a failing application-shell test**

```tsx
it('shows the Chinese navigation and safe default status', async () => {
  render(<App />)
  expect(screen.getByText('任务总览')).toBeInTheDocument()
  expect(screen.getByText('本地靶场')).toBeInTheDocument()
  expect(screen.getByText('结果与报告')).toBeInTheDocument()
  expect(screen.getByText('未自动访问任何真实目标')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the frontend test and verify it fails**

Run from `dashboard/`: `..\runtime\node\npm.cmd test -- --run`

Expected: missing `App` or missing labels.

- [ ] **Step 3: Implement the shell from approved Figma tokens**

Create semantic navigation, a top safety banner, a main content outlet, and keyboard-visible focus states. Do not include a free-form URL execution box on the home page.

- [ ] **Step 4: Add a typed API client**

```ts
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'X-SRC-Auto-Session': window.__SRC_AUTO_TOKEN__, ...init.headers },
  })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return response.json() as Promise<T>
}
```

The token is injected into the local document at startup and never persisted to `localStorage` or logs.

- [ ] **Step 5: Run tests and production build**

Run:

```powershell
runtime\node\npm.cmd --prefix dashboard test -- --run
runtime\node\npm.cmd --prefix dashboard run build
```

Expected: tests pass and `dashboard/dist/index.html` exists without external CDN URLs.

- [ ] **Step 6: Commit the frontend shell**

```powershell
git add -- dashboard
git commit -m "feat: scaffold Chinese task dashboard"
```

### Task 7: Build task list, task detail, and real-time timeline

**Files:**
- Create: `dashboard/src/pages/TaskOverviewPage.tsx`
- Create: `dashboard/src/pages/TaskDetailPage.tsx`
- Create: `dashboard/src/components/StageTimeline.tsx`
- Create: `dashboard/src/components/EventLog.tsx`
- Create: `dashboard/src/components/TaskCounters.tsx`
- Create: `dashboard/src/hooks/useTaskEvents.ts`
- Test: `dashboard/src/pages/TaskDetailPage.test.tsx`

- [ ] **Step 1: Write a failing real-time rendering test**

```tsx
it('updates the timeline and counters from task events', async () => {
  const source = fakeEventSource()
  render(<TaskDetailPage runId="run-1" eventSourceFactory={() => source} />)
  source.emit({event_type: 'stage_started', stage: 'surface_discovery', progress: 35, counters: {candidates: 2}})
  expect(await screen.findByText('表面发现')).toHaveAttribute('data-state', 'running')
  expect(screen.getByText('2')).toBeInTheDocument()
})
```

- [ ] **Step 2: Verify the page test fails**

Run: `runtime\node\npm.cmd --prefix dashboard test -- --run TaskDetailPage`

Expected: missing component failure.

- [ ] **Step 3: Implement task overview and detail views**

Display actual state strings translated through a single map. `completed` means task completion, not confirmed vulnerability. `waiting_authorization`, `blocked`, and `not_tested` must remain visually distinct.

- [ ] **Step 4: Implement SSE reconnect with last event cursor**

The hook stores the last event ID only in component/session memory, reconnects with a bounded exponential delay, then calls the REST event endpoint to fill any gap before reopening SSE.

- [ ] **Step 5: Virtualize or window the event log**

Render at most the visible event slice while retaining the complete redacted event list in state. Provide level, stage, and tool filters plus a clear “已脱敏” indicator.

- [ ] **Step 6: Run component and build tests**

Run:

```powershell
runtime\node\npm.cmd --prefix dashboard test -- --run
runtime\node\npm.cmd --prefix dashboard run build
```

Expected: all pass.

- [ ] **Step 7: Commit task views**

```powershell
git add -- dashboard/src
git commit -m "feat: visualize live task stages and events"
```

### Task 8: Add five-lab dashboard, reports, controls, and history

**Files:**
- Create: `dashboard/src/pages/LocalLabsPage.tsx`
- Create: `dashboard/src/pages/ReportsPage.tsx`
- Create: `dashboard/src/pages/TaskHistoryPage.tsx`
- Create: `dashboard/src/components/SafeTaskControls.tsx`
- Create: `dashboard/src/components/ReportPreview.tsx`
- Test: `dashboard/src/pages/LocalLabsPage.test.tsx`
- Test: `dashboard/src/components/SafeTaskControls.test.tsx`

- [ ] **Step 1: Write failing per-lab and confirmation tests**

```tsx
it('shows all five fixed loopback labs independently', async () => {
  render(<LocalLabsPage />)
  for (const name of ['Juice Shop', 'DVWA', 'WebGoat', 'VAmPI', 'Business API']) {
    expect(await screen.findByText(name)).toBeInTheDocument()
  }
})

it('requires confirmation before cancel', async () => {
  render(<SafeTaskControls runId="run-1" state="running" />)
  await user.click(screen.getByRole('button', {name: '停止任务'}))
  expect(screen.getByText('安全停止会在当前操作完成后生效')).toBeInTheDocument()
})
```

- [ ] **Step 2: Verify tests fail**

Run: `runtime\node\npm.cmd --prefix dashboard test -- --run LocalLabsPage SafeTaskControls`

Expected: missing component failures.

- [ ] **Step 3: Implement five-lab cards and controls**

Each lab card shows lifecycle, current round, discovery, controlled validation, adjudication, score, report, and error independently. Starting validation can only target the fixed inventory returned by the backend.

- [ ] **Step 4: Implement safe report preview**

Reuse the server report allowlist. Render Markdown as sanitized HTML or text, JSON as formatted text, and HTML reports as source/text unless an explicit sanitizer test proves safe. Never execute report scripts.

- [ ] **Step 5: Implement task history and interrupted-task recovery prompts**

Recovery UI must explain that authorized tasks will require a fresh Scope/time-window confirmation; local tasks may resume from a valid checkpoint.

- [ ] **Step 6: Run tests and build**

Run: `runtime\node\npm.cmd --prefix dashboard test -- --run; runtime\node\npm.cmd --prefix dashboard run build`

Expected: all pass and build succeeds.

- [ ] **Step 7: Commit dashboard workflows**

```powershell
git add -- dashboard/src
git commit -m "feat: add lab reports controls and task history"
```

### Task 9: Verify the browser dashboard locally

**Files:**
- Create: `tests/browser/test_dashboard.spec.ts`
- Create: `validation/task-visualization/dashboard-verification.md`
- Modify: `USER_MANUAL.md`

- [ ] **Step 1: Add Playwright smoke flows**

Cover dashboard load, create local task, task detail updates, pause confirmation, cancel confirmation, report preview, reload and reconnect, keyboard navigation, and blocked API calls without a token.

- [ ] **Step 2: Start the backend on loopback only**

Run using the project-local Python:

```powershell
runtime\python312\python.exe -m src_auto.dashboard.app --host 127.0.0.1 --port 0 --token-file runtime\session-token.test
```

Expected: startup JSON reports a loopback URL and selected port; the token file is consumed and deleted.

- [ ] **Step 3: Run browser tests at two viewport sizes**

Run:

```powershell
runtime\node\npx.cmd playwright test tests/browser/test_dashboard.spec.ts --project=chromium
```

Expected: all flows pass at 1366×768 and 1920×1080.

- [ ] **Step 4: Verify no external frontend dependencies are requested**

Fail the test if any request host is not `127.0.0.1` or `localhost`. Record `external_frontend_requests=0`.

- [ ] **Step 5: Run the complete Python and frontend suites**

Run:

```powershell
runtime\python312\python.exe -m unittest discover -s tests -p 'test_*.py'
runtime\node\npm.cmd --prefix dashboard test -- --run
runtime\node\npm.cmd --prefix dashboard run build
```

Expected: all commands exit 0; save exact counts and versions.

- [ ] **Step 6: Commit verification evidence and documentation**

```powershell
git add -- tests/browser validation/task-visualization/dashboard-verification.md USER_MANUAL.md
git commit -m "test: verify local real-time dashboard"
```

## Completion gate

This plan is complete only when the Python, component, build, and Playwright suites pass; the SSE stream reconnects without gaps or duplicated state transitions; every report link resolves through the project-root allowlist; the browser console has no unhandled errors; the frontend makes zero external requests; and one local five-lab task is observable from creation through its honest terminal state.

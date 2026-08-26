# Authorized Target Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a human-gated authorized-target task flow that visualizes every planned and executed action, enforces the recorded scope and time window before every request, and never submits findings automatically.

**Architecture:** An immutable `AuthorizationSnapshot` is created from the user-entered target, program rules, allowed hosts/ports, testing window, automation permission, rate limit, and exclusions. Creating a task does not send network traffic. A separate confirmation step binds a short-lived nonce to the exact snapshot hash and current desktop session. The authorized adapter checks that gate plus `ScopeGuard` before every request and redirect. The dashboard renders scope, planned actions, blocks, evidence, and pause/cancel state from the common `TaskEvent` stream.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, existing `ScopeGuard`/`live_plan`/`runtime_policy`, SQLite + JSONL events, React/TypeScript dashboard, pytest, Playwright, local Business API lab as the only integration target.

---

## Non-negotiable safety boundaries

- Tests in this plan may target only loopback-hosted local labs.
- Entering or saving a real target must not trigger DNS, HTTP, TLS, port, or scanner activity.
- A task may execute only after a distinct human confirmation of the exact immutable snapshot.
- Scope, time window, automation permission, request budget, and redirect destination are checked before every network action.
- Default online actions are non-destructive `GET`, `HEAD`, and explicitly approved scanner-safe requests.
- Destructive payloads, denial of service, password attacks, bulk personal-data collection, arbitrary object-ID enumeration, and automatic platform submission are out of scope.
- The user remains responsible for the final vulnerability judgment, evidence minimization, and submission to 补天.

## Task 1: Model immutable authorization snapshots

**Files:**

- Create: `src_auto/authorization_gate.py`
- Create: `tests/test_authorization_gate.py`
- Modify: `src_auto/store.py`

**Step 1: Write failing snapshot tests**

```python
def test_snapshot_hash_changes_when_any_safety_field_changes():
    original = snapshot(allowed_hosts=["127.0.0.1"], max_requests=25)
    changed = snapshot(allowed_hosts=["127.0.0.1"], max_requests=26)
    assert original.digest != changed.digest


def test_snapshot_rejects_missing_time_window_or_automation_permission():
    with pytest.raises(ValueError):
        snapshot(time_window=None)
    with pytest.raises(ValueError):
        snapshot(automation_allowed=None)
```

**Step 2: Run and confirm failure**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorization_gate.py -q
```

Expected: import failure because `authorization_gate.py` does not exist.

**Step 3: Implement canonical snapshots**

The immutable model must include:

```python
@dataclass(frozen=True)
class AuthorizationSnapshot:
    target_name: str
    start_urls: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    excluded_paths: tuple[str, ...]
    window_start_utc: datetime
    window_end_utc: datetime
    automation_allowed: bool
    allowed_methods: tuple[str, ...]
    max_requests: int
    max_concurrency: int
    max_requests_per_second: float
    rule_source: str
    rule_captured_at_utc: datetime
```

Canonicalize host case, URL ports, path prefixes, method order, and timestamps before SHA-256 hashing. Store the JSON and digest in SQLite; never mutate a saved snapshot.

**Step 4: Run tests**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorization_gate.py -q
```

Expected: all snapshot, canonicalization, hash-change, expiry, and persistence tests pass.

**Step 5: Commit**

```powershell
git add src_auto/authorization_gate.py src_auto/store.py tests/test_authorization_gate.py
git commit -m "feat: add immutable authorization snapshots"
```

## Task 2: Create authorized tasks without network side effects

**Files:**

- Modify: `src_auto/dashboard/api.py`
- Modify: `src_auto/dashboard/schemas.py`
- Create: `tests/test_authorized_task_creation.py`

**Step 1: Write the failing no-network test**

```python
def test_creating_authorized_task_performs_no_network(monkeypatch, client):
    attempted = []
    monkeypatch.setattr("socket.create_connection", lambda *a, **k: attempted.append(a))

    response = client.post("/api/v1/tasks/authorized", json=local_authorized_payload())

    assert response.status_code == 201
    assert response.json()["state"] == "waiting_authorization"
    assert attempted == []
```

**Step 2: Run and confirm failure**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_task_creation.py -q
```

Expected: 404 because the route does not exist.

**Step 3: Implement the draft route**

`POST /api/v1/tasks/authorized` must:

1. validate and canonicalize the form;
2. save a new authorization snapshot;
3. create a task in `waiting_authorization`;
4. emit `task.created` and `authorization.required` events;
5. return the snapshot digest and human-readable summary;
6. perform no network or subprocess activity.

Do not accept a raw command, scanner argument string, credential, cookie, or payload in this endpoint.

**Step 4: Run tests**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_task_creation.py -q
```

Expected: route tests pass and the network spy remains empty.

**Step 5: Commit**

```powershell
git add src_auto/dashboard/api.py src_auto/dashboard/schemas.py tests/test_authorized_task_creation.py
git commit -m "feat: create gated authorized task drafts"
```

## Task 3: Require a short-lived human confirmation

**Files:**

- Modify: `src_auto/authorization_gate.py`
- Modify: `src_auto/dashboard/api.py`
- Create: `tests/test_authorized_task_confirmation.py`

**Step 1: Write failing confirmation tests**

Cover:

- valid nonce + current session + matching snapshot digest -> `queued`;
- expired nonce -> rejected;
- reused nonce -> rejected;
- different snapshot digest -> rejected;
- changed rules or time window -> new confirmation required;
- confirmation never starts a task when `automation_allowed` is false;
- confirmation itself makes zero network calls.

**Step 2: Run and confirm failure**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_task_confirmation.py -q
```

**Step 3: Implement the confirmation endpoint**

`POST /api/v1/tasks/{task_id}/authorization/confirm` accepts:

```json
{
  "snapshot_digest": "sha256:...",
  "confirmation_nonce": "single-use-short-lived-value",
  "confirmed": true
}
```

The server must bind the nonce to the current desktop session token, task ID, snapshot digest, and expiry. On success it emits `authorization.confirmed`; it does not execute until the orchestrator dequeues it.

**Step 4: Run tests**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_task_confirmation.py -q
```

Expected: all confirmation and replay tests pass.

**Step 5: Commit**

```powershell
git add src_auto/authorization_gate.py src_auto/dashboard/api.py tests/test_authorized_task_confirmation.py
git commit -m "security: require per-task authorization confirmation"
```

## Task 4: Enforce scope and budgets before every request and redirect

**Files:**

- Create: `src_auto/task_adapters/authorized_target.py`
- Modify: `src_auto/scope.py`
- Modify: `src_auto/runtime_policy.py`
- Create: `tests/test_authorized_target_adapter.py`

**Step 1: Write failing enforcement tests**

```python
@pytest.mark.parametrize(
    "url,allowed",
    [
        ("http://127.0.0.1:18090/api/products", True),
        ("http://127.0.0.1:18091/api/products", False),
        ("http://localhost:18090/api/products", False),
        ("https://example.com/", False),
    ],
)
def test_scope_is_checked_for_every_destination(url, allowed, adapter):
    assert adapter.can_request(url, method="GET") is allowed
```

Also cover redirects, DNS rebinding defense, method allowlist, request count, concurrency, rate limit, excluded paths, window expiry during a task, pause/cancel, and subprocess argument generation.

**Step 2: Run and confirm failure**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_target_adapter.py -q
```

Expected: failures because the adapter does not exist.

**Step 3: Implement an event-producing adapter**

Before each request:

1. reload current task state and stop if paused/cancelled;
2. verify snapshot digest and current UTC time window;
3. canonicalize URL and resolve host;
4. check scheme, exact host, explicit port, excluded path, and method;
5. check request/concurrency/rate budgets;
6. emit `network.request.planned`;
7. execute the single permitted action;
8. emit redacted `network.request.completed` or `network.request.blocked`.

Disable automatic redirects. Validate every `Location` destination before making a new request. Never derive an unbounded sequence of object IDs. Any future IDOR helper must compare only user-supplied test objects and identities within a separately confirmed plan.

**Step 4: Run tests**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_target_adapter.py -q
```

Expected: all allow/block, redirect, budget, expiry, and cancellation tests pass.

**Step 5: Commit**

```powershell
git add src_auto/task_adapters/authorized_target.py src_auto/scope.py src_auto/runtime_policy.py tests/test_authorized_target_adapter.py
git commit -m "security: enforce authorized request boundaries"
```

## Task 5: Build the Chinese authorization and progress screens

**Files:**

- Create: `dashboard/src/pages/AuthorizedTargetPage.tsx`
- Create: `dashboard/src/features/authorization/AuthorizationForm.tsx`
- Create: `dashboard/src/features/authorization/ConfirmationDialog.tsx`
- Create: `dashboard/src/features/authorization/ScopeSummary.tsx`
- Create: `dashboard/src/features/tasks/BlockedActionCard.tsx`
- Create: `dashboard/src/features/authorization/AuthorizationForm.test.tsx`
- Modify: `dashboard/src/App.tsx`

**Step 1: Verify the Figma gate**

Do not implement this task until the approved Figma file contains:

- target and project metadata form;
- allowed hosts/ports and excluded paths editor;
- time-window and rate-budget controls;
- automation-permission statement;
- immutable confirmation summary with digest suffix;
- waiting, queued, running, blocked, paused, cancelled, failed, and completed states;
- explicit “不会自动提交补天” notice.

Export the approved node IDs and visual comparison screenshots to `docs/design/figma-authorized-target-map.md`.

**Step 2: Write failing component tests**

Tests must prove:

- saving a draft does not display “正在扫描”;
- start button is unavailable before confirmation;
- the confirmation dialog displays hosts, ports, time window, exclusions, methods, and request budget;
- editing any safety field invalidates the previous confirmation;
- blocked actions show a Chinese reason and do not offer a bypass button;
- automatic submission is never offered.

**Step 3: Run and confirm failure**

```powershell
.\runtime\node\npm.cmd --prefix dashboard test -- AuthorizationForm.test.tsx
```

**Step 4: Implement the approved Figma flow**

Use typed API clients. The form must call only the draft endpoint. The dialog must require an explicit checked statement and confirmation button. The progress view must consume the common task event model and visually separate planned, allowed, completed, failed, and blocked actions.

**Step 5: Run tests and visual comparison**

```powershell
.\runtime\node\npm.cmd --prefix dashboard test -- AuthorizationForm.test.tsx
.\runtime\node\npm.cmd --prefix dashboard run build
```

Expected: component tests and build pass; screenshots match the approved Figma structure at desktop and minimum supported window sizes.

**Step 6: Commit**

```powershell
git add dashboard/src docs/design/figma-authorized-target-map.md
git commit -m "feat: add authorized target review flow"
```

## Task 6: Add a loopback-only authorized-target simulator

**Files:**

- Create: `tests/fixtures/authorized_target/business_api_scope.json`
- Create: `tests/fixtures/authorized_target/business_api_rules.md`
- Create: `tools/run_authorized_target_simulation.py`
- Create: `tests/test_authorized_target_simulation.py`

**Step 1: Write the failing simulation test**

The test must start the local Business API lab, create a draft, confirm it, run a small read-only plan, pause/resume once, and prove all destinations are `127.0.0.1` on the declared port.

**Step 2: Run and confirm failure**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_target_simulation.py -q
```

**Step 3: Implement the simulator**

The simulator must use the same public API and adapter as a future real authorized task. Do not add a test-only bypass for scope or authorization. Capture:

- authorization snapshot and confirmation event;
- planned/completed/blocked requests;
- stage timings;
- pause/resume timestamps;
- finding candidates and redacted evidence pointers;
- final counters and terminal state.

**Step 4: Run the simulation test**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_target_simulation.py -q
```

Expected: pass; `external_targets_contacted = 0`.

**Step 5: Commit**

```powershell
git add tests/fixtures/authorized_target tools/run_authorized_target_simulation.py tests/test_authorized_target_simulation.py
git commit -m "test: simulate authorized target workflow locally"
```

## Task 7: Verify expiry, scope drift, redirect, and recovery paths

**Files:**

- Create: `tests/test_authorized_target_safety_matrix.py`
- Create: `tests/e2e/authorized-target.spec.ts`
- Create: `docs/validation/authorized-target-safety-matrix.md`

**Step 1: Implement the backend safety matrix**

Required cases:

| Case | Expected outcome |
|---|---|
| Time window expires before dequeue | Task blocked without request |
| Time window expires mid-run | Next action blocked; task stops safely |
| Allowed port changes | Old confirmation invalidated |
| Excluded path changes | Old confirmation invalidated |
| Redirect leaves scope | Redirect blocked and event emitted |
| Host resolves outside approved addresses | Request blocked |
| Request budget exhausted | Further action blocked |
| User pauses | No new requests after pause checkpoint |
| User cancels | Terminal cancelled state; no resume |
| Backend restarts | Waiting/running task recovers to review-required state |

**Step 2: Implement the browser journey**

Playwright must exercise the entire flow against the local Business API lab: draft, review, confirm, run, observe, pause, resume, open evidence, cancel a second task, and verify the absence of an automatic submission control.

**Step 3: Run the safety suites**

```powershell
.\runtime\python312\python.exe -m pytest tests/test_authorized_target_safety_matrix.py -q
.\runtime\node\npx.cmd --prefix dashboard playwright test tests/e2e/authorized-target.spec.ts
```

Expected: all cases pass with no destination outside loopback.

**Step 4: Record evidence and commit**

```powershell
git add tests/test_authorized_target_safety_matrix.py tests/e2e/authorized-target.spec.ts docs/validation/authorized-target-safety-matrix.md
git commit -m "test: verify authorized target safety matrix"
```

## Task 8: Run the final local-only safety acceptance

**Files:**

- Create: `tools/accept_authorized_target_flow.ps1`
- Create: `docs/validation/authorized-target-acceptance.md`
- Modify: `docs/使用手册.md`

**Step 1: Build one acceptance command**

The command must run the focused unit, API, component, Playwright, and local simulator suites and then write a machine-readable summary under `reports/acceptance`.

**Step 2: Execute acceptance**

```powershell
.\tools\accept_authorized_target_flow.ps1
```

Required final assertions:

```text
authorized_drafts_created >= 1
human_confirmations_recorded >= 1
scope_checks_before_requests = 100%
redirects_checked_before_follow = 100%
external_targets_contacted = 0
destructive_actions_executed = 0
automatic_submissions = 0
unredacted_secrets_in_artifacts = 0
```

**Step 3: Update the user manual**

Document:

- how to transcribe 补天 project rules and target scope;
- how to set the time window and request budget;
- what saving, confirming, starting, pausing, cancelling, and blocking mean;
- how to read evidence and manually judge candidates;
- how to submit manually after independent confirmation;
- why a saved target never starts automatically.

**Step 4: Commit**

```powershell
git add tools/accept_authorized_target_flow.ps1 docs/validation/authorized-target-acceptance.md docs/使用手册.md
git commit -m "docs: accept authorized target progress flow"
```

## Completion gate

This plan is complete only when:

- creating and editing a target causes zero network activity;
- every execution has a fresh, single-use human confirmation for an immutable snapshot;
- every request and redirect is checked against scope, window, methods, exclusions, rate, concurrency, and total budget;
- pause, cancel, expiry, scope drift, restart, and redirect escape all fail safely;
- the UI provides complete Chinese progress and block explanations;
- local simulation proves the full flow without contacting external systems;
- candidate findings remain subject to manual evidence review and manual 补天 submission.

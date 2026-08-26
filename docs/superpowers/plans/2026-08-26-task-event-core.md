# SRC-Auto Task Event Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent, typed task event engine and connect the fixed five-lab validation to it without changing existing safety boundaries or report outputs.

**Architecture:** Extend the existing SQLite `Store`, `runs`, `events`, and `checkpoints` rather than creating another database. A focused `TaskOrchestrator` owns legal state transitions and cooperative pause/cancel flags; adapters emit structured events through a small sink interface.

**Tech Stack:** Standard-library Python core kept compatible with the current Python 3.8 baseline during this phase and executed by the project-local Python 3.12 runtime after Phase 2, `sqlite3`, dataclasses, existing `unittest`, existing local-lab runner and `data/src_auto.sqlite3`.

---

### Task 1: Define task states, stages, events, and legal transitions

**Files:**
- Create: `src_auto/task_events.py`
- Test: `tests/test_task_events.py`

- [ ] **Step 1: Write failing state and serialization tests**

```python
import unittest

from src_auto.task_events import TaskEvent, TaskState, assert_transition


class TaskEventTests(unittest.TestCase):
    def test_running_can_pause_or_finish_but_cannot_return_to_created(self):
        assert_transition(TaskState.RUNNING, TaskState.PAUSING)
        assert_transition(TaskState.RUNNING, TaskState.COMPLETED)
        with self.assertRaises(ValueError):
            assert_transition(TaskState.RUNNING, TaskState.CREATED)

    def test_event_mapping_is_structured_and_redacted_by_default(self):
        event = TaskEvent(
            event_type="stage_started",
            stage="surface_discovery",
            state=TaskState.RUNNING,
            progress=35,
            message_zh="正在发现本地入口",
            target_mode="local_lab",
            network_contact="loopback",
        )
        mapping = event.to_mapping()
        self.assertEqual(mapping["schema_version"], 1)
        self.assertTrue(mapping["redacted"])
        self.assertEqual(mapping["progress"], 35)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m unittest tests.test_task_events -v`

Expected: `ModuleNotFoundError: No module named 'src_auto.task_events'`.

- [ ] **Step 3: Implement the minimal typed event module**

```python
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict


class TaskState(str, Enum):
    CREATED = "created"
    WAITING_AUTHORIZATION = "waiting_authorization"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"


LEGAL_TRANSITIONS = {
    TaskState.CREATED: {TaskState.WAITING_AUTHORIZATION, TaskState.QUEUED, TaskState.BLOCKED},
    TaskState.WAITING_AUTHORIZATION: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.QUEUED: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.RUNNING: {TaskState.PAUSING, TaskState.CANCELLING, TaskState.COMPLETED, TaskState.FAILED, TaskState.BLOCKED},
    TaskState.PAUSING: {TaskState.PAUSED, TaskState.FAILED},
    TaskState.PAUSED: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.CANCELLING: {TaskState.CANCELLED, TaskState.FAILED},
    TaskState.INTERRUPTED: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.BLOCKED},
}


def assert_transition(current: TaskState, target: TaskState) -> None:
    if target not in LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError("invalid_state_transition:{}:{}".format(current.value, target.value))


@dataclass(frozen=True)
class TaskEvent:
    event_type: str
    stage: str
    state: TaskState
    progress: int
    message_zh: str
    target_mode: str
    network_contact: str
    tool: str = ""
    counters: Dict[str, int] = field(default_factory=dict)
    error_code: str = ""
    redacted: bool = True
    schema_version: int = 1

    def to_mapping(self) -> Dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        value["progress"] = max(0, min(100, int(self.progress)))
        return value
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `python -m unittest tests.test_task_events -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the event contract**

```powershell
git add -- src_auto/task_events.py tests/test_task_events.py
git commit -m "feat: define persistent task event contract"
```

### Task 2: Add task runtime snapshots and event cursors to Store

**Files:**
- Modify: `src_auto/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Add failing Store migration and cursor tests**

```python
def test_task_runtime_and_event_cursor_survive_reopen(self):
    run_id = self.store.create_run("local-lab", "scope-hash", "local")
    self.store.create_task_runtime(run_id, "local_lab", "五靶场本地验收")
    first = self.store.append_task_event(run_id, {"event_type": "task_created", "progress": 0})
    second = self.store.append_task_event(run_id, {"event_type": "stage_started", "progress": 10})
    self.assertGreater(second, first)
    self.store.close()

    reopened = Store(self.path)
    self.assertEqual(reopened.get_task_runtime(run_id)["display_name"], "五靶场本地验收")
    self.assertEqual([item["id"] for item in reopened.list_task_events(run_id, after_id=first)], [second])
```

- [ ] **Step 2: Run the Store test and verify the missing methods fail**

Run: `python -m unittest tests.test_store.StoreTests.test_task_runtime_and_event_cursor_survive_reopen -v`

Expected: `AttributeError` for `create_task_runtime`.

- [ ] **Step 3: Add the task runtime schema migration**

Add this table inside `Store._init_schema()`:

```sql
CREATE TABLE IF NOT EXISTS task_runtime (
    run_id TEXT PRIMARY KEY,
    task_kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    current_stage TEXT NOT NULL DEFAULT 'policy_check',
    state TEXT NOT NULL DEFAULT 'created',
    progress INTEGER NOT NULL DEFAULT 0,
    network_contact TEXT NOT NULL DEFAULT 'none',
    pause_requested INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    last_event_id INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_code TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_events_run_id_id ON events(run_id, id);
```

- [ ] **Step 4: Implement focused Store methods**

```python
def create_task_runtime(self, run_id: str, task_kind: str, display_name: str) -> None:
    now = utc_now()
    self.conn.execute(
        "INSERT INTO task_runtime(run_id,task_kind,display_name,heartbeat_at) VALUES(?,?,?,?)",
        (run_id, task_kind, display_name, now),
    )
    self.conn.commit()

def append_task_event(self, run_id: str, payload: Dict[str, Any], level: str = "info") -> int:
    message = str(payload.get("message_zh", payload.get("event_type", "task_event")))
    cursor = self.conn.execute(
        "INSERT INTO events(run_id,level,message,payload_json,created_at) VALUES(?,?,?,?,?)",
        (run_id, level, message, json.dumps(payload, ensure_ascii=False, sort_keys=True), utc_now()),
    )
    event_id = int(cursor.lastrowid)
    self.conn.execute(
        "UPDATE task_runtime SET last_event_id=?,heartbeat_at=? WHERE run_id=?",
        (event_id, utc_now(), run_id),
    )
    self.conn.commit()
    return event_id
```

Also add `get_task_runtime()`, `list_task_runtime()`, `list_task_events(after_id=0)`, `update_task_runtime()`, `request_pause()`, `request_cancel()`, and `clear_task_requests()` with parameterized SQL only.

- [ ] **Step 5: Run Store and migration tests**

Run: `python -m unittest tests.test_store -v`

Expected: all Store tests pass, including reopening an existing database created before `task_runtime` existed.

- [ ] **Step 6: Commit the Store migration**

```powershell
git add -- src_auto/store.py tests/test_store.py
git commit -m "feat: persist task runtime snapshots and cursors"
```

### Task 3: Add a single redaction boundary for task events

**Files:**
- Create: `src_auto/task_redaction.py`
- Test: `tests/test_task_redaction.py`

- [ ] **Step 1: Write failing secret-redaction tests**

```python
def test_redacts_headers_tokens_and_nested_values(self):
    value = redact_event_payload({
        "headers": {"Authorization": "Bearer secret", "Cookie": "sid=abc", "X-Test": "ok"},
        "api_key": "sk-example",
        "nested": [{"set-cookie": "session=hidden"}],
    })
    self.assertEqual(value["headers"]["Authorization"], "[REDACTED]")
    self.assertEqual(value["headers"]["Cookie"], "[REDACTED]")
    self.assertEqual(value["headers"]["X-Test"], "ok")
    self.assertEqual(value["api_key"], "[REDACTED]")
    self.assertEqual(value["nested"][0]["set-cookie"], "[REDACTED]")
```

- [ ] **Step 2: Verify the test fails before implementation**

Run: `python -m unittest tests.test_task_redaction -v`

Expected: missing module failure.

- [ ] **Step 3: Implement recursive key-based redaction and bounded strings**

```python
SECRET_KEYS = {
    "authorization", "cookie", "set-cookie", "api_key", "apikey",
    "password", "token", "access_token", "refresh_token", "session",
}

def redact_event_payload(value):
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SECRET_KEYS else redact_event_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_event_payload(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:2000]
    return value
```

- [ ] **Step 4: Apply redaction before every `append_task_event()` call**

The Store method must import and apply `redact_event_payload(payload)` before JSON serialization. No adapter may bypass this boundary.

- [ ] **Step 5: Run focused and existing secret tests**

Run: `python -m unittest tests.test_task_redaction tests.test_session_vault tests.test_remote_ai -v`

Expected: all tests pass and no test output contains fixture secrets.

- [ ] **Step 6: Commit redaction**

```powershell
git add -- src_auto/task_redaction.py src_auto/store.py tests/test_task_redaction.py
git commit -m "security: redact structured task events"
```

### Task 4: Implement cooperative orchestration and state transitions

**Files:**
- Create: `src_auto/task_orchestrator.py`
- Test: `tests/test_task_orchestrator.py`

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_task_pauses_only_at_checkpoint_and_resumes(self):
    adapter = FakeAdapter(stages=["policy_check", "target_health", "report_generation"])
    run_id = create_task(self.store)
    self.store.request_pause(run_id)
    result = TaskOrchestrator(self.store).run(run_id, adapter)
    self.assertEqual(result["state"], "paused")
    self.assertEqual(self.store.get_task_runtime(run_id)["current_stage"], "policy_check")

def test_cancelled_task_never_emits_completed(self):
    adapter = FakeAdapter(stages=["policy_check"])
    run_id = create_task(self.store)
    self.store.request_cancel(run_id)
    TaskOrchestrator(self.store).run(run_id, adapter)
    event_types = [item["payload"]["event_type"] for item in self.store.list_task_events(run_id)]
    self.assertIn("task_cancelled", event_types)
    self.assertNotIn("task_completed", event_types)
```

- [ ] **Step 2: Verify tests fail for the missing orchestrator**

Run: `python -m unittest tests.test_task_orchestrator -v`

Expected: missing module failure.

- [ ] **Step 3: Implement `TaskAdapter` and `TaskOrchestrator`**

```python
class TaskAdapter:
    def stages(self):
        raise NotImplementedError

    def run_stage(self, stage, emit, checkpoint):
        raise NotImplementedError


class TaskOrchestrator:
    def __init__(self, store):
        self.store = store

    def run(self, run_id, adapter):
        self._transition(run_id, "running")
        for stage in adapter.stages():
            request = self.store.get_task_requests(run_id)
            if request["cancel_requested"]:
                return self._cancel(run_id, stage)
            if request["pause_requested"]:
                return self._pause(run_id, stage)
            self._stage_started(run_id, stage)
            adapter.run_stage(stage, lambda event: self.emit(run_id, event), self._checkpoint(run_id, stage))
            self._stage_completed(run_id, stage)
        return self._complete(run_id)
```

Implement `_transition()` through `TaskState` and `assert_transition()`. Every state change and exception must produce one structured event and one runtime snapshot update in the same SQLite transaction.

- [ ] **Step 4: Add interruption detection**

Add `mark_stale_tasks_interrupted(max_age_seconds=30)` and test that terminal states are never rewritten while stale `running`, `pausing`, and `cancelling` tasks become `interrupted`.

- [ ] **Step 5: Run orchestration and pipeline tests**

Run: `python -m unittest tests.test_task_orchestrator tests.test_pipeline tests.test_failures -v`

Expected: all tests pass.

- [ ] **Step 6: Commit orchestration**

```powershell
git add -- src_auto/task_orchestrator.py tests/test_task_orchestrator.py
git commit -m "feat: add cooperative task orchestration"
```

### Task 5: Instrument the five-lab validator with an event sink

**Files:**
- Create: `src_auto/task_adapters.py`
- Modify: `tools/run_local_lab_validation.py`
- Test: `tests/test_task_adapters.py`
- Modify: `tests/test_local_lab_validation.py`

- [ ] **Step 1: Write failing local-lab event-order tests**

```python
def test_five_lab_adapter_emits_per_lab_and_final_events(self):
    events = []
    adapter = LocalLabAdapter(run_validation=fake_validation)
    adapter.run_stage("controlled_validation", events.append, {})
    pairs = [(item["event_type"], item.get("lab_id")) for item in events]
    self.assertIn(("lab_started", "juice-shop"), pairs)
    self.assertIn(("lab_started", "business-api"), pairs)
    self.assertEqual(events[-1]["event_type"], "stage_progress")
```

- [ ] **Step 2: Verify the missing adapter test fails**

Run: `python -m unittest tests.test_task_adapters -v`

Expected: missing `LocalLabAdapter`.

- [ ] **Step 3: Add optional event emission to `run_validation()`**

Change the signature without breaking existing callers:

```python
def run_validation(repeat_rounds: int = 0, event_sink=None):
    emit = event_sink or (lambda event: None)
    emit({"event_type": "stage_started", "stage": "dependency_check", "progress": 5})
    # existing validation logic remains the source of reports and scores
```

Emit bounded events before and after each lab lifecycle, round, discovery, schema smoke, ZAP parse, adjudication, scoring, and final report write. Do not emit raw responses, cookies, tokens, or scanner command lines containing secrets.

- [ ] **Step 4: Implement `LocalLabAdapter`**

```python
class LocalLabAdapter(TaskAdapter):
    ORDER = (
        "policy_check", "dependency_check", "target_health",
        "surface_discovery", "controlled_validation", "normalize",
        "deduplicate", "candidate_triage", "report_generation",
    )

    def stages(self):
        return self.ORDER
```

The adapter translates validator callbacks to `TaskEvent`; it must not duplicate actual scanning logic.

- [ ] **Step 5: Run focused validation tests**

Run: `python -m unittest tests.test_task_adapters tests.test_local_lab_validation -v`

Expected: all tests pass; existing final JSON and Markdown fixtures are unchanged except for deterministic timestamps already covered by tests.

- [ ] **Step 6: Commit the five-lab adapter**

```powershell
git add -- src_auto/task_adapters.py tools/run_local_lab_validation.py tests/test_task_adapters.py tests/test_local_lab_validation.py
git commit -m "feat: stream five-lab validation events"
```

### Task 6: Add task lifecycle CLI commands

**Files:**
- Modify: `src_auto/cli.py`
- Test: `tests/test_task_cli.py`

- [ ] **Step 1: Write failing CLI contract tests**

```python
def test_task_local_lab_creates_a_queued_local_task(self):
    result = run_cli("task-local-lab", "--name", "五靶场本地验收", "--json")
    self.assertEqual(result["task_kind"], "local_lab")
    self.assertEqual(result["state"], "queued")
    self.assertFalse(result["network_contact"] == "authorized_target")

def test_task_cancel_is_idempotent(self):
    run_id = create_local_task()
    first = run_cli("task-cancel", "--run-id", run_id, "--json")
    second = run_cli("task-cancel", "--run-id", run_id, "--json")
    self.assertEqual(first["status"], "cancel_requested")
    self.assertEqual(second["status"], "cancel_requested")
```

- [ ] **Step 2: Verify commands are missing**

Run: `python -m unittest tests.test_task_cli -v`

Expected: argparse rejects `task-local-lab`.

- [ ] **Step 3: Add commands without enabling authorized execution**

Add parsers and handlers for:

```text
task-local-lab
task-status
task-events
task-pause
task-resume
task-cancel
task-export
```

`task-local-lab` may enqueue only the fixed local inventory. No command in this task accepts an arbitrary URL.

- [ ] **Step 4: Run CLI and policy tests**

Run: `python -m unittest tests.test_task_cli tests.test_runtime_policy tests.test_local_labs -v`

Expected: all pass.

- [ ] **Step 5: Commit CLI commands**

```powershell
git add -- src_auto/cli.py tests/test_task_cli.py
git commit -m "feat: expose local task lifecycle commands"
```

### Task 7: Export per-task JSONL audit and summary files

**Files:**
- Create: `src_auto/task_export.py`
- Test: `tests/test_task_export.py`

- [ ] **Step 1: Write failing path-containment and export tests**

```python
def test_export_stays_under_sessions_and_uses_event_order(self):
    paths = export_task(store, run_id, project_root)
    self.assertTrue(str(paths["events"]).startswith(str(project_root / "sessions")))
    lines = [json.loads(line) for line in paths["events"].read_text(encoding="utf-8").splitlines()]
    self.assertEqual([item["id"] for item in lines], sorted(item["id"] for item in lines))

def test_export_rejects_run_id_path_traversal(self):
    with self.assertRaises(ValueError):
        export_task(store, "..\\outside", project_root)
```

- [ ] **Step 2: Verify the export module is missing**

Run: `python -m unittest tests.test_task_export -v`

Expected: missing module failure.

- [ ] **Step 3: Implement atomic summary and append-order JSONL export**

Use `Path.resolve()` containment, a temporary sibling file, `os.replace()`, UTF-8 without BOM for JSON, and one event object per line. Exported payloads must already be redacted by the Store boundary.

- [ ] **Step 4: Run export and report tests**

Run: `python -m unittest tests.test_task_export tests.test_store tests.test_validation -v`

Expected: all pass.

- [ ] **Step 5: Commit exports**

```powershell
git add -- src_auto/task_export.py tests/test_task_export.py
git commit -m "feat: export task audit journals"
```

### Task 8: Verify the event core against the fixed local environment

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `OPERATIONS.md`
- Create: `validation/task-visualization/event-core-verification.md`

- [ ] **Step 1: Run all focused tests**

Run:

```powershell
python -m unittest tests.test_task_events tests.test_task_redaction tests.test_task_orchestrator tests.test_task_adapters tests.test_task_cli tests.test_task_export -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the full Python suite**

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Expected: exit code 0; record the exact test count instead of copying a planned count.

- [ ] **Step 3: Run one local five-lab task and inspect the event sequence**

Run:

```powershell
python -m src_auto task-local-lab --name '五靶场事件验收' --run-now --json
```

Expected: only fixed loopback hosts are contacted; terminal state is `completed` or an honestly reported `blocked` dependency state; `events.jsonl` is ordered and contains no secrets.

- [ ] **Step 4: Verify safety counters**

The verification report must record:

```json
{
  "external_targets_contacted": 0,
  "automatic_submissions": 0,
  "secret_leakage": 0,
  "unauthorized_remote_ai_calls": 0
}
```

- [ ] **Step 5: Update documentation with actual commands and results**

Do not describe the dashboard or WebView2 shell as implemented in this phase. Mark only the event core and CLI as available.

- [ ] **Step 6: Commit verification evidence**

```powershell
git add -- README.md ARCHITECTURE.md OPERATIONS.md validation/task-visualization/event-core-verification.md
git commit -m "test: verify persistent local task events"
```

## Completion gate

This plan is complete only when the focused and full Python suites pass, one canonical five-lab task produces an ordered persistent event stream, every task has exactly one terminal state, the event and JSONL artifacts contain no secrets, and the acceptance report proves zero external targets, automatic submissions, and unauthorized remote-AI calls.

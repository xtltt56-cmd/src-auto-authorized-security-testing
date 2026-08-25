# OWASP Regression Lab Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement this plan task-by-task with verification checkpoints.

**Goal:** Add a pinned OWASP WebGoat local target and a safe, repeatable regression harness that verifies previously untested vulnerability classes only on loopback.

**Architecture:** Keep the existing Juice Shop/DVWA Compose project and extend its fixed local inventory with WebGoat on `127.0.0.1:8082`. Add a separate regression layer that uses explicit, non-destructive local cases and a ground-truth matrix; it records evidence and adjudication separately from ZAP control metrics. The default one-click flow remains local-only, and no case is submission-ready automatically.

**Tech Stack:** Python 3.8 stdlib, `unittest`, Docker Compose, OWASP WebGoat `v2025.3` pinned by digest, existing RuntimePolicy/ScopeGuard, JSON artifacts under `validation/autotest`.

---

### Task 1: Extend the fixed local inventory with WebGoat

**Files:**
- Modify: `config/labs/local_labs.json`
- Modify: `docker-compose.local-labs.yml`
- Modify: `config/validation/local_only.json`
- Modify: `src_auto/local_labs.py`
- Test: `tests/test_local_labs.py`

- [x] Write a failing test that the inventory accepts only the WebGoat pinned digest, loopback port `8082`, and health URL `http://127.0.0.1:8082/WebGoat/actuator/health`.
- [x] Run `python -m unittest tests.test_local_labs.LocalLabSpecTests -v`; confirm the new WebGoat assertions fail before configuration changes.
- [x] Add the official WebGoat `v2025.3` digest `sha256:3101bd9e7bcfe122d7ef91e690ef3720de36cc4e86b3d06763a1ddf2e2751a4b`, internal port `8080`, loopback host port `8082`, and a health URL to the inventory.
- [x] Add a Compose `webgoat` service with the pinned digest, `127.0.0.1:8082:8080`, `restart: "no"`, `init: true`, `no-new-privileges`, dropped capabilities, bounded CPU/memory/PIDs, and a `wget` health check because this image does not ship `curl`.
- [x] Add `8082` to the local runtime allowlist and keep `allow_remote_llm=false`.
- [x] Run the focused tests and `docker compose -f docker-compose.local-labs.yml config --quiet`; both pass.

### Task 2: Add a local regression case schema and conservative probe engine

**Files:**
- Create: `config/validation/local_regression_cases.json`
- Create: `src_auto/local_regression.py`
- Test: `tests/test_local_regression.py`

- [x] Write failing tests for case validation: IDs, loopback-only target IDs, allowed methods (`GET`, `POST`), bounded payloads, no shell commands, and explicit expected outcomes.
- [x] Run `python -m unittest tests.test_local_regression -v`; confirm the schema/probe tests fail for the missing module.
- [x] Define six safe cases against local WebGoat/DVWA/Juice Shop surfaces: public surface, unauthenticated access boundaries, authenticated DVWA SQLi surface, and a harmless reflected marker. Unsupported destructive categories remain explicitly out of scope.
- [x] Implement a bounded HTTP probe using `urllib.request`, no redirects, RuntimePolicy preflight, max body/response limits, redacted headers, and no external URL resolution.
- [x] Implement a conservative pass/fail/block adjudicator for regression assertions; it never sets `submission_ready=true` and is separate from vulnerability adjudication.
- [x] Run focused tests and verify no probe can contact a non-loopback host before the network call.

### Task 3: Build authenticated local fixtures without brute force or real data

**Files:**
- Modify: `src_auto/local_regression.py`
- Create: `tools/run_local_regression.py`
- Test: `tests/test_local_regression_runner.py`

- [x] Write failing tests for a fixture lifecycle: prepare local state, create only synthetic accounts/data, run one case, and capture bounded evidence.
- [x] Run the focused runner tests and confirm failure before implementation.
- [x] Implement fixture setup for DVWA using the documented local database/login flow and WebGoat using one random synthetic account; no credential guessing, rate testing, or external identity provider.
- [x] Implement the runner with `--local-only`, bounded `--lab` selection, `--case`, `--repeat-rounds 0..3`, and project-root artifact checks.
- [x] Write per-case artifacts under `validation/autotest/local_regression/<lab>/round_nn/<case_id>.json`, plus `LOCAL_REGRESSION_SCORE.json` and a Chinese human report; response bodies and cookies are not written.
- [x] Run the runner against all six harmless cases and verify the artifacts contain no password, cookie, token, or response body.

### Task 4: Integrate the regression score without conflating it with bounty readiness

**Files:**
- Modify: `tools/run_local_lab_validation.py`
- Modify: `src_auto/cli.py`
- Modify: `tests/test_local_lab_validation.py`
- Create: `validation/autotest/LOCAL_REGRESSION_TEST_REPORT.md`

- [x] Write failing tests for a score document that reports per-case pass/fail/blocked counts separately from `bounty_ready_count=0`.
- [x] Run the focused tests and verify the expected fields are missing before implementation.
- [x] Add the explicit `local-regression` CLI/tool entry point; the desktop flow invokes it only after the local control benchmark and never enables remote execution.
- [x] Aggregate latest-round and per-round metrics, mark unsupported destructive categories in limitations, and keep the official Juice Shop `116/67` Ground Truth separate in the ZAP score.
- [x] Write the Chinese human report with exact counts, limitations, and case-level artifact paths.
- [x] Run focused CLI/report tests and verify the JSON is stable and machine-readable.

### Task 5: Execute, document, and verify

**Files:**
- Modify: `START_SYSTEM.ps1`
- Modify: `README.md`
- Modify: `USER_MANUAL.md`
- Modify: `OPERATIONS.md`
- Modify: `IMPLEMENTATION_REPORT.md`
- Modify: `TEST_REPORT.md`
- Modify: `KNOWN_ISSUES.md`

- [x] Write a failing launcher test that the new regression option is explicit and still only uses loopback.
- [x] Run the launcher test and confirm it fails before wiring the option.
- [x] Add the regression CLI to manual usage and the desktop flow; it remains local-only and performs only non-destructive cases.
- [x] Start WebGoat and verify `healthy` plus HTTP 200/redirect behavior on `127.0.0.1:8082`.
- [x] Execute the bounded local regression matrix for three rounds; all 18 executions pass and unsupported destructive categories remain documented as not run.
- [x] Run the full unittest suite, compile checks, Compose config validation, launcher contract tests, and local-only HTTP/port checks.
- [x] Update documentation with the official repository links, digest, safe scope, exact regression score, and the explicit fact that no bounty-ready finding is produced automatically.

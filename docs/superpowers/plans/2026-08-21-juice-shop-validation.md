# Juice Shop Local Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Validate SRC-Auto only against an operator-started OWASP Juice Shop instance bound to `127.0.0.1:3000`, using local AI only, a post-scan Ground Truth comparison, two measured rounds, and an honest Markdown report.

**Architecture:** A validation profile provides an exact host/port allowlist and hard `AI_PROVIDER=local`, `LOCAL_LLM_ONLY=true`, `ALLOW_REMOTE_LLM=false` controls. The existing ScopeGuard and SafeToolAdapter remain the request gate. Baseline and regression artifacts are stored under `validation/juice-shop/`; Ground Truth is read only for post-scan scoring and never feeds scanner decisions.

**Tech Stack:** Python 3.8 stdlib, existing `unittest`, SQLite Store, local Ollama, existing `httpx`/`katana` binaries when available, Docker Juice Shop when Docker is installed, and JSON/Markdown artifacts under the project root.

---

### Task 1: Freeze validation boundaries

**Files:**
- Create: `config/validation/local_only.json`
- Create: `config/targets/juice-shop-local/scope_confirmed.yaml`
- Create: `src_auto/runtime_policy.py`
- Modify: `src_auto/cli.py`
- Modify: `src_auto/ai.py`
- Test: `tests/test_runtime_policy.py`

- [x] Add exact host/port policy for `localhost` and `127.0.0.1:3000`, local AI-only flags, and concurrency `5`.
- [x] Make remote Provider construction fail closed unless a caller supplies an explicit non-default test/operation override; normal CLI reads the local-only policy and blocks remote review.
- [x] Make ModelRouter reject non-local automatic routes when `LOCAL_LLM_ONLY=true`.
- [x] Add tests for an allowed Juice Shop URL, rejected subdomain, rejected external host, rejected port, remote-provider block, and local model route.
- [x] Run the focused runtime tests in RED then GREEN, followed by the existing suite.

### Task 2: Build Ground Truth and validation data model

**Files:**
- Create: `validation/juice-shop/ground_truth.json`
- Create: `validation/juice-shop/schema.json`
- Create: `src_auto/validation.py`
- Test: `tests/test_validation.py`

- [x] Record challenge metadata only from the local Juice Shop scoreboard/API or the official source definitions; include `challenge_id`, `challenge_name`, `category`, `difficulty`, `expected_vulnerability_type`, `scanner_detectable`, `requires_business_logic`, `requires_authentication`, and `notes`.
- [x] Normalize scanner findings to the requested fields and restrict status to `TRUE_POSITIVE`, `FALSE_POSITIVE`, `POSSIBLE`, and `NOT_VERIFIED`.
- [x] Implement matching and metrics for TP, FP, FN, precision, recall, F1, and scanner-detectable recall; do not inject Ground Truth into scanner input.
- [x] Add tests for matching, unmatched findings, business-logic exclusions, zero denominators, and schema validation.

### Task 3: Run local baseline

**Files:**
- Create: `validation/juice-shop/baseline_results.json`
- Create: `validation/juice-shop/baseline_metrics.json`
- Create/modify: `src_auto/juice_shop.py` only if a small adapter is needed
- Test: `tests/test_juice_shop.py`

- [x] Verify Docker and the exact local endpoint; if Docker is unavailable, record a blocker without contacting any substitute or public target.
- [x] Implement bounded discovery against only `http://127.0.0.1:3000` with concurrency no greater than five and no external-link expansion; execution remains ready for the authorized container.
- [x] Record the unavailable-dependency state, zero remote AI calls/cost, and null unexecuted scan metrics without fabricating runtime measurements.
- [x] Store baseline findings and metrics under the validation directory; Ground Truth comparison is ready for a reachable target.

### Task 4: Make bounded improvements and run regression

**Files:**
- Modify only the smallest files identified by baseline evidence.
- Create: `validation/juice-shop/regression_results.json`
- Create: `validation/juice-shop/regression_metrics.json`

- [x] Prioritize allowlist enforcement, bounded discovery, normalization, evidence, deduplication, local-only AI routing, and timeout/concurrency controls.
- [x] Add a regression test for every changed behavior before implementation.
- [x] Re-run the local control-plane suite; target-level delta metrics remain `NOT_RUN` because the baseline dependency is blocked.
- [x] Do not hard-code Juice Shop vulnerabilities or use Ground Truth to influence detection.

### Task 5: Produce the report and verify delivery

**Files:**
- Create: `JUICE_SHOP_VALIDATION_REPORT.md`
- Modify: `TEST_REPORT.md`, `KNOWN_ISSUES.md`, `USER_MANUAL.md` if the measured state changes.

- [x] Report environment, endpoint, model, tools, baseline/regression data, normalized findings, Ground Truth matching, TP/FP/FN, precision/recall/F1, scanner-detectable recall, missed/false-positive causes, changes, score, API calls/costs, and the three highest-priority next steps.
- [x] Explicitly distinguish a real Juice Shop run from an unavailable-Docker blocker; never report an unexecuted scan as passed.
- [x] Run the full test, compile, diff, and secret hygiene checks before delivery.
- [x] Keep all generated artifacts under `D:\网络安全文件夹\SRC-Auto`; do not modify the preserved sibling artifacts or contact remote AI.

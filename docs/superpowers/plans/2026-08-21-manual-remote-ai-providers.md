# Manual Remote AI Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Add manually confirmed DeepSeek V4 Flash review calls, prepare a disabled OpenAI Responses provider, and preserve local Ollama as the only automatic path.

**Architecture:** A new `src_auto/remote_ai.py` owns sanitized payloads, provider-specific HTTP calls, JSON validation, and cost estimation. The CLI adds network-free preview/status commands and a digest-bound single-call command. SQLite stores remote opinions separately from local triage; there is no monetary or call-count ceiling, but each request is bounded by configured input/output token limits.

**Tech Stack:** Python 3.8 standard library (`urllib`, `json`, `hashlib`, `os`), SQLite, existing `unittest`, existing `ScopeGuard`, `Store`, and `sanitize_finding` conventions. No third-party SDK or API key is committed.

---

### Task 1: Lock provider contracts with failing tests

**Files:**
- Create: `tests/test_remote_ai.py`
- Modify: `tests/test_store.py`

- [x] **Step 1: Write the failing provider tests**

Add tests for `RemoteReviewRequest`, `DeepSeekProvider`, and `OpenAIProvider` that use an injected fake `urlopen` and assert:

```python
request = RemoteReviewRequest.from_finding(finding)
assert request.payload["url"] == "https://example.test/path"
assert "token" not in json.dumps(request.payload).lower()
assert len(request.digest) == 64
```

The DeepSeek fake response must assert the POST path, `Authorization: Bearer ...` header, `deepseek-v4-flash`, non-thinking mode, JSON response format, and a normalized review. The OpenAI fake response must assert `/v1/responses`, `store: false`, no tools, `gpt-5.6-luna`, and strict JSON schema fields. Add failures for missing environment keys, disabled providers, malformed JSON, and HTTP errors.

Add Store tests that expect `insert_ai_review`, `list_ai_reviews`, and a summary of remote call count/estimated USD cost.

- [x] **Step 2: Run the focused tests and verify the expected RED state**

Run:

```powershell
python -m unittest tests.test_remote_ai tests.test_store -v
```

Expected result: import or attribute failures because the remote provider module and review persistence methods do not yet exist.

### Task 2: Implement provider transport and validation

**Files:**
- Create: `src_auto/remote_ai.py`
- Modify: `src_auto/ai.py`

- [x] **Step 1: Implement canonical payload and digest**

Reuse `sanitize_finding`, then add `RemoteReviewRequest.from_finding` that removes query, fragment, credentials, and secrets, caps the fields, adds an unconfirmed-observation instruction, serializes with sorted keys, and computes SHA-256.

- [x] **Step 2: Implement DeepSeek transport**

Use `urllib.request.Request` and `urlopen` with:

```text
POST https://api.deepseek.com/chat/completions
Authorization: Bearer <DEEPSEEK_API_KEY>
model: deepseek-v4-flash
thinking: {"type": "disabled"}
response_format: {"type": "json_object"}
max_tokens: 256
stream: false
```

Read the key only from the configured environment variable. Never include the key in exceptions, returned dictionaries, or logs.

- [x] **Step 3: Implement OpenAI Responses transport**

Use the same sanitized payload with:

```text
POST https://api.openai.com/v1/responses
model: gpt-5.6-luna
store: false
tools: []
max_output_tokens: 256
text.format: strict json_schema
```

Read the key only from `OPENAI_API_KEY`. Keep the provider disabled by configuration until the operator has an independent OpenAI Platform key.

- [x] **Step 4: Normalize and validate output**

Accept only the four allowed dispositions, clamp confidence to `[0, 1]`, cap reasons and suggested checks, parse usage when present, calculate configured estimated USD cost, and raise a typed provider error for empty/malformed/invalid responses.

- [x] **Step 5: Run focused tests and verify GREEN**

Run the same focused command. Expected result: all provider and Store contract tests pass without a live network call.

### Task 3: Persist reviews and expose manual CLI gates

**Files:**
- Modify: `src_auto/store.py`
- Modify: `src_auto/cli.py`
- Modify: `src_auto/scope.py` only if the existing Finding URL decision helper needs a narrow reusable call
- Create: `tests/test_remote_cli.py`

- [x] **Step 1: Write failing CLI gate tests**

Test that `remote-status` does not contact the network, `remote-preview` prints a redacted payload and digest without contact, and `remote-triage` refuses missing `--confirm-external`, a mismatched digest, missing key, disabled provider, Scope mismatch, or STOP. Use a temporary Store and injected provider transport where the CLI boundary permits it; otherwise test the extracted helper directly.

- [x] **Step 2: Add SQLite migration and review methods**

Create `ai_reviews` with run ID, Finding fingerprint, provider/model, payload digest, normalized disposition, confidence, reason, suggested checks JSON, token usage, estimated USD cost, and timestamp. Add migration logic for existing databases and methods to insert/list/summarize reviews. Never overwrite canonical local triage.

- [x] **Step 3: Add `remote-status`**

Report provider/model/enabled/manual-only/key-present state only. Do not probe a remote endpoint and do not print the key or any derived secret value.

- [x] **Step 4: Add `remote-preview`**

Resolve the run and Finding association, verify the Scope decision, build the canonical payload, and print `network_contact: false` plus the digest.

- [x] **Step 5: Add `remote-triage`**

Repeat the preview checks, require `--confirm-external` and an exact `--confirm-digest`, check STOP, read the environment key, send exactly one request, persist the normalized review, and return an explicit status. Do not implement automatic retry or remote fallback.

- [x] **Step 6: Run CLI-focused tests and the existing full suite**

Run:

```powershell
python -m unittest tests.test_remote_ai tests.test_remote_cli tests.test_store -v
python -m unittest discover -s tests -v
```

Expected result: all new gates and the existing local 32-test baseline pass.

### Task 4: Configuration, manual, and operational documentation

**Files:**
- Modify: `config/models.yaml`
- Modify: `USER_MANUAL.md`
- Modify: `README.md`
- Modify: `OPERATIONS.md`
- Modify: `KNOWN_ISSUES.md`
- Modify: `TEST_REPORT.md`
- Modify: `IMPLEMENTATION_REPORT.md`

- [x] **Step 1: Configure providers without secrets**

Add the DeepSeek and disabled OpenAI provider entries, endpoints, models, environment variable names, token limits, and peak price metadata. Do not add a key or a budget ceiling.

- [x] **Step 2: Document manual-only operation**

Document environment setup using placeholders, key rotation after the chat exposure, preview/digest/send commands, data minimization, no automatic fallback, no ChatGPT Plus browser reuse, and the fact that OpenAI remains unverified without an OpenAI Platform key.

- [x] **Step 3: Update test and implementation reports**

Record fake-provider verification and clearly distinguish it from a live DeepSeek probe. Do not claim the provided exposed key was used.

### Task 5: Verification and handoff

**Files:**
- No source changes expected

- [ ] **Step 1: Run static and full verification**

Run:

```powershell
python -m compileall -q src_auto lab tests
python -m unittest discover -s tests -v
git diff --check
```

- [ ] **Step 2: Verify secret hygiene**

Search tracked files and staged diff for `sk-`, `DEEPSEEK_API_KEY=` with a value, `OPENAI_API_KEY=` with a value, `Authorization: Bearer`, and raw test credentials. The expected result is no raw credential.

- [ ] **Step 3: Verify local behavior remains unchanged**

Run `python -m src_auto model-status`, a local-lab E2E, and the PowerShell launcher parser check. Confirm the desktop launcher still cannot enter the remote path.

- [ ] **Step 4: Commit and report**

Commit the implementation and documentation, report that live DeepSeek verification is pending a rotated key set locally, and provide the exact environment-variable and CLI commands without exposing any key.

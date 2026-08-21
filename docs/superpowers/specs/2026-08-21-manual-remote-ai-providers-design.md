# Manual Remote AI Providers Design

Date: 2026-08-21  
Status: implemented; fake-provider and CLI gate verification passed; live DeepSeek probe pending key rotation

## Goal

Add DeepSeek V4 Flash as a manually invoked remote Finding reviewer and prepare an OpenAI Responses API provider that remains disabled until a separate OpenAI Platform API key is supplied. Local Ollama remains the only automatic model path.

## Safety boundary

- Remote providers never participate in automatic fallback.
- The desktop launcher and `run --local-lab` never contact a remote AI service.
- Every remote request requires an operator-selected Finding, a redacted preview, an exact payload digest, and `--confirm-external`.
- Candidate scope files cannot authorize a remote request. The Finding URL must still pass the run's confirmed `ScopeGuard` policy.
- API keys are read only from `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` environment variables.
- Keys, authorization headers, raw cookies, tokens, full request/response bodies, and user data are never stored or printed.
- A remote opinion is advisory. It cannot mark a vulnerability confirmed or submit a report to Butian.

## Non-goals

- No ChatGPT browser automation or reuse of ChatGPT Plus login state.
- No automatic remote failover when Ollama is unavailable.
- No remote web search, computer use, file search, tools, function calls, or agent loops.
- No automatic target discovery, exploitation, login, CAPTCHA handling, or Butian submission.
- No use of the API key pasted into chat; it must be revoked and replaced before a live probe.

## Provider architecture

Create `src_auto/remote_ai.py` with three focused units:

1. `RemoteReviewRequest` builds the canonical sanitized payload and SHA-256 digest.
2. `DeepSeekProvider` sends an OpenAI-compatible Chat Completions request to `https://api.deepseek.com/chat/completions` using `deepseek-v4-flash` in non-thinking JSON mode.
3. `OpenAIProvider` sends a Responses API request to `https://api.openai.com/v1/responses` using `gpt-5.6-luna`, `store: false`, no tools, and strict structured output.

Both providers accept an injected URL opener for deterministic tests and return the same normalized review shape:

```json
{
  "disposition": "manual_review",
  "confidence": 0.0,
  "reason": "Concise reviewer rationale",
  "suggested_checks": [],
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "input_tokens": 0,
  "output_tokens": 0,
  "estimated_cost_usd": 0.0
}
```

Allowed dispositions are `candidate`, `manual_review`, `needs_manual_validation`, and `false_positive`. Invalid remote output fails closed and is not saved as a valid review.

## Configuration

Extend `config/models.yaml` with a `remote_providers` mapping:

```json
{
  "remote_providers": {
    "deepseek": {
      "enabled": true,
      "manual_only": true,
      "protocol": "openai_chat_completions",
      "endpoint": "https://api.deepseek.com/chat/completions",
      "model": "deepseek-v4-flash",
      "key_env": "DEEPSEEK_API_KEY",
      "thinking": false,
      "timeout_seconds": 60,
      "max_input_tokens": 2000,
      "max_output_tokens": 256,
      "peak_input_usd_per_million": 0.44,
      "peak_output_usd_per_million": 1.32
    },
    "openai": {
      "enabled": false,
      "manual_only": true,
      "protocol": "openai_responses",
      "endpoint": "https://api.openai.com/v1/responses",
      "model": "gpt-5.6-luna",
      "key_env": "OPENAI_API_KEY",
      "timeout_seconds": 60,
      "max_input_tokens": 2000,
      "max_output_tokens": 256,
      "input_usd_per_million": 0.20,
      "output_usd_per_million": 1.20
    }
  }
}
```

DeepSeek support is enabled but cannot make a request without the manual CLI gates and an environment key. OpenAI support is present but disabled because the operator currently has ChatGPT Plus rather than an OpenAI Platform API key. There is no monetary or call-count budget ceiling in this version; the per-request input/output token limits remain as a data-volume and latency safeguard, and every call is still manually confirmed.

## Data minimization

Reuse and tighten `sanitize_finding` from `src_auto.ai`. The canonical remote payload contains only:

- title, capped at 300 characters;
- URL scheme, host, port, and path, with credentials, fragment, and query removed;
- parameter name, capped at 200 characters;
- severity, capped at 40 characters;
- minimal evidence, capped at 1,200 characters;
- a statement that the Finding is unconfirmed and must not be treated as a successful exploit.

The preview prints the exact canonical payload plus its SHA-256 digest. The send command rebuilds the payload from SQLite and refuses the request if the supplied digest differs.

## CLI workflow

Add three commands to `src_auto.cli`.

### `remote-status`

Reports provider, model, enabled state, manual-only state, and whether the named environment variable is present. It performs no network request and never prints key metadata.

### `remote-preview`

Example:

```powershell
python -m src_auto remote-preview --run-id RUN_ID --finding-id 1 --provider deepseek
```

It validates the run, Finding association, provider allowlist, provider state, and Scope, then prints the sanitized payload and digest with `network_contact: false`.

### `remote-triage`

Example:

```powershell
python -m src_auto remote-triage --run-id RUN_ID --finding-id 1 --provider deepseek --confirm-external --confirm-digest SHA256
```

It repeats every preview check, verifies the digest, checks STOP, reads the provider key from its environment variable, performs one non-streaming request, records the normalized review, and exits. It does not retry automatically.

## Persistence and accounting

Add an `ai_reviews` SQLite table:

```text
id, run_id, finding_fingerprint, provider, model, payload_digest,
disposition, confidence, reason, suggested_checks_json,
input_tokens, output_tokens, estimated_cost_usd, created_at
```

Add store methods to insert and list reviews and to summarize remote call count and estimated USD cost. Remote reviews remain separate from the canonical local triage JSON, so a remote opinion cannot overwrite local evidence or status.

## Error handling

Return explicit fail-closed reasons for:

- provider disabled;
- key environment variable missing;
- Finding or run missing;
- Finding not associated with the run;
- Scope mismatch or out-of-scope URL;
- missing `--confirm-external`;
- payload digest mismatch;
- STOP requested;
- per-request token limit exceeded;
- timeout, DNS/TLS error, HTTP 401/402/403/429/5xx;
- empty, malformed, or schema-invalid model output.

No automatic retry is used because a retry would create a second paid external transmission without another operator decision.

## Testing

Use Python 3.8 `unittest` and injected fake HTTP responses. Tests must cover:

- deterministic sanitized payload and digest;
- query, credentials, token, cookie, and authorization redaction;
- DeepSeek request endpoint, bearer header presence without exposing its value, model, non-thinking mode, JSON output, and token limit;
- OpenAI Responses request endpoint, `store: false`, no tools, strict JSON schema, and token limit;
- provider-disabled and missing-key behavior without network contact;
- preview never contacts the network;
- missing confirmation and digest mismatch never contact the network;
- Scope, STOP, and per-request token limit blocks;
- successful normalized review persistence;
- malformed output and HTTP failure are not persisted as successful reviews;
- secrets are absent from CLI output, SQLite rows, reports, and tracked configuration;
- the existing local launcher and 32-test baseline remain green.

The DeepSeek live probe is performed only after the operator rotates the exposed key and sets `DEEPSEEK_API_KEY`. OpenAI remains `implemented_not_live_verified` until an independent OpenAI Platform key exists.

## Acceptance criteria

- `remote-status` is network-free and reports DeepSeek key presence without disclosing it.
- `remote-preview` produces a redacted payload and stable digest without network contact.
- `remote-triage` cannot send unless every manual and safety gate passes.
- One successful fake DeepSeek response and one successful fake OpenAI response normalize to the same review schema.
- Local Ollama behavior is unchanged and never calls a remote provider automatically.
- Full tests and compile verification pass, the Git worktree is clean, and project-created files remain under `D:\网络安全文件夹\SRC-Auto` except the already-authorized desktop shortcut.

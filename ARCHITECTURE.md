# Architecture

```text
scope_candidate / scope_confirmed
              |
        ScopePolicy + ScopeGuard (fail closed)
              |
      CLI -> SQLite Store -> checkpointed Pipeline
              |                 |
      Budget/Disk/Resource/STOP  external adapters (optional)
              |
      normalize -> fingerprint/diff -> local AI triage
              |
      minimal evidence -> manual Butian report draft

Existing Finding -> redacted preview + SHA-256 digest -> human confirmation
              -> one DeepSeek V4 Flash review (or disabled OpenAI adapter)
              -> ai_reviews audit (never overwrites local triage)
```

## Modules

- `src_auto.scope`: URL parsing, host/port matching, redirect checks, scope digest.
- `src_auto.store`: SQLite runs, assets, snapshots/diff, findings/dedup, evidence, checkpoints, reports, local accounting and separate `ai_reviews` records.
- `src_auto.controls`: budget, project-directory disk, resource and manual STOP gates.
- `src_auto.adapters`: version/status checks and a safe subprocess boundary for BBOT, Subfinder, httpx, Katana, Nuclei, reconFTW and ZAP.
- `src_auto.live_plan`: validates a human-authored external plan, rejects shell/prohibited markers, and records a stable digest before any live adapter can start.
- `src_auto.pipeline`: deterministic local-lab E2E and an external fail-closed gate; it does not invent scanner behavior.
- `src_auto.ai`: switchable bulk/primary/expert lanes with a no-API deterministic fallback; this remains the only automatic AI path.
- `src_auto.remote_ai`: manually selected, HTTPS-only DeepSeek/OpenAI transports with data minimization, strict JSON normalization, per-request token limits and no automatic retry.
- `src_auto.reporting`: minimal evidence packaging and a Chinese manual-review draft report.

The control layer does not reimplement scanners. If an official tool is absent, the status is `unavailable`; the system never presents a fixture as a live scan.

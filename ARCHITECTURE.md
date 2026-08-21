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
```

## Modules

- `src_auto.scope`: URL parsing, host/port matching, redirect checks, scope digest.
- `src_auto.store`: SQLite runs, assets, snapshots/diff, findings/dedup, evidence, checkpoints, reports and accounting records.
- `src_auto.controls`: budget, project-directory disk, resource and manual STOP gates.
- `src_auto.adapters`: version/status checks and a safe subprocess boundary for BBOT, Subfinder, httpx, Katana, Nuclei, reconFTW and ZAP.
- `src_auto.pipeline`: deterministic local-lab E2E and an external fail-closed gate; it does not invent scanner behavior.
- `src_auto.ai`: switchable bulk/primary/expert lanes with a no-API deterministic fallback.
- `src_auto.reporting`: minimal evidence packaging and a Chinese manual-review draft report.

The control layer does not reimplement scanners. If an official tool is absent, the status is `unavailable`; the system never presents a fixture as a live scan.

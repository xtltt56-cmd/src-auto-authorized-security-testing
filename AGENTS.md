# SRC-Auto Agent Contract

## Scope and safety

- This project is an authorized, fail-closed SRC assistance workflow. It must not scan a real target until a human has reviewed and manually confirmed `scope_confirmed.yaml`.
- A candidate scope file never grants permission. Missing confirmation, a third-party host, an excluded host, a disallowed port, an out-of-scope redirect, or an unsupported scheme blocks the request.
- Never perform brute force, credential stuffing, destructive writes/deletes, denial of service, persistence, lateral movement, or bulk collection of user data.
- The system produces a draft report only. Submission to 补天 is always manual.

## Workspace boundary

All project-created files belong under `D:\网络安全文件夹\SRC-Auto`. The sibling paths `D:\网络安全文件夹\qa_zut_report` and `D:\网络安全文件夹\build_zut_report.py` are user-owned and must remain unchanged.

## Operating rules

- START is manual and foreground. Do not create services, scheduled tasks, startup entries, proxy pools, paid APIs, or background daemons.
- Keep the default `balanced` resource profile. Check disk, CPU, memory, budget, and STOP before each stage.
- Keep evidence minimal and redact credentials, tokens, cookies, and bulk response bodies.
- Prefer local fixtures and loopback testing. Any external adapter must pass every URL through `ScopeGuard` before invoking a tool.

## Development

- Use Python 3.8-compatible stdlib code; optional dependencies must have an explicit fallback.
- Write a failing test before production behavior and run the full unittest suite after changes.
- Do not claim a tool or phase passed unless a fresh command output proves it.

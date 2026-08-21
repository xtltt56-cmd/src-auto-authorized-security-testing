# Test Report

Date: 2026-08-21 (Asia/Shanghai)

## Automated tests

`python -m unittest discover -s tests -v` — **23 tests passed, 0 failed**.

Coverage includes:

- exact/subdomain allow, excluded/third-party/default-deny, invalid URL/port and redirect checks;
- candidate scope cannot grant permission;
- SQLite run/checkpoint/asset baseline and incremental diff;
- deterministic finding fingerprint and deduplication;
- budget daily/monthly gates, disk 80/90 GiB simulation, resource pause, and manual STOP/RESUME;
- out-of-scope adapter rejection before process start and explicit missing-tool status;
- external sequence requires an explicit `execute=True` and injected adapters;
- loopback HTTP server, pipeline ordering, minimal evidence and manual Butian report generation.

`python -m compileall -q src_auto lab tests` — **passed**.

## Manual/local verification

- CLI `new -> run --local-lab -> findings -> reports` — **passed**; one deduplicated low-severity fixture candidate produced.
- CLI `stop -> run` — **stopped**; CLI `resume --local-lab` — **completed**.
- `httpx.exe -silent -u http://127.0.0.1:8765/` — **passed**, loopback only.
- `katana.exe -silent -u http://127.0.0.1:8765/ -d 1` — **passed**, loopback only.
- No real Butian or third-party target was contacted.

## Tool verification

- Subfinder v2.15.0 — version verified.
- httpx v1.10.0 — version and loopback invocation verified.
- Katana v1.7.0 — version and loopback invocation verified.
- Nuclei v3.11.1 — SHA-256 verified, execution blocked by endpoint security (not marked passed).
- OWASP ZAP 2.17.0 — version verified from the D-drive core distribution; no real target scan run.
- BBOT 3.0.1 — not runnable on this Python 3.8/Windows-only environment; current release requires Python >=3.10 and POSIX-oriented dependencies.
- reconFTW — not runnable without Linux shell/WSL.

## Acceptance status

The control plane and local E2E acceptance criteria pass. Full external-tool acceptance is intentionally **partial** until WSL2/admin setup and endpoint-security review are completed; this is recorded in `KNOWN_ISSUES.md`.

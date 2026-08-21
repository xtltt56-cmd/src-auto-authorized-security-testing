# Operations

## First local run

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m unittest discover -s tests -v
$json = python -m src_auto new --target-id local-lab --scope config/targets/local-lab/scope_confirmed.yaml --mode local
$run = ($json | ConvertFrom-Json).run_id
python -m src_auto run --run-id $run --scope config/targets/local-lab/scope_confirmed.yaml --local-lab
python -m src_auto findings --run-id $run
python -m src_auto reports
```

`START.bat RUN_ID` is the same foreground local-lab run. It does not create a scheduled task, service, startup entry or background worker.

The desktop one-click launcher is `START_SYSTEM.ps1`. It manually starts the local Ollama service when needed, runs the local-lab workflow, and prints Findings/reports. It never starts a real target workflow.

## STOP and RESUME

```powershell
STOP.bat RUN_ID
STATUS.bat --run-id RUN_ID
START.bat RUN_ID       # observes STOP and remains stopped
python -m src_auto resume --run-id RUN_ID --scope config/targets/local-lab/scope_confirmed.yaml --local-lab
```

Only `resume` clears the marker. If the process is interrupted, the SQLite checkpoints and run status remain available for inspection.

## Tool status

```powershell
python -m src_auto tool-status
```

The command verifies versions only. ProjectDiscovery binaries are in `vendor\bin`; ZAP is in `vendor\zap`. A status of `unavailable` or `error` is a real limitation, not a fixture result.

## First real SRC target

1. Save the platform's current rules, time window, explicit roots/hosts/ports, exclusions, and authorization source as a new candidate snapshot.
2. Run `python -m src_auto resolve-scope --snapshot <rules.json-or-yaml> --output-dir config\targets\<id>`.
3. A human reviews the candidate and creates a separate `scope_confirmed.yaml` with `confirmed: true` and `allow_network_contact: true`. Do not reuse the loopback file.
4. Create a run with `src_auto new --mode real` and inspect the scope hash.
5. Copy `config\live_plan.example.yaml`, replace every placeholder, keep `manual_execution_confirmed: false` until the final review, and set an explicit bounded sequence and arguments.
6. The default `config\policy.yaml` has `network.allow_real_targets: false`; only change it after the authorization review. Run `python -m src_auto run-live ... --plan ...` for a dry gate, then add `--execute-live` only for the reviewed window.
7. Review the generated draft report and submit manually through 补天 only if the platform rules permit it. The desktop launcher never enters this path.

## Data locations

- SQLite: `data\src_auto.sqlite3` (ignored by Git)
- Logs/checkpoints: SQLite events and `logs\`
- Minimal evidence: `evidence\<run_id>\`
- Draft reports: `reports\<run_id>.md`

Never commit evidence, credentials, tokens, cookies, or database files.

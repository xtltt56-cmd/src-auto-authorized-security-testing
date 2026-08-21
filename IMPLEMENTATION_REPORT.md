# Implementation Report

## Overall result

The D-drive V1 control layer is implemented and locally verified. It is safe to start in the local loopback lab. It is not an authorization to scan arbitrary live websites, and it does not auto-submit to 补天.

## Final directory

`D:\网络安全文件夹\SRC-Auto`

Existing sibling artifacts were left outside the project and were not edited:

- `D:\网络安全文件夹\qa_zut_report`
- `D:\网络安全文件夹\build_zut_report.py`

The current SHA-256 snapshot is recorded in `preservation_manifest.sha256`; the manifest is an audit aid and is not permission to modify either sibling path.

## Environment snapshot

- Windows PowerShell host; Python 3.8.10; Git 2.55.0; Java 17.0.10 LTS.
- WSL reports that it is not installed; Go, Node and Docker are not on PATH.
- D: volume: approximately 167.2 GiB free at the snapshot; project directory approximately 0.47 GiB.
- Snapshot CPU approximately 9.5%; visible memory approximately 31.7 GiB total / 20.3 GiB free.

## Scope architecture and data flow

`ScopeResolver` accepts explicit platform-rule data and emits a candidate with both permission flags false. `ScopePolicy` normalizes hosts/ports and computes a digest. `ScopeGuard` is called before every external adapter request and denies missing confirmation, third parties, exclusions, bad schemes, bad ports and outside redirects.

The pipeline is:

```text
BBOT -> Subfinder -> httpx -> Katana -> Nuclei -> ZAP passive -> reconFTW Deep Recon
  -> normalize -> SHA-256 fingerprint/diff -> AI triage -> minimal evidence -> manual report
```

The external sequence is library-gated and requires confirmed scope, a validated human-authored plan, the policy switch `allow_real_targets: true`, and an explicit `--execute-live`. The default policy and desktop launcher only run or allow the loopback fixture.

## Database

SQLite stores runs/status, assets, snapshots, incremental diff, global findings/fingerprints, per-run Finding associations, evidence hashes, checkpoints, events, spend, manual submissions and report paths. The database is ignored by Git.

## Model router and AI cost

`ModelRouter` has bulk/primary/expert lanes from `config/models.yaml`. Primary now connects to local Ollama using `qwen-agent-stable:30b`, expert is configured for `qwen3-coder:30b`, and failed/invalid/slow calls fall back to the deterministic local heuristic. `AITriage` returns candidate/manual-review dispositions and hands off to manual review when the budget gate is exhausted. Remote API use is disabled and no API key is present. Finding data is redacted before a local model call.

## Disk and resource controls

Balanced mode checks project-directory usage before every local stage, warns at 80 GiB and hard-stops at 90 GiB. Resource metrics are optional; known over-limit CPU/RAM pauses the run, while unavailable metrics are reported as unknown. Manual `STOP` is a marker under the project root.

## Installed tools and methods

Official Windows amd64 release archives for Subfinder v2.15.0, httpx v1.10.0, Katana v1.7.0 and Nuclei v3.11.1 were downloaded to `vendor\downloads`, SHA-256 checked, and expanded under `vendor\bin`. ZAP 2.17.0 Core was downloaded and checked under `vendor\zap`. No paid service or proxy was used. BBOT/reconFTW remain blocked by the environment limitations described below.

## Tests and E2E

See `TEST_REPORT.md`: 32 automated tests passed, compileall passed, loopback HTTP and CLI E2E passed, Ollama Provider was tested with a local model, and STOP/RESUME passed. The out-of-scope fixture was rejected and never requested.

## Operations

- Start local: `START.bat RUN_ID` or `python -m src_auto run --run-id ... --local-lab`.
- Stop: `STOP.bat RUN_ID`.
- Resume: `python -m src_auto resume --run-id ... --local-lab`.
- View status/findings/reports: `STATUS.bat`, `python -m src_auto findings`, `python -m src_auto reports`.
- Desktop one-click start: `START_SYSTEM.ps1`; it starts local Ollama when needed and runs only the local-lab workflow.
- First real target: create a new candidate from current platform rules, manually create a matching `scope_confirmed.yaml`, then create a real run and review the scope hash. No real target was used in this build.
- Controlled external path: copy `config/live_plan.example.yaml`, keep the plan false until final review, run the dry gate, and use `--execute-live` only after policy and Scope approval. No real target was used in this build.

## Known limitations

See `KNOWN_ISSUES.md`. In particular, WSL2/admin setup is not available, endpoint security blocks Nuclei execution, ZAP is version-verified only, and no bounty or profitability is promised.

# Known Issues and Honest Limitations

1. WSL2/Ubuntu is not installed. Installing it can require administrator privileges and a restart, so it was not forced. BBOT 3.0.1 currently declares Python >=3.10 and POSIX-oriented dependencies; the host Python is 3.8.10. reconFTW requires a Linux shell. These are environment blockers, not successful-tool claims.
2. The Nuclei v3.11.1 Windows binary and release hash are present on D:, but endpoint security blocks its execution with WinError 225. It was not bypassed and no Nuclei scan was run.
3. ZAP 2.17.0 is version-verified from the D-drive core archive. A full passive baseline run is not claimed because no real target was authorized and the control layer intentionally leaves external execution behind an explicit adapter gate.
4. Version checks for third-party tools may create their own per-user configuration under `C:\Users\lenovo\AppData` on Windows. The project never stores credentials there, but the tools do not all honor the D-drive-only project boundary. If strict host-wide cleanup is required, remove only the tool-created config directories after reviewing them.
5. YAML loading uses PyYAML when available and otherwise accepts the project's JSON-compatible `.yaml` files. Arbitrary YAML with anchors/comments needs PyYAML installed in a D-drive environment before use.
6. V1 has no remote LLM API integration, login/CAPTCHA automation, or automatic Butian submission. AI triage is local and conservative; final validation and submission remain human work.
7. No income, bounty amount, acceptance, or monthly profit is guaranteed. The accounting tables and report fields are prepared for later measurement.

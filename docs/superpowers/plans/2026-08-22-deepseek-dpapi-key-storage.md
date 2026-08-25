# DeepSeek DPAPI Key Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save the DeepSeek API key once as a current-user DPAPI blob under the D-drive project, then load it only after the operator selects “enable” at startup.

**Architecture:** A focused PowerShell helper owns DPAPI protect/unprotect operations and fixed project-bound path validation. A one-time save UI consumes a hidden `SecureString`; the launcher calls the unprotect function only inside the affirmative consent branch and never initiates an API request automatically.

**Tech Stack:** Windows PowerShell 5.1, Windows DPAPI via `ConvertFrom-SecureString` / `ConvertTo-SecureString`, Python `unittest`, existing SRC-Auto launcher and consent gates.

---

### Task 1: DPAPI helper and round-trip regression

**Files:**
- Create: `tools/deepseek_secret.ps1`
- Create: `tests/test_deepseek_secret.py`

- [ ] **Step 1: Write failing tests**

Add tests that require UTF-8 BOM, invoke Windows PowerShell 5.1 with a dummy `SecureString`, write only below `validation/test-secrets`, assert that the encrypted file does not contain the dummy plaintext, decrypt to the same dummy value, and reject an output path outside `D:\网络安全文件夹\SRC-Auto`.

```python
def test_dpapi_round_trip_stays_encrypted_and_project_bound(self):
    # Invoke tools/deepseek_secret.ps1 with a non-secret fixture value.
    # Assert exit 0, encrypted file lacks plaintext, and round-trip matches.

def test_dpapi_rejects_path_outside_project(self):
    # Invoke Protect-DeepSeekKey with C:\Windows\Temp\outside.dpapi.
    # Assert non-zero and deepseek_secret_path_outside_project.
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_deepseek_secret -v
```

Expected: FAIL because `tools/deepseek_secret.ps1` does not exist.

- [ ] **Step 3: Implement the minimal helper**

Implement these functions in `tools/deepseek_secret.ps1`:

```powershell
function Assert-DeepSeekSecretPath([string]$Path, [string]$ProjectRoot) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    if(-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)){
        throw 'deepseek_secret_path_outside_project'
    }
    return $full
}

function Protect-DeepSeekKey([Security.SecureString]$SecureKey, [string]$Path, [string]$ProjectRoot) {
    $full = Assert-DeepSeekSecretPath $Path $ProjectRoot
    $encrypted = $SecureKey | ConvertFrom-SecureString
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($full)) | Out-Null
    [IO.File]::WriteAllText($full, $encrypted, (New-Object Text.UTF8Encoding($false)))
}

function Unprotect-DeepSeekKey([string]$Path, [string]$ProjectRoot) {
    $full = Assert-DeepSeekSecretPath $Path $ProjectRoot
    $secure = (Get-Content -LiteralPath $full -Raw).Trim() | ConvertTo-SecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if($pointer -ne [IntPtr]::Zero){ [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        $secure.Dispose()
    }
}
```

- [ ] **Step 4: Convert the helper to UTF-8 BOM and verify GREEN**

Run the focused test again. Expected: all `tests.test_deepseek_secret` tests PASS.

### Task 2: One-time hidden save interface

**Files:**
- Create: `tools/save_deepseek_key.ps1`
- Modify: `.gitignore`
- Modify: `tests/test_deepseek_secret.py`

- [ ] **Step 1: Add failing interface tests**

Require the save script to use `Read-Host -AsSecureString`, dot-source the helper, target `config\secrets\deepseek_api_key.dpapi`, avoid `setx`, avoid printing secret material, and have UTF-8 BOM. Require `.gitignore` to include `config/secrets/`.

- [ ] **Step 2: Run the focused tests and verify RED**

Expected: FAIL because the save interface and ignore rule do not exist.

- [ ] **Step 3: Implement the save interface**

The script must obtain one hidden `SecureString`, reject an empty value, call `Protect-DeepSeekKey`, dispose the secure value, and print only the fixed encrypted-file path and a Chinese success/failure message. It must not place plaintext into an environment variable or result file.

- [ ] **Step 4: Add `config/secrets/` to `.gitignore` and verify GREEN**

Run `python -m unittest tests.test_deepseek_secret -v`. Expected: PASS.

### Task 3: Load the encrypted key only after affirmative startup consent

**Files:**
- Modify: `START_SYSTEM.ps1`
- Modify: `tests/test_launcher.py`

- [ ] **Step 1: Add failing launcher tests**

Require the launcher to reference the fixed DPAPI path and `Unprotect-DeepSeekKey`, with the consent prompt text appearing before the unprotect call. Require an explicit Chinese decryption-failure message and preservation of `remote_ai_disabled_for_session`.

- [ ] **Step 2: Run the launcher tests and verify RED**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected: FAIL because the launcher does not load DPAPI storage.

- [ ] **Step 3: Implement affirmative-only loading**

Inside the existing affirmative branch, when `DEEPSEEK_API_KEY` is empty and the DPAPI file exists, dot-source the helper and call `Unprotect-DeepSeekKey`. On success, place the returned plaintext only in the current process environment and set the local variable to `$null`. On absence or failure, retain the existing hidden-input fallback. The negative branch must remain before any call to `Unprotect-DeepSeekKey` at runtime.

- [ ] **Step 4: Verify launcher tests and Windows PowerShell parsing**

Expected: launcher tests PASS and both `START_SYSTEM.ps1` and the save/helper scripts report zero parser errors under Windows PowerShell 5.1.

### Task 4: Full verification and one-time save prompt

**Files:**
- Update: `USER_MANUAL.md`
- Update: `OPERATIONS.md`
- Generated and ignored: `config/secrets/deepseek_api_key.dpapi`

- [ ] **Step 1: Document the one-time save and startup behavior**

Document that DPAPI binds the blob to the current Windows user and machine, that choosing “否” skips decryption, and that rerunning the save tool rotates the stored key.

- [ ] **Step 2: Run complete verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src_auto tools tests
git check-ignore config/secrets/deepseek_api_key.dpapi
```

Expected: zero test failures, compile exit 0, and the secret path is ignored.

- [ ] **Step 3: Scan for mojibake and plaintext-secret risks**

Scan project text for common corruption markers and confirm zero hits. Confirm the DPAPI file is not staged and that no report contains its encrypted content or the key.

- [ ] **Step 4: Open the visible save interface**

Launch Windows PowerShell 5.1 with `-NoProfile -ExecutionPolicy Bypass -NoExit -File tools\save_deepseek_key.ps1`. The user pastes the key once into the hidden prompt.

- [ ] **Step 5: Verify the stored blob without revealing it**

Report only: file exists, file is ignored by Git, plaintext prefix is absent, same-user DPAPI decryption succeeds, and no API request was made during saving.

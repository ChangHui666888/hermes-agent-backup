# Environment Variable Tracing on Windows

## Problem

A tool is hard-wired to use a proxy (`HTTP_PROXY`/`HTTPS_PROXY`) but you didn't set it in your shell init files. Where is it coming from?

## Trace Path

### Step 1: Check current environment

```bash
env | grep -i proxy
# Or
export | grep -i proxy
```

Common observations:
- **Uppercase only set:** `HTTP_PROXY=http://127.0.0.1:10808` but lowercase `http_proxy` is empty → not from bash init files
- **Both uppercase and lowercase set with the same value** → likely from Windows system/user env vars
- **Neither set** → proxy is configured inside the application itself (check its config)

### Step 2: Check bash init files (git-bash / MSYS)

```bash
for f in ~/.bashrc ~/.bash_profile ~/.profile ~/.bash_login; do
  echo "--- $f ---"
  [ -f "$f" ] && grep -in "proxy" "$f" || echo "(not found)"
done
```

On Windows git-bash, `$HOME` may point to a Hermes-managed home dir (e.g. `$HERMES_HOME/home/`). Check both `~/.bashrc` and the user's Windows home at `/c/Users/<username>/.bashrc`.

### Step 3: Check Windows registry — User environment variables

```bash
reg query "HKCU\Environment" 2>/dev/null | grep -i proxy
```

PRIMARY source for user-scoped env vars on Windows. These are the "User variables" in the System Properties → Environment Variables GUI.

### Step 4: Check Windows registry — System environment variables

```bash
reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" 2>/dev/null | grep -i proxy
```

These are the "System variables". Less common for proxy settings, but worth checking.

### Step 5: Verify from cmd.exe / PowerShell (not always needed)

```powershell
# PowerShell
Get-ChildItem Env:* | Where-Object { $_.Name -match 'proxy' }

# cmd.exe
set | findstr /i proxy
```

If proxy shows in PowerShell/cmd.exe too, it's definitely a Windows system/user env var.

## Fix: Remove from Registry

### Using PowerShell (preferred — handles spaces/paths better)

```powershell
Remove-ItemProperty -Path 'HKCU:\Environment' -Name 'HTTP_PROXY'
Remove-ItemProperty -Path 'HKCU:\Environment' -Name 'HTTPS_PROXY'
```

Change `HKCU:\Environment` to `HKLM:\SYSTEM\...` if it's a system-wide variable (requires admin).

**Note:** The change only takes effect in **new** processes. Current shell and its children still have the old env var.

### Using reg.exe (from bash/MSYS)

In MSYS bash, backslashes in registry paths are escape chars. Use PowerShell or quote carefully:

```bash
# Wrong (MSYS eats the backslash):
reg delete "HKCU\Environment" /v HTTP_PROXY /f    # FAILS

# Right — use PowerShell:
powershell.exe -Command "Remove-ItemProperty -Path 'HKCU:\Environment' -Name 'HTTP_PROXY'"
```

### Step 6: Unset in current shell immediately

```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
```

This clears the vars from the current process so fixes take effect without restarting the terminal.

## Verification

```bash
# 1. Confirm env is clean
env | grep -i proxy || echo "(none)"

# 2. Test direct connectivity to the API
curl -s --connect-timeout 10 -o /dev/null -w "%{http_code}" https://api.example.com/v1/models
# 401 = reaches API (needs auth) ✓
# connection refused / timeout = still through dead proxy ✗

# 3. Confirm registry is clean
reg query "HKCU\Environment" 2>/dev/null | grep -i proxy || echo "(no proxy vars remaining)"
```

## Common Variations

| Symptom | Likely Source | Fix |
|---------|--------------|-----|
| Only uppercase HTTP_PROXY/HTTPS_PROXY set | Windows user env var | Registry removal |
| Both upper and lower case set, matching value | Windows env var → bash inherits | Registry removal |
| Proxy set in `.bashrc` but not `.bash_profile` | Non-login shell source | Edit `.bashrc` |
| Proxy works in git-bash but not cmd.exe | Only in bash init | Edit bash init file |
| Proxy works in cmd.exe but not git-bash | Windows env var + bash overrides | Check both sources |

## Root Cause Classification

When debugging proxy issues, categorize the source tier:

- **Tier 1 — Session-local:** shell init files (`.bashrc`, `.zshrc`, etc.)
- **Tier 2 — User-global:** `HKCU\Environment` registry key
- **Tier 3 — Machine-global:** `HKLM\SYSTEM\...\Environment` registry key
- **Tier 4 — Application-level:** inside the app's own config (e.g. npm config, git config, PIP config)

Always check Tier 1 → 2 → 3 in order. Tier 4 is tool-specific.

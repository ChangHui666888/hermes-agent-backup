# Wiki Auto-Sync via Hermes Cron (Windows)

## Overview

Two parallel approaches for automatic wiki sync:

1. **Hermes Cron** — runs inside the Hermes gateway process
2. **Windows Scheduled Task** — OS-level task independent of Hermes

**Hermes Cron with `--no-agent`** is simpler because it requires no admin rights.

---

## Approach A: Hermes Cron (Recommended)

### Architecture

```
hermes cron (in gateway) 
  → profiles/<profile>/scripts/wiki-sync.sh (wrapper)
    → /c/Users/<user>/wiki/scripts/wiki-sync.sh (real script)
      → git add, git commit, git push
      → python scripts/wiki-graph.py
```

### Step 1: Create Wrapper Script

Place a wrapper script in the **profile's scripts directory** (`profiles/<profile>/scripts/wiki-sync.sh`):

```bash
#!/bin/bash
exec bash /c/Users/<user>/wiki/scripts/wiki-sync.sh
```

**Why a wrapper?** The `--script` parameter expects a single filename relative to the profile's scripts directory. Passing `--script "bash /path/to/script.sh"` treats the whole string as a filename, causing `Script not found` errors with path corruption like `...\scripts\bash \c\Users\...\`.

### Step 2: Register the Cron Job

```bash
hermes cron create "30m" \
  --name "wiki-sync" \
  --script "wiki-sync.sh" \
  --no-agent \
  --workdir /c/Users/<user>/wiki
```

| Flag | Purpose |
|------|---------|
| `"30m"` | Schedule: every 30 minutes (also accepts cron expressions) |
| `--name wiki-sync` | Human-friendly job name |
| `--script wiki-sync.sh` | Script name relative to `profiles/<profile>/scripts/` |
| `--no-agent` | Skip LLM — run script directly, deliver stdout verbatim |
| `--workdir /c/Users/.../wiki` | Working directory for git and python commands |

### Step 3: Verify

```bash
hermes cron list
```

Expected output shows job with `[active]` status, next run time, script name, and workdir.

---

## Approach B: Windows Scheduled Task

Use when the Hermes gateway is not running, or for redundancy.

```batch
schtasks /Create ^
  /SC MINUTE /MO 30 ^
  /TN "HermesWiki-Sync" ^
  /TR "C:\Program Files\Git\bin\bash.exe -c \"cd /c/Users/<user>/wiki && bash scripts/wiki-sync.sh\"" ^
  /IT /RL HIGHEST /F
```

Verify with `schtasks /Query /TN "HermesWiki-Sync" /FO LIST`.

---

## Troubleshooting

### `Script not found: ...\scripts\bash \c\...\wiki-sync.sh`

**Cause:** Previous cron registration passed `--script "bash /c/Users/.../wiki-sync.sh"`, treating the whole string as a filename. `.sh` files run via bash but the `--script` value must be a single relative filename.

**Fix:** Create a wrapper script in the profile's scripts directory, then register with just the filename.

### Cron output shows failed runs

Cron output lives at `profiles/<profile>/cron/output/<job-id>/`. Each run writes a timestamped markdown file with exit status and error messages.

```bash
ls -lt profiles/<profile>/cron/output/<job-id>/
cat profiles/<profile>/cron/output/<job-id>/latest.md
```

### `hermes cron list` shows no jobs

If `jobs.json` is an empty array `"jobs": []`, the job was removed. Re-register using the steps above. The `jobs.json` file is at `profiles/<profile>/cron/jobs.json`.

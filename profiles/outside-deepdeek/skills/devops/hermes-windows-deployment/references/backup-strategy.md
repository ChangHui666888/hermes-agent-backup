# Backup Strategy Reference

## Architecture

| Type | Scheduler | Frequency | Target | Retention |
|------|-----------|:---------:|--------|:---------:|
| Git remote | Task Scheduler | Daily 12:00 | GitHub | Permanent |
| Full local | Task Scheduler | Daily 18:00 | F:\hermes-backup | 14 days |

## Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `git-backup.sh` | `~/.hermes/scripts/` | git add/commit/push |
| `full-backup.sh` | `~/.hermes/scripts/` | rsync to F: drive |
| `restore.bat` | `~/.hermes/scripts/` | One-click restore |

## Full Backup Requirements

1. Windows absolute paths (no `$HOME`)
2. `logs/full-backup.log` for audit
3. `backup.ok` marker file for restore validation
4. 14-day retention (`-mtime +14`)
5. Explicit exit 1 on `rsync` failure

## Restore Flow

1. Shows latest valid backup (with `backup.ok`)
2. First confirmation: type `YES`
3. Second confirmation: type `YES` again
4. Only stops `hermes-gateway.exe` (not all Python)
5. Backs up current to `hermes_old_yyyyMMdd`
6. `/MIR` mirror restore (deletes extra files)
7. Prompts to restart Hermes

## Task Scheduler vs Hermes Cron

- Interval tasks (5min, 30min) → **Hermes Cron**
- Fixed-time tasks (12:00, 18:00) → **Windows Task Scheduler**
- Reason: Task Scheduler is more reliable for fixed times; Hermes Cron is simpler for intervals

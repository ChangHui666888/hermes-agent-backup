# Backup Strategy Reference

## Architecture

```
Hermes Cron                          Windows Task Scheduler
─────────────                        ──────────────────────
rss-scan (5min)                      12:00 → git-backup.sh
news-pipeline (30min)                18:00 → full-backup.sh

              ↓                              ↓
         ~/.hermes/                    GitHub + F:\hermes-backup
```

## Scripts

- `git-backup.sh` — daily git add/commit/push
- `full-backup.sh` — daily rsync to F: drive, 14d retention, `backup.ok` marker
- `restore.bat` — one-click restore with dual confirmation, /MIR mirror restore, safe process stop

## Restore

1. Double-click `restore.bat` in `~/.hermes/scripts/`
2. Enter `YES` twice to confirm
3. Automatically backs up current version, restores from latest F: backup
4. Restart Hermes manually

## Cron Commands (PowerShell)

```powershell
hermes cron add "every 5m" --name rss-scan --script rss-scanner.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
hermes cron add "every 30m" --name news-pipeline --script news-pipeline.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
```

## Task Scheduler Commands (PowerShell Admin)

```powershell
schtasks /create /tn "Hermes-Git-Backup" /tr '"C:\Users\ChangHui\AppData\Local\hermes\scripts\git-backup.sh"' /sc daily /st 12:00 /f
schtasks /create /tn "Hermes-Full-Backup" /tr '"C:\Users\ChangHui\AppData\Local\hermes\scripts\full-backup.sh"' /sc daily /st 18:00 /f
```

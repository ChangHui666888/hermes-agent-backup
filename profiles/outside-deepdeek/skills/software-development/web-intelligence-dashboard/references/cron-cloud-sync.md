# Cron Pipeline Sync Pattern

## Problem

Pipeline produces event_registry SQLite on Windows. Cloud Docker mounts a snapshot. When pipeline updates the DB, the cloud serves stale data.

## Solution

Hermes cron job every 30 minutes:

```python
# cron-sync.py — runs as Hermes cron (no_agent=true)
import paramiko, subprocess, sys, os

def main():
    # 1. Aggregate events (re-run to capture new articles)
    from news_intel.aggregator import aggregate_events
    events = aggregate_events(articles, window_hours=24)

    # 2. SCP upload SQLite to cloud
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS)
    sftp = client.open_sftp()
    sftp.put("news_intel/news_intel.db", f"{REMOTE_DIR}/news_intel.db")
    sftp.close()

    # 3. Restart cloud backend to remount DB
    client.exec_command("cd project && docker compose restart backend")
    client.close()
```

## Cron Registration

```python
cronjob(action="create", name="db-cloud-sync", schedule="30m",
        script="cron-sync.py", no_agent=True)
```

## Verification

```bash
# Local
python -c "import sqlite3; print(sqlite3.connect('news_intel.db').execute('SELECT COUNT(*) FROM event_registry').fetchone()[0])"

# Cloud
curl http://cloud-ip/api/v1/dashboard | python3 -c "import sys,json; print(json.load(sys.stdin)['metrics']['active_events'])"

# Must match
```

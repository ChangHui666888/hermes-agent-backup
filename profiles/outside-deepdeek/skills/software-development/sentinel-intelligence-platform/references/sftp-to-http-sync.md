# SFTP → HTTP Sync Replacement

Replace paramiko/SCP/SSH data sync with HTTP POST for pipeline-to-cloud data flow.

## Before (Fragile)

```python
# cron-sync.py — OLD version (DO NOT USE)
import paramiko
# SCP upload SQLite file
sftp.put(local_db, remote_path)
# SSH restart container
client.exec_command("docker compose restart backend")
```

## After (Robust)

```python
# cron-sync.py — NEW version
import httpx

# 1. Aggregate events locally
events = aggregate_events(articles)

# 2. HTTP POST to cloud (no SSH, no SCP)
resp = httpx.post(
    f"{API_BASE}/internal/events/batch",
    json=events,
    headers={"X-Internal-Token": INTERNAL_TOKEN},
    timeout=30,
)
```

## Why

- No SSH key/password management
- No hardcoded credentials in scripts
- Atomic: transaction commits or fails, no partial state
- No restart needed — data is live on next API call
- HTTP is firewall-friendly, works through proxies

# SFTP → HTTP Data Sync Migration

## Why Replace SFTP Sync

Local pipeline (Windows) produces event_registry SQLite. Old pattern synced to cloud via SFTP + SSH restart. This is fragile:

- File-level copy can corrupt database (WAL state mismatch)
- Requires Docker container restart (downtime)
- Hardcoded SSH credentials in scripts
- paramiko dependency in cron jobs

## New Pattern: HTTP POST

```python
# cron-sync.py — no paramiko, no SFTP, no SSH restart
import httpx, os

API = os.environ.get("NEWS_API_BASE")
TOKEN = os.environ.get("NEWS_API_TOKEN")

# 1. Aggregate events locally
events = aggregate_events(articles)

# 2. Push via HTTP
body = [_event_to_api_format(e) for e in events]
resp = httpx.post(
    f"{API}/internal/events/batch",
    json=body,
    headers={"X-Internal-Token": TOKEN},
    timeout=60,
)

# 3. Immediate visibility — no restart needed
print(f"Synced {len(events)} events: {resp.status_code}")
```

## Backend Endpoint

```python
@router.post("/internal/events/batch")
def ingest_events(events: List[dict], token=Depends(verify_internal), db=Depends(get_db)):
    for ev in events:
        db.execute(text("""
            INSERT INTO events (...) VALUES (...)
            ON CONFLICT (event_id) DO UPDATE SET ...
        """), {...})
    db.commit()
    return {"ok": ok, "fail": fail}
```

## Benefits Over SFTP

| SFTP | HTTP POST |
|------|-----------|
| File copy + WAL corruption risk | Atomic PG transaction |
| Container restart needed | Immediate visibility |
| paramiko dependency | httpx (already used) |
| Hardcoded SSH password | Bearer token in env |
| ~30 lines of SFTP code | ~5 lines of HTTP |

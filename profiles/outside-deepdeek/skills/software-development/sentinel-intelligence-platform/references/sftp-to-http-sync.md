# Data Sync: SFTP → HTTP Migration

## Old Pattern (SFTP — DEPRECATED)

```python
# sync-db-to-cloud.py
sftp.put("news_intel.db", "/data/news_intel.db")
ssh.exec_command("docker compose restart backend")
```

**Problems**:
- Requires paramiko (heavy dependency)
- Password in code
- No atomicity — file could be partially uploaded
- Restart required — downtime
- SQLite file corruption on read-only mounts

## New Pattern (HTTP POST)

```python
# cron-sync.py
events = aggregate_events(articles)
httpx.post("http://cloud:80/internal/events/batch", 
           json=events, 
           headers={"X-Internal-Token": TOKEN})
```

**Advantages**:
- No paramiko dependency
- No password in code (token in env)
- Atomic transaction (PG ON CONFLICT DO UPDATE)
- No restart — data visible immediately
- Single data source (PG, no SQLite on cloud)

## Backend Endpoint

```python
@router.post("/events/batch")
def ingest_events(events: List[dict], _=Depends(verify_internal), db=Depends(get_db)):
    SQL = text("""INSERT INTO events (...) VALUES (...) ON CONFLICT (event_id) DO UPDATE SET ...""")
    for ev in events:
        db.execute(SQL, {...})
    db.commit()
    return {"ok": ok, "fail": fail}
```

Must use `text()` wrapper for SQLAlchemy 2.0 raw SQL.

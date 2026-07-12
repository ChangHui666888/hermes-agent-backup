# DB to Cloud Sync Pattern

When a pipeline writes to a local SQLite and the web frontend reads from a cloud copy, use this cron pattern to keep them in sync.

## Script: cron-sync.py

```python
#!/usr/bin/env python3
"""Aggregate events + sync SQLite to cloud + restart backend."""

import sys, os, time, subprocess

PROFILE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(PROFILE, "skills", "research", "search-engine-v2", "scripts")
sys.path.insert(0, PIPELINE)

# 1. Aggregate events (writes to event_registry)
from news_intel.db import init_db, get_db
from news_intel.aggregator import aggregate_events
init_db()
db = get_db()
db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
rows = db.execute("""
    SELECT nc.id, rr.title, nc.summary_cn, rr.description,
           ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name
    FROM news_content nc
    JOIN news_intelligence ni ON nc.intel_id = ni.id
    JOIN rss_raw rr ON ni.raw_id = rr.id
    WHERE ni.tier IN ('A','B') ORDER BY nc.id DESC LIMIT 100
""").fetchall()
events = aggregate_events(rows, window_hours=24)
db.close()

# 2. Upload SQLite to cloud
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username="administrator", password="...", timeout=15)

DB_PATH = os.path.join(PIPELINE, "news_intel", "news_intel.db")
sftp = client.open_sftp()
sftp.put(DB_PATH, "/home/administrator/news-intel-web/data/news_intel.db")
sftp.close()

# 3. Restart cloud backend container
client.exec_command(
    "cd /home/administrator/news-intel-web && docker compose restart backend"
)
client.close()
```

## Hermes Cron Registration

```bash
hermes cron add "every 30m" --name db-cloud-sync --script cron-sync.py --no-agent
```

## Key Points

- Script location: `profiles/<name>/scripts/cron-sync.py` (not skills/)
- `--no-agent` is mandatory — no LLM needed for file sync
- `sqlite3.connect` for aggregation, `paramiko.SFTP.put` for upload
- Docker `restart` (not rebuild) after file replacement
- Uses `sys.path.insert(0, PIPELINE)` to import pipeline modules from skill directory

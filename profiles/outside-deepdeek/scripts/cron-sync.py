#!/usr/bin/env python3
"""cron-sync.py — Pipeline aggregation + cloud DB sync

Finds the pipeline scripts relative to the profile root.
Runs: aggregate -> sync-db-to-cloud -> restart cloud backend.

Called by Hermes cron every 30 minutes.
"""

import sys, os, time, subprocess

# Paths — profile root is parent of scripts/
PROFILE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(
    PROFILE, "skills", "research", "search-engine-v2", "scripts"
)
SYNC_SCRIPT = os.path.join(PROFILE, "scripts", "sync-db-to-cloud.py")

sys.path.insert(0, PIPELINE)

print(f"[cron] Pipeline: {PIPELINE}")
print(f"[cron] Sync script: {SYNC_SCRIPT}")

# 1. Aggregate events
try:
    from news_intel.db import init_db
    from news_intel.aggregator import aggregate_events
    init_db()
    from news_intel.db import get_db
    db = get_db()
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = db.execute("""
        SELECT nc.id, rr.title, nc.summary_cn, rr.description,
               ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE ni.tier IN ('A','B')
        ORDER BY nc.id DESC LIMIT 100
    """).fetchall()
    events = aggregate_events(rows, window_hours=24)
    print(f"[cron] Aggregated {len(events)} events")
    db.close()
except Exception as e:
    print(f"[cron] Aggregation: {e}")

# 2. Sync to cloud
try:
    result = subprocess.run(
        [sys.executable, SYNC_SCRIPT],
        capture_output=True, text=True, timeout=60,
    )
    print(result.stdout.strip())
    if result.stderr:
        print(f"[cron] Sync stderr: {result.stderr[:200]}")
except Exception as e:
    print(f"[cron] Sync failed: {e}")

# 3. Restart cloud backend
try:
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("100.107.117.23", username="administrator",
                   password="root123root!@", timeout=15)
    stdin, stdout, stderr = client.exec_command(
        "cd /home/administrator/news-intel-web && docker compose restart backend 2>&1"
    )
    print(f"[cron] Cloud restart: {stdout.read().decode().strip()}")
    client.close()
except Exception as e:
    print(f"[cron] Cloud restart failed: {e}")

print(f"[cron] Done at {time.strftime('%H:%M:%S')}")

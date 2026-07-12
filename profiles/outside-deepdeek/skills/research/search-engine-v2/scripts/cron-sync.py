#!/usr/bin/env python3
"""cron-sync.sh — Pipeline + Cloud Sync

Runs after RSS ingestion. Full cycle:
  1. Aggregate events from latest articles
  2. Sync SQLite to cloud
  3. Restart cloud backend

This is the cron entry point. No Agent session needed.
"""

import sys
import os
import time
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

def main():
    print(f"[cron] === Pipeline + Sync {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

    # 1. Aggregate events (auto-persists to event_registry)
    print("[cron] Step 1: Aggregate events...")
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
        print(f"[cron]   {len(events)} events aggregated")
        db.close()
    except Exception as e:
        print(f"[cron]   Aggregation skipped: {e}")

    # 2. Sync DB to cloud
    print("[cron] Step 2: Sync DB to cloud...")
    sync_script = os.path.join(SCRIPT_DIR, "sync-db-to-cloud.py")
    result = subprocess.run(
        [sys.executable, sync_script, "--no-restart"],
        capture_output=True, text=True, timeout=60,
    )
    print(result.stdout.strip())

    # 3. Restart cloud backend separately for reliability
    print("[cron] Step 3: Restart cloud backend...")
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect("100.107.117.23", username="administrator",
                       password="root123root!@", timeout=15)
        stdin, stdout, stderr = client.exec_command(
            "cd /home/administrator/news-intel-web && docker compose restart backend"
        )
        print(f"[cron]   {stdout.read().decode().strip()}")
        client.close()
    except Exception as e:
        print(f"[cron]   Restart failed: {e}")

    print(f"[cron] === Done {time.strftime('%H:%M:%S')} ===")


if __name__ == "__main__":
    main()

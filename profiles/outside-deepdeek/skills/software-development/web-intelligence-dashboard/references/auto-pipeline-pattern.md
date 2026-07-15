# auto-pipeline.py — Fully Automated RSS→Cloud Pipeline

## Overview
Triggered by Hermes cron every 15 minutes. Runs the complete pipeline with zero manual intervention.
Replaces the old cron-sync.py (SFTP/paramiko model).

## Execution Flow
```
1. Sync+Score (~3s)
   subprocess: python -m news_intel.pipeline --hours 2
   Only processes articles from last 2 hours (incremental)

2. Fetch (~2-5min, timeout 480s)
   Queries SQLite for unfetched Tier A/B articles
   Generates URL list → batch.py (ThreadPoolExecutor, 4 workers)
   Imports results from _fetch_tmp.jsonl back to DB

2.5. Push article content to PG
   SELECT all articles with content_len > 0 from SQLite
   HTTP POST /internal/news/batch (batch push, single request)

3. Aggregate (~0.1s)
   Python import: aggregate_events() on up to 300 rows
   Writes to event_registry, source_registry, entity_registry

4. Cloud Sync (~5s)
   SELECT all events from event_registry
   HTTP POST /internal/events/batch
   ON CONFLICT(event_id) DO UPDATE

5. Summary log
   Total elapsed time
```

## Registration
```bash
# Manual: edit cron/jobs.json
{
  "auto-pipeline": {
    "name": "auto-pipeline",
    "script": "auto-pipeline.py",
    "schedule": "once in 15m",
    "repeat": "forever",
    "no_agent": true,
    "enabled": true,
    "state": "scheduled",
    "deliver": "local"
  }
}
```

## Environment Variables
- `NEWS_API_BASE=http://100.107.117.23` — Cloud V8 backend
- `NEWS_API_TOKEN=v8-pipeline-token-2026-...` — Internal auth token

## Key Differences from cron-sync.py (deprecated)
- No SFTP/SCP: data transfer via HTTP POST only
- No paramiko dependency: uses httpx
- No SSH restart: server-side ON CONFLICT upsert, immediate visibility
- Smaller: ~160 lines vs old ~200 lines

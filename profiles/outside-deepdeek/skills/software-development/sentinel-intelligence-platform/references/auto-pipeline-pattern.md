# Auto-Pipeline Cron Pattern

## Problem
Pipeline stalls because no automatic trigger connects RSS ingestion to event aggregation to cloud sync. Manual `python -m news_intel.pipeline --hours 48 --fetch` works but must be run by hand.

## Solution: standalone Python script run by Hermes cron

File: `auto-pipeline.py` at project root.

### Key Design Decisions

1. **15-minute interval** — fast enough for news ingestion, slow enough to avoid resource waste
2. **5 sequential steps** — Sync(3s) → Fetch(2-5min) → Aggregate(0.1s) → Cloud Sync(5s) → Summary
3. **Batch timeout at 480s** — subprocess.run with generous timeout to avoid the 300s pipeline.py default
4. **Result import after batch** — reads `_fetch_tmp.jsonl` and UPDATEs `news_content` directly (bypasses pipeline.py timeout)
5. **No new dependencies** — uses existing httpx, sqlite3, json, subprocess

### Cron Registration

```python
# In cron/jobs.json:
{
  "auto-pipeline": {
    "name": "auto-pipeline",
    "script": "auto-pipeline.py",
    "schedule": "once in 15m",
    "repeat": "forever",
    "no_agent": true,
    "enabled": true
  }
}
```

### Flow

```
RSS Scanner (external, 30min) → writes to rss-archive.db
    │
auto-pipeline.py (15min cron)
    ├── ① Sync+Score: subprocess ["python", "-m", "news_intel.pipeline", "--hours", "2"]
    ├── ② Fetch: subprocess ["python", "batch.py", "--urls", tmp_file, ...] timeout=480
    │       └── Import: read JSONL → UPDATE news_content
    ├── ③ Aggregate: from news_intel.aggregator import aggregate_events → write event_registry
    ├── ④ Cloud Sync: httpx.post("/internal/events/batch", json=events)
    └── ⑤ Summary log: elapsed time
```

### Verification

```bash
python auto-pipeline.py
curl http://100.107.117.23/api/v1/dashboard
```

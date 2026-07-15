# V8 Pipeline Automation Pattern

## Architecture

```
RSS Scanner (external cron 30min)
    |
    v
auto-pipeline.py (Hermes cron 15min, no_agent)
    |
    +-- 1. Sync+Score (news_intel.pipeline --hours 2, ~3s)
    +-- 2. Fetch (batch.py, ~2-5min, timeout 480s)
    +-- 3. Aggregate (aggregator.py, ~0.1s)
    +-- 4. Cloud Sync (HTTP POST /internal/events/batch, ~5s)
    |
    v
http://<cloud-ip> (immediate update, no restart)
```

## Key Design Decisions

1. **HTTP POST not SFTP**: The old pattern of SCP'ing SQLite files to cloud + SSH restart was replaced with `httpx.post("http://<cloud>/internal/events/batch")`. No paramiko dependency. No restart needed. Data visible immediately.

2. **Incremental fetch**: Only fetch Tier A/B articles that have no content (`content_md IS NULL OR content_md = ''`). Previously this was broken — the SQL checked `nc.id IS NULL` which missed placeholder rows. Fixed to: `nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = ''`.

3. **Batch timeout handling**: `pipeline.py` has a 300s subprocess timeout. For large batches (200+ URLs), `batch.py` needs 5-10 minutes. The `auto-pipeline.py` script runs `batch.py` separately with a 480s timeout and imports the JSONL results into the DB after the subprocess completes.

4. **Entity JSON parsing**: The aggregator.py had multiple places where `entities` came from the DB as JSON strings but were used as dicts. Fixed with `if isinstance(entities, str): try: entities = json.loads(entities); except: entities = {}`.

## Cron Registration

```python
# ~/AppData/Local/hermes/profiles/<profile>/cron/jobs.json
{
  "auto-pipeline": {
    "name": "auto-pipeline",
    "script": "auto-pipeline.py",
    "schedule": "once in 15m",
    "repeat": "forever",
    "no_agent": true,
    "enabled": true,
    "state": "scheduled"
  }
}
```

## Cloud PG Schema Fix

When the PG events table was created from an older migration, it lacked the Dossier fields (evidence, source_chain, timeline, etc.). The fix was:

```sql
ALTER TABLE events ADD COLUMN IF NOT EXISTS evidence JSONB;
ALTER TABLE events ADD COLUMN IF NOT EXISTS source_chain JSONB;
ALTER TABLE events ADD COLUMN IF NOT EXISTS timeline JSONB;
-- ... 19 more columns
```

And the backend's internal.py needed `from sqlalchemy import text` and `db.execute(text("""SQL"""), params)` for SQLAlchemy 2.0 compatibility.

## Pipeline Health Check

```bash
python pipeline_check.py check
# Output: RSS→PIPELINE→FETCHER→AGGREGATOR→SQLITE→SYNC→API status
# YAML-style output for Agent consumption
```

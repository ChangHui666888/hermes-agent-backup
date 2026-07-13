# Profile Landscape Analysis Pattern

Before building any web product on top of an existing pipeline, scan the full profile structure.

## Scan Checklist

1. List all subdirectories under scripts/ to find projects
2. Check for news_intel.db — the event_registry SQLite is the data source
3. Compare local vs cloud DB timestamps for sync status
4. Check cron jobs in cron/jobs.json
5. Check skills directory for accumulated knowledge
6. Check workspace for abandoned experiments

## Typical Layout

```
profile/outside-deepdeek/
  skills/research/search-engine-v2/scripts/
    news_intel/           Pipeline (data production)
    news-intel-platform/  Old web (frozen, DO NOT recover)
    news-intel-web/       Current web (production)
  scripts/                Cron scripts
  cron/                   Cron job definitions
  workspace/              One-off experiments (safe to clean)
```

## Project Relationships

news_intel (Pipeline) → SQLite → news-intel-web (Dashboard) → Docker Cloud
news-intel-platform is frozen — never docker compose up on it.

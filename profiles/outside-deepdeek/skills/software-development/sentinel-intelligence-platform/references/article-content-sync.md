# Article Content Sync Pattern

## Problem

The V8 pipeline pushes articles to PostgreSQL during sync+score (Step 1), but the content
is only fetched later in batch.py (Step 2). After fetching, the content exists in SQLite
but is **never pushed back to PG**, leaving articles in PG with `content_len=0`.

## Fix: auto-pipeline Step 2.5

In `auto-pipeline.py`, add a step between fetch and aggregate that pushes all articles
with content to PG:

```python
# Step 2.5: Push article content to PG
conn = sqlite3.connect(db_path)
rows = conn.execute("""
    SELECT rr.article_url, rr.title, nc.content_md, nc.content_len,
           ni.score_total, ni.tier, rr.source_name, rr.source_domain,
           nc.fetch_strategy, nc.fetch_cost
    FROM news_content nc
    JOIN news_intelligence ni ON nc.intel_id = ni.id
    JOIN rss_raw rr ON ni.raw_id = rr.id
    WHERE nc.content_len > 0
""").fetchall()

if rows:
    body = [{'url':r[0],'title':r[1],'content_md':r[2],'score_total':r[4],'tier':r[5],
             'source_name':r[6],'source_domain':r[7],'fetch_strategy':r[8],'fetch_cost':r[9]}
            for r in rows]
    r = httpx.post(f"{CLOUD_API}/internal/news/batch", json=body,
                    headers={'X-Internal-Token': TOKEN}, timeout=30)
```

## Verification

After running, verify PG has content:
```bash
docker exec news-platform-v8-postgres-1 psql -U news_admin -d news_intel \
  -t -c "SELECT COUNT(*) FROM articles WHERE length(content_md) > 0"
```

## Note

The `/internal/news/batch` endpoint uses `ON CONFLICT (url) DO UPDATE` which updates
`content_md`, `title`, `score_total`, `tier`. It does NOT update `content_len` —
this was omitted to keep the upsert minimal. The article detail page uses `content_md`
directly, so `content_len` being stale doesn't affect the frontend.

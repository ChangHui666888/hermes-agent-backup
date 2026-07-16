# Retry Tracking & Comprehensive Recovery

## Problem

Placeholder rows (`fetch_strategy IS NULL, content_md=''`) block re-fetch.
The batch pipeline creates news_content rows but fails to fill content for
paywalled/anti-bot sources. Without retry tracking, these URLs are retried
indefinitely or skipped because the query only checks `nc.id IS NULL`.

## Retry Column

Add to `news_content`:

```sql
ALTER TABLE news_content ADD COLUMN retry_count INTEGER DEFAULT 0;
```

## Retry Logic (in auto-pipeline.py Step 3)

On fetch success:
- INSERT/UPDATE with `retry_count=0`

On fetch failure:
```python
conn.execute("""
    UPDATE news_content SET retry_count = COALESCE(retry_count,0) + 1
    WHERE article_url = ?
""", (url,))
conn.execute("""
    UPDATE news_content SET fetch_strategy = 'exhausted'
    WHERE article_url = ? AND COALESCE(retry_count,0) >= 3
""", (url,))
```

## Fetch Queue Exclusion

The Step 3 query must exclude exhausted rows:

```sql
SELECT DISTINCT rr.article_url FROM news_intelligence ni
JOIN rss_raw rr ON ni.raw_id = rr.id
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A','B')
  AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
  AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
  AND rr.article_url IS NOT NULL AND rr.article_url != ''
LIMIT 50
```

## Cleanup Step (Step 0)

Added before Step 1 to periodically remove exhausted placeholder rows:

```python
conn.execute("""
    DELETE FROM news_content
    WHERE fetch_strategy IS NULL
      AND (content_md IS NULL OR content_md = '')
      AND retry_count >= 3
""")
```

This frees URLs to re-enter the queue through RSS_FULLTEXT.

## Comprehensive Recovery Pass (Step 3.5)

Replaces inline SearXNG/Tavily blocks with reusable functions that scan
ALL empty content rows (not just those in the current batch):

### SearXNG (score 80-89, free, max 10/run)
```python
def _recover_searxng(title, intel_id, url):
    q = (title or url)[:80]
    resp = httpx.get('http://100.107.117.23:8080/search',
                     params={'q': q, 'format': 'json'}, timeout=10)
    for alt in resp.json().get('results', [])[:2]:
        alt_url = alt.get('url', '')
        if alt_url and alt_url != url:
            r2 = httpx.get(alt_url, timeout=10)
            if r2.status_code == 200 and len(r2.text) > 500:
                content = _extract_main_text(r2.text, url=alt_url)
                if content and len(content) > 200:
                    # INSERT ON CONFLICT DO UPDATE with retry_count=0
                    return True
    return False
```

### Tavily (score >=90, paid, max 5/run)
```python
def _recover_tavily(title, intel_id, url):
    resp = httpx.post('https://api.tavily.com/search', json={
        'api_key': TAVILY_KEY, 'query': (title or url)[:100],
        'search_depth': 'basic', 'max_results': 2, 'include_answer': True
    }, timeout=15)
    answer = resp.json().get('answer', '')
    if answer and len(answer) > 100:
        content = f'[Tavily]\n\n{answer}'
        # INSERT ON CONFLICT DO UPDATE with retry_count=0
        return True
    return False
```

### Candidate Selection
Both queries filter:
- `nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL`
- `nc.retry_count IS NULL OR nc.retry_count < 3`
- `nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = ''`

## Batch Size Tuning

Scrapling (Playwright headless) is slow (~10-15s per URL on Windows).
With 200 URLs and 3 workers: easily exceeds 600s timeout.

**Recommended**: `LIMIT 50`, `--max-workers 8`, `--rate-delay 0.1`
→ ~140s for 50 URLs, well under the 600s BATCH_TIMEOUT.

## INSERT ON CONFLICT Pattern

Always use `INSERT ... ON CONFLICT(article_url) DO UPDATE` instead of
separate SELECT + conditional INSERT/UPDATE. This handles both:
- Creating rows for URLs that don't exist yet
- Updating rows that already have a placeholder

All inserts MUST include `retry_count=0` to reset the counter on success.

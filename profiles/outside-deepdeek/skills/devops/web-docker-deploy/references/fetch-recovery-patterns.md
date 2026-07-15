# Fetch Recovery Patterns

## Cascade Architecture (cost-ordered)

```
RSS FullText (cost=0) → Direct (cost=1) → Archive (cost=1) → Scrapling (cost=2)
  → [score 80-89] SearXNG alt URL search (cost=2, free)
  → [score >=90] Tavily AI search (cost=5, premium)
```

## RSS FullText (Step 0)

Before any HTTP fetch, check if RSS description is usable:
- `description >= 200 chars`
- HTML tag ratio < 30%
- No boilerplate keywords

If yes: write directly to news_content with `strategy='rss_fulltext', cost=0`.
Saves ~23% of HTTP requests.

Implementation: pipeline.py pre-check before batch.py call.

## SearXNG Configuration

SearXNG Docker requires specific config for API access:

```yaml
server:
  bind_address: "0.0.0.0"     # NOT 127.0.0.1 — Docker containers can't reach localhost
  limiter: false               # No rate limiting for internal calls
  public_instance: false       # NOT true — enables bot protection

search:
  formats:
    - html
    - json                     # Must be explicitly enabled
```

Environment variable `SEARXNG_PORT` in docker-compose overrides yaml `port`.

## Tavily Integration

```python
resp = httpx.post("https://api.tavily.com/search", json={
    "api_key": TAVILY_KEY,
    "query": title,
    "search_depth": "basic",
    "max_results": 2,
    "include_answer": True,
}, timeout=15)
```

Cost: 5 per call. Max 5 calls per pipeline run. Only for score >=90 articles.

## Pipeline Logging

auto-pipeline.py writes per-step statistics to `pipeline.log`:

```
[2026-07-14 18:30:03] Step 3/6: Fetch (batch.py)
[2026-07-14 18:35:21]   FETCH: 123 ok, 42 fail (74%) 200 URLs
```

Format: `[timestamp] STEP_NAME: ok ok, fail fail (rate%) detail`

## Domain Strategy Statistics

PG `fetch_stats` table tracks per-domain per-strategy success rates:

```sql
SELECT domain, strategy, SUM(ok_count) as ok, SUM(fail_count) as fail,
       ROUND(SUM(ok_count)*100.0/MAX(SUM(ok_count)+SUM(fail_count),1),1) as rate
FROM fetch_stats
GROUP BY domain, strategy
ORDER BY SUM(ok_count+fail_count) DESC;
```

Pushed from auto-pipeline.py Step 3 after batch.py completes.

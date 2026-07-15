# Fetch Cascade Recovery Chain

## Complete Chain

```
RSS FullText (cost=0) → Direct (cost=1) → Archive (cost=1) → Scrapling (cost=2)
    → [fail + score 80-89] SearXNG alt URL search (cost=2, free, max 10/run)
    → [fail + score >=90] Tavily AI search (cost=5, paid, max 5/run)
```

## SearXNG Integration

SearXNG runs on cloud Docker at port 8080. API endpoint: `/search?q=...&format=json`

```python
SEARXNG_URL = "http://100.107.117.23:8080"

resp = httpx.get(f"{SEARXNG_URL}/search",
    params={"q": title[:80], "format": "json"},
    headers={"User-Agent": "NewsIntelBot/1.0"}, timeout=10)
data = resp.json()
alt_urls = [r["url"] for r in data.get("results", [])[:2]]
# Try fetching alternative URLs
for alt_url in alt_urls:
    content = fetch_direct(alt_url)
    if content: write_to_db(strategy="searxng_alt")
```

## Tavily Integration

Only for score >=90 articles. Uses Tavily's AI-powered search with answer generation.

```python
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "...")
resp = httpx.post("https://api.tavily.com/search", json={
    "api_key": TAVILY_KEY, "query": title[:100],
    "search_depth": "basic", "max_results": 2, "include_answer": True,
}, timeout=15)
data = resp.json()
if data.get("answer") and len(data["answer"]) > 100:
    content = f"[Tavily]\n\n{data['answer']}"
    write_to_db(strategy="tavily", cost=5)
```

## SearXNG Docker Configuration

If `/search?format=json` returns 403, check:

1. `settings.yml` formats must include `json`:
```yaml
search:
  formats:
    - html
    - json
```

2. Server settings for internal use:
```yaml
server:
  bind_address: "0.0.0.0"  # NOT 127.0.0.1 (breaks Docker networking)
  limiter: false
  public_instance: false   # NOT true (enables bot protection)
```

3. Environment variables may override settings:
```bash
docker exec searxng-core env | grep SEARXNG
# SEARXNG_PORT=8080 may override port:8888 in yaml
```

4. Test from host (not container):
```bash
curl "http://100.107.117.23:8080/search?q=test&format=json"
```

## Recovery in auto-pipeline.py

Two separate steps added after FETCH:

```python
# Step 3.5: SearXNG (score 80-89, free, max 10)
failed_urls = conn.execute("""
    SELECT ... FROM news_intelligence ni
    JOIN rss_raw rr ON ni.raw_id = rr.id
    LEFT JOIN news_content nc ON nc.intel_id = ni.id
    WHERE ni.tier IN ('A','B') AND ni.score_total >= 80 AND ni.score_total < 90
      AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
    LIMIT 10
""").fetchall()
# For each: search SearXNG → fetch alt URL → write to DB

# Step 3.6: Tavily (score >=90, paid, max 5)
failed_high = conn.execute("""
    SELECT ... WHERE ni.score_total >= 90 ... LIMIT 5
""").fetchall()
# For each: call Tavily API → write answer to DB
```

Both steps write `step_result()` to pipeline.log with ok/fail counts.

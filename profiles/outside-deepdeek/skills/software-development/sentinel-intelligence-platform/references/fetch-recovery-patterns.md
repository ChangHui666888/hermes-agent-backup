# Fetch Recovery Patterns — SearXNG + Tavily

## Existing Cascade

```
RSS FullText (cost=0) → Direct → Archive → GoogleCache → Scrapling → Browser
```

## Tavily Recovery (Implemented)

After all cascade strategies fail, for high-score articles (>=85), call Tavily Search API
as a last-resort content recovery. This is NOT a strategy in the cascade — it's a
**post-processing step** in `pipeline.py` after `batch.py` completes.

```python
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "...")

# After batch.py results are collected:
failed_high = [url for url in urls if url not in fetched_content and score >= 85]
for url in failed_high[:5]:  # Max 5 per run
    resp = httpx.post("https://api.tavily.com/search", json={
        "api_key": TAVILY_KEY, "query": url,
        "search_depth": "basic", "max_results": 2, "include_answer": True,
    })
    answer = resp.json().get("answer", "")
    if answer and len(answer) > 100:
        content = f"[Tavily]\n\n{answer}"  # Strategy: tavily, cost=5
```

Key design decisions:
- **Location**: In `pipeline.py` (not `batch.py`) — keeps batch.py focused on cascade
- **Limit**: Max 5 calls per pipeline run (cost control)
- **Score gate**: Only >=85 score articles trigger Tavily
- **Marking**: Strategy="tavily", cost=5 (clearly premium)
- **Tavily free tier**: 1000 calls/month — sufficient for this volume

## SearXNG Investigation (Not Implemented)

SearXNG runs on cloud (port 8080) but API access returns 403 Forbidden.
Investigation results:

- **Web UI works**: `http://100.107.117.23:8080/` — manual search functional
- **API blocked**: `GET /search?q=test&format=json` → 403 regardless of config changes
- **Attempted fixes** (all failed):
  1. Added `json` to `formats` list in settings.yml
  2. Set `public_instance: true`
  3. Changed `method: "POST"` to `method: "GET"`
  4. Added browser User-Agent header
- **Root cause**: SearXNG has built-in bot protection at the server level
  (limiter, Nginx config, or rate-limit middleware) that cannot be disabled
  via settings.yml alone. The Docker image's embedded Nginx may be blocking
  non-browser requests regardless of SearXNG settings.

**Recommendation**: Use Tavily as primary search recovery. SearXNG is useful
for manual research but not for automated pipeline integration in its current
configuration. If SearXNG API is needed, investigate the Docker image's Nginx
config or switch to a different SearXNG instance with API access enabled.

## Alternative: Direct SearXNG URL Discovery

Even without the JSON API, SearXNG web search can find alternative URLs for
failed articles. A browser-based approach (Playwright/Scrapling) could scrape
the HTML search results page, but this adds complexity and cost (cost=3 for
browser strategy). Not worth it for V1.

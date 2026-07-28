# Third-party fallback strategies (Jina Reader + Tavily)

When local cascade strategies (direct, archive, google_cache, scrapling, browser) all fail for anti-bot/paywall sites, two zero-configuration third-party APIs can serve as fallbacks.

## Jina Reader (`jina` strategy, cost=2)

**API**: `https://r.jina.ai/URL` → returns markdown content
**Key**: Free, no account needed
**Rate limit**: ~100 req/day on free tier
**Timeout**: 10s in cascade (15s total with curl overhead)

### IPv6 workaround (critical on this network)

`r.jina.ai` resolves to both IPv4 (`154.83.14.134`) and IPv6. IPv6 is unreachable from this Windows host → SSL connection fails silently.

**Fix**: Use `curl -4` subprocess instead of httpx:
```python
import subprocess
result = subprocess.run(
    ["curl", "-4", "-s", "--max-time", str(timeout),
     f"https://r.jina.ai/{target_url}",
     "-H", "Accept: text/plain, text/markdown, */*"],
    capture_output=True, text=True, timeout=timeout + 2)
```

`curl -4` forces IPv4 resolution. httpx cannot force IPv4 natively.

### Content quality

| Source | Result | Note |
|--------|--------|------|
| BBC News | ✅ 16,577 chars | Full article markdown |
| CNBC Tech | ✅ 31,033 chars | Full article markdown |
| Bloomberg | ✅ 1,043 chars | Partial content (paywall detected at render time) |
| Reuters | ✅ 753 chars | Summary-level |
| MarketWatch | ✅ 208 chars | Minimal (CAPTCHA gate) |
| WaPo | ❌ | Timeout |

### Failure modes

| Symptom | Cause | Action |
|---------|-------|--------|
| Empty/000 HTTP | IPv6 attempted, network unreachable | Force IPv4 (`curl -4`) |
| `Warning: This page maybe requiring CAPTCHA` | Jina couldn't bypass either | Accept short content, don't retry |
| Timeout >10s | Jina render backlog or slow site | Let cascade continue to next strategy |

## Tavily (`tavily` strategy, cost=3)

**API**: `POST https://api.tavily.com/search` → returns AI-generated summary
**Key**: `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` (free dev key)
**Rate limit**: Dev tier ~10 req/min
**Timeout**: 10s

### Implementation

```python
# Build search query from URL path segments
from urllib.parse import urlparse
path = urlparse(url).path
segments = [s.replace('-', ' ') for s in path.split('/') if s and len(s) > 6]
query = ' '.join(segments[:4]) if segments else url[:100]

resp = httpx.post("https://api.tavily.com/search", json={
    "api_key": TAVILY_DEV_KEY,
    "query": query,
    "search_depth": "basic",
    "max_results": 2,
    "include_answer": True,
})
answer = resp.json().get("answer", "")
return f"[Tavily summary]\n\n{answer}"
```

### Content quality

| Source | Result | Note |
|--------|--------|------|
| MarketWatch | ✅ ~300 chars | AI summary of the article topic |
| Reuters | ✅ ~300 chars | AI summary |
| BBC/CNBC | ❌ not used | direct already works |

### Advantages over Jina Reader

- Works reliably regardless of IPv6/DNS issues (httpx with direct domain)
- Returns structured data with citation sources
- Faster than Jina for simple queries

### Disadvantages vs Jina Reader

- Summary only (200-500 chars), never full article text
- Costs API quota (dev tier limited)
- Query extraction from URL path is fragile; may return irrelevant content

## Cascade integration

Both strategies are registered in `extract_single()`'s `STRATEGY_FN` and `COST` dicts:

```python
STRATEGY_FN = {
    ...
    "jina": lambda u: fetch_jina_reader(u, rate_limiter),
    "tavily": lambda u: fetch_tavily(u, rate_limiter),
    ...
}
COST = {"direct": 1, "archive": 1, "google_cache": 1, "search_snippet": 1,
        "scrapling": 2, "jina": 2, "tavily": 3, "browser": 3, "computer_use": 5}
```

They sit at the END of each domain's `strategy_order`, after all local strategies:
```python
# reuters.com: archive → google_cache → jina → tavily → search_snippet
# marketwatch.com: direct → archive → google_cache → jina → tavily → search_snippet
```

## Cost trade-off

jina is cost=2 and tavily is cost=3 because:
- jina: free API, delivers full markdown when it works, but has IPv6/CAPTCHA issues
- tavily: free dev key, faster, more reliable, but only delivers AI summaries

Both are cheaper than browser (cost=3) and far cheaper than computer_use (cost=5).

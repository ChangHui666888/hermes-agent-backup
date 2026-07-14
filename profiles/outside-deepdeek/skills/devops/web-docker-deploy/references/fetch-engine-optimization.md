# Fetch Engine Optimization Reference

## Scrapling Timeout Fix (critical)

**Bug**: `core/fetchers.py` line 308 passes timeout in seconds but Scrapling's `StealthyFetcher.fetch()` expects milliseconds.

```python
# WRONG — 45 seconds becomes 45 milliseconds
resp = fetcher.fetch(url, timeout=timeout)

# CORRECT
resp = fetcher.fetch(url, timeout=int(timeout * 1000))
```

This caused ALL Scrapling attempts to timeout at 45ms instead of 45s. Affected France24, investing.com, and other sites needing headless browser fallback.

## Pipeline Fetch Gap Fix

**Bug**: `news_intel/pipeline.py` line 66 checked only `nc.id IS NULL`, missing articles with empty placeholder rows.

```sql
-- WRONG — misses articles with content_md=''
WHERE ni.tier IN ('A', 'B') AND nc.id IS NULL

-- CORRECT
WHERE ni.tier IN ('A', 'B')
  AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
```

## Direct Fetch Headers (Frozen)

```python
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

RETRY_STATUS = {408, 429, 500, 502, 503, 504}  # NOT 403
MAX_RETRIES = 3
```

**Effect**: France24 went from 403→OK after adding Sec-Fetch-* headers.

## DirectClientPool Pattern

Domain-isolated httpx.Client pool for cookie persistence:

```python
class DirectClientPool:
    def __init__(self, max_domains=50):
        self._clients = {}
        self._access = {}
        self._lock = threading.Lock()
    
    def get(self, url: str) -> httpx.Client:
        domain = urlparse(url).netloc
        with self._lock:
            if domain not in self._clients:
                if len(self._clients) >= self._max:
                    self._evict_lru()
                self._clients[domain] = _make_client(url=url)
            self._access[domain] = time.monotonic()
            return self._clients[domain]
```

**Rules**:
- Thread-safe via threading.Lock
- LRU eviction at max_domains
- Pool applies to fetch_direct ONLY (not archive/scrapling/browser)
- Uses urlparse (no tldextract dependency)
- NO Referer header (unnatural for news sites)
- NO TLS fingerprint (httpx can't do it — delegate to Scrapling)

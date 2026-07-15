# Fetch Engine Optimization Patterns

## Frozen Headers

Located in `core/fetchers.py`. The `DEFAULT_HEADERS` dict replaces the old `_make_client` per-call headers.

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
```

Key additions over basic headers:
- `Sec-Fetch-*` headers — modern browser fingerprint required by anti-bot systems
- Removed `br` from Accept-Encoding (brotli caused issues with some proxies)
- Removed `zh-CN` from Accept-Language (some sites block non-English locales)

Result: France24 went from 403 Forbidden → 200 OK.

## Retry Logic

```python
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    resp = client.get(url)
    if resp.status_code in RETRY_STATUS:
        wait = 2 ** attempt  # 1s, 2s, 4s
        time.sleep(wait)
        continue
    resp.raise_for_status()
```

**403 is explicitly EXCLUDED** from retry — retrying a forbidden request won't help and wastes time.

## ClientPool (Domain-Level Cookie Sharing)

```python
class DirectClientPool:
    def __init__(self, max_domains=50):
        self._clients = {}
        self._lock = threading.Lock()
    
    def get(self, url):
        domain = urlparse(url).netloc
        if domain not in self._clients:
            if len(self._clients) >= self._max:
                self._evict_lru()
            self._clients[domain] = httpx.Client(headers=DEFAULT_HEADERS, ...)
        return self._clients[domain]
```

Benefits:
- Same-domain requests share cookies (Set-Cookie from first request persists)
- Thread-safe via lock
- LRU eviction prevents memory leaks
- Module-level singleton: `_direct_client_pool = DirectClientPool(max_domains=50)`

**Scope**: fetch_direct only. archive/google_cache/scrapling do NOT use the pool.

## Scrapling Timeout: Milliseconds vs Seconds

Scrapling's `fetch(url, timeout=...)` expects **milliseconds**, not seconds.
Passing 45.0 is interpreted as 45ms → instant timeout.

```python
# ❌ WRONG:
resp = fetcher.fetch(url, timeout=45.0)  # 45ms!

# ✅ CORRECT:
resp = fetcher.fetch(url, timeout=int(45.0 * 1000))  # 45000ms = 45s
```

## httpx.Timeout (Structured)

```python
client = httpx.Client(
    timeout=httpx.Timeout(connect=5, read=15, write=10, pool=5)
)
```

Replaces the old `timeout=30.0` flat timeout. Structured timeouts prevent hanging on slow reads.

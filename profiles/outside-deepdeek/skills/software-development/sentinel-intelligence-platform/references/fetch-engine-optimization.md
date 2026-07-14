# Fetch Engine Optimization — Frozen Headers + Retry + Client Pool

## Default Headers (frozen)

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

NOT included: Referer (news articles have no referrer), TLS fingerprint (httpx can't do it, leave to Scrapling), JS challenge (leave to Scrapling/Playwright).

## Retry Strategy

- **Retryable statuses**: `{408, 429, 500, 502, 503, 504}`
- **NOT retried**: 403 (bot detection — retry won't help)
- **Backoff**: exponential `2**attempt` seconds (1s, 2s, 4s)
- **Max attempts**: 3

## Timeout Configuration

```python
httpx.Timeout(connect=5, read=15, write=10, pool=5)
```

Per-operation timeouts instead of single global timeout.

## DirectClientPool

Domain-isolated httpx.Client pool for `fetch_direct` only (not archive/scrapling/browser):

- Per-domain client reuse for cookie persistence
- Thread-safe via `threading.Lock`
- LRU eviction at max_domains (default 50)
- Module-level singleton: `_direct_client_pool = DirectClientPool(max_domains=50)`

Usage: `client = _direct_client_pool.get(url)` — returns cached or new client for the domain.
Do NOT close the client — pool manages lifecycle.

## Domain Profiles

Add failing domains to `config/domain_profiles.py` to skip known-failing strategies:

```python
"france24.com": DomainProfile(
    domain="france24.com",
    anti_bot="cloudflare",
    strategy_order=["archive", "direct", "search_snippet"],
    known_failing=["scrapling", "browser"],
)
```

This prevents wasting 45s on Scrapling timeout for France24 (which always fails).

## Scrapling Timeout Bug

**Root cause**: `Scrapling.StealthyFetcher.fetch(url, timeout=...)` expects **milliseconds**.
Code passed `timeout=45.0` (seconds) → interpreted as 45ms → instant timeout.
**Fix**: `resp = fetcher.fetch(url, timeout=int(timeout * 1000))`
Location: `core/fetchers.py`, `fetch_scrapling()` function.

## Verification

Use `test_fetch.py` for targeted testing:
```bash
python test_fetch.py                          # 10 sample URLs
python test_fetch.py --url "https://..."      # single URL debug
python test_fetch.py --source "France 24"     # by source name
python test_fetch.py --all                    # all unfetched Tier A/B
```

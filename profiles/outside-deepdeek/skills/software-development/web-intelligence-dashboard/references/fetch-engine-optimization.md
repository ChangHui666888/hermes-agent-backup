# Fetch Engine Optimization Patterns

## Frozen Headers

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

**Key addition**: Sec-Fetch-* headers made France24 go from 403→200. These are modern browser fingerprint headers that anti-bot systems check.

## Client Pool Pattern

```python
class DirectClientPool:
    """Domain-isolated httpx.Client pool for fetch_direct.
    Reuses Client per domain for cookie persistence.
    Thread-safe via threading.Lock. LRU eviction at max_domains=50.
    """
```

**DO NOT** share pool across all strategies — only fetch_direct. Archive/google_cache/scrapling each manage their own clients.

## Scrapling Timeout Bug

Scrapling's `StealthyFetcher.fetch(url, timeout=N)` expects **milliseconds**, not seconds:

```python
# WRONG (45 seconds passed as 45ms → instant timeout)
resp = fetcher.fetch(url, timeout=45.0)

# RIGHT
resp = fetcher.fetch(url, timeout=45000)
```

## Retry Strategy

```python
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_RETRIES = 3

# Exponential backoff: 1s, 2s, 4s
# 403 is EXCLUDED — no point retrying forbidden responses
```

## What NOT to Add

- ❌ Referer header (fake referer from google.com looks suspicious)
- ❌ TLS fingerprint simulation (httpx can't do it; leave to scrapling)
- ❌ JS challenge handling in direct strategy (leave to scrapling)

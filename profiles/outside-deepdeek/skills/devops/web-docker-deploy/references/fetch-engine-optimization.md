# Fetch Engine Optimization Patterns

## Scrapling Timeout Bug

**Root cause**: `fetchers.py` line 308 passes timeout in seconds to Scrapling's `fetch()` which expects **milliseconds**. `45.0` → interpreted as **45ms**, causing instant timeout on all Scrapling calls.

**Fix**: `resp = fetcher.fetch(url, timeout=int(timeout * 1000))` — converts 45s to 45000ms.

**Impact**: Was silently failing ALL Scrapling calls (cost=2 tier) for months. Only detected when analyzing France24/investing.com failures.

## Direct Fetch Header Optimization (Frozen)

```python
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 ... Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",        # NEW - browser fingerprint
    "Sec-Fetch-Mode": "navigate",        # NEW
    "Sec-Fetch-Site": "none",            # NEW
    "Upgrade-Insecure-Requests": "1",    # NEW
}
```

**What was added**: Sec-Fetch-* headers (standard browser headers that bots often miss)
**What was removed**: `br` from Accept-Encoding, `zh-CN` from Accept-Language (reduces fingerprint surface)
**What was NOT added**: Referer (news articles don't have one, faking google.com is suspicious), TLS fingerprint (httpx can't do this)

**Result**: France24 went from 403→direct fail to 200 OK.

## Retry Logic

```python
RETRY_STATUS = {408, 429, 500, 502, 503, 504}  # NOT 403
MAX_RETRIES = 3
# Exponential backoff: 1s, 2s, 4s
```

**Why exclude 403**: 403 means the server has made a deliberate decision to block. Retrying won't help.
**Why include 429**: Rate limiting — backing off usually works.

## httpx.Timeout

```python
timeout=httpx.Timeout(connect=5, read=15, write=10, pool=5)
```

Structured timeouts are safer than a single float — prevents hanging on slow connections while allowing slow reads.

## ClientPool Pattern (Approved, Not Yet Implemented)

```python
class ClientPool:
    def __init__(self):
        self.clients = {}  # domain → httpx.Client
    
    def get_client(self, url):
        domain = tldextract.extract(url)
        key = f"{domain.domain}.{domain.suffix}"
        if key not in self.clients:
            self.clients[key] = httpx.Client(headers=DEFAULT_HEADERS, ...)
        return self.clients[key]
```

**Purpose**: Same-domain URLs share cookies (Set-Cookie from first request reused on second).
**Isolation**: Different domains get separate clients (no cookie leakage).
**Requires**: `tldextract` pip package.

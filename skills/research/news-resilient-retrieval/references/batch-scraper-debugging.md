# Batch scraper infrastructure debugging (httpx, proxy, cascade strategies)

## The httpx 0.28 + HTTP CONNECT proxy problem

### Symptom
Python httpx 0.28.1 on Windows with an HTTP CONNECT proxy (Clash/V2Ray on localhost):
```python
client = httpx.Client(proxy='http://127.0.0.1:10808', timeout=10)
r = client.get('https://www.bbc.com')  # → ConnectTimeout: ssl handshake timeout
```
Sometimes works, sometimes hangs — **intermittent**. This is NOT the proxy being broken.

### Root cause
httpx 0.28.1 on Windows has **HTTP/2 connection pool issues** with HTTP CONNECT proxies. The SSL handshake through the CONNECT tunnel intermittently fails due to a state corruption in h2's connection reuse.

### Fix
```python
# Option A: Disable http2
client = httpx.Client(proxy='http://127.0.0.1:10808', http2=False, timeout=10)

# Option B: Use SOCKS5 proxy instead
client = httpx.Client(proxy='socks5://127.0.0.1:10808', timeout=10)
```
SOCKS5 + `http2=True` works fine — only the HTTP CONNECT + http2 combo is broken.

### Connection pooling exacerbates it
When using a per-domain client pool (common in scraper code), a stale connection with a failed SSL handshake poisons the pool for all subsequent requests to that domain. Fix: create fresh clients per request, or add connection health checks.

## Cascade strategy timing analysis

### The strategy chain
```python
strategy_order = ["direct", "archive", "google_cache", "scrapling", "browser", "search_snippet"]
```

### Per-strategy timeout cost (worst case)
| Strategy | Client timeout | With retries | 
|---|---|---|
| direct | 30s | ~45s (3 retries on 408/429/5xx) |
| archive.org | 30s | ~30s |
| google_cache | 30s | ~30s (often captcha) |
| scrapling | 45s | ~45s (slow init) |
| browser (Playwright) | 60s | ~60s (browser launch + load) |
| **Total worst case** | | **~165s per URL** |

### The exponential failure pattern (real data)
```
Run 1: 66% success   Direct+archive handle the easy ones
Run 2: 44%           Good sources consumed
Run 3: 10%           Hard sources start dominating
Run 4+: 2%           Only anti-bot/paywall URLs remain
```
At 2% success, each failed URL runs all 5 strategies (165s). 50 URLs × 165s = 8,250s. With 600s timeout, pipeline times out after 10 URLs.

### Fixes
```python
# 1. Lower per-strategy timeouts aggressively
direct_timeout: float = 15.0   # 30→15
archive_timeout: float = 15.0  # 30→15
scrapling_timeout: float = 20.0  # 45→20
browser_timeout: float = 30.0    # 60→30

# 2. Increase batch concurrency (safe with RateLimiter)
max_workers: 1 → 3   # 3x throughput
rate_delay: 1.0 → 0.3  # RateLimiter has per-domain lock

# 3. Log strategy-level failure reasons (not just "none:0/49")
# Current: {"ok": false}
# Better: {"ok": false, "failures": {"direct": "ConnectTimeout", "archive": "404", ...}}
```

## Domain profile knowledge base

This system uses `config/domain_profiles.py` to cache per-domain anti-bot characteristics:
```python
# Strong anti-bot → browser-first strategy
DomainProfile(domain='wsj.com', anti_bot='datadome',
    strategy_order=['browser', 'archive', 'google_cache', 'search_snippet'],
    known_failing=['scrapling'])

# Moderate anti-bot → direct-first  
DomainProfile(domain='cnbc.com', anti_bot='cloudflare',
    strategy_order=['direct', 'scrapling', 'archive', 'search_snippet'])
```

**Key insight**: If `browser` (Playwright) is unavailable, all strong-anti-bot domains silently become unfetchable. Always verify: `python -c "from playwright.sync_api import sync_playwright; print('OK')"`

**Key insight**: The domain profiles table is a cache of past debugging effort. Each domain profiled once saves ~165s on every future failed fetch. Keep it maintained.

## Verification toolkit

```bash
# 1. Test proxy types
curl -x socks5://127.0.0.1:10808 -s -o /dev/null -w "%{http_code} %{time_total}s" https://www.bbc.com
curl -x http://127.0.0.1:10808 -s -o /dev/null -w "%{http_code} %{time_total}s" https://www.bbc.com

# 2. Test httpx with http2 disabled (benchmark)
python -c "import httpx; c=httpx.Client(timeout=8, http2=False); r=c.get('https://www.bbc.com'); print(r.status_code, len(r.text))"

# 3. Test Playwright availability
python -c "from playwright.sync_api import sync_playwright; print('OK')"

# 4. Measure per-strategy timing (override/extract_single)
python -c "
import time
from core.fetchers import fetch_direct, RateLimiter
rl = RateLimiter(default_delay=0)
t0 = time.monotonic()
text = fetch_direct('https://www.reuters.com/world', rl)
t = time.monotonic()
print(f'direct: {len(text) if text else 0} chars in {t-t0:.1f}s')
"

# 5. Check pipeline log for timing breakdown
grep 'DONE in' pipeline.log
```

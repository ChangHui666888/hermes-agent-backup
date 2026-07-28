# RSS Cascade Engine Debug: Session Record

## System Under Test
- **Pipeline**: `auto-pipeline.py` (cron, 15min interval)
- **Cascade engine**: `core/fetchers.py` — 6 strategies: direct → archive → google_cache → scrapling → browser → search_snippet
- **Batch tool**: `batch.py` — ThreadPoolExecutor wrapper
- **Proxy**: Clash/V2Ray at 127.0.0.1:10808 (mixed HTTP + SOCKS5 port)

## What Failed
Pipeline log (2026-07-16) showed escalating fetch failure rates:

| Batch | Fetch Rate | Strategy Used | Duration |
|-------|-----------|---------------|----------|
| Run 1 | **0%** (0/50) | batch.py timeout 600s | 615s |
| Run 2 | **66%** (33/50) | direct:30, archive:3 | 530s |
| Run 3 | **44%** (22/50) | direct:22 | 453s |
| Run 4 | **10%** (5/50) | direct:5 | 552s |
| Run 5-7 | **2%** (1/50) | direct:1 | ~580s each |

Pattern: Easy URLs consumed first, leaving only anti-bot/paywall pages. Strategy breakdown: only "direct" ever succeeded — archive/scrapling/browser/google_cache returned zero across all runs.

### Browser Strategy Effectiveness (2026-07-27)

| Site | Browser Strategy | Content | Notes |
|------|----------------|---------|-------|
| Bloomberg | ✅ **Success** | 706 chars | `[browser] Found content selector: article` |
| Reuters | ❌ `Target crashed` | — | Playwright process killed by site anti-detection |
| MarketWatch | ❌ `None` | — | Browser detected, returns no content |
| CBS News | ✅ direct | 296-14,772 chars | No browser needed — direct works |
| BBC | ✅ direct | 867-7,024 chars | No browser needed |

Key lesson: Browser strategy is site-dependent. Bloomberg allows headless Chromium with anti-detection; Reuters and MarketWatch actively kill it. Always test before making browser the default for a new domain.

### Duplicate Domain Profile Bug

While adding `reuters.com` profile, encountered a Python dict key override:
```python
KNOWN_PROFILES = {
    "reuters.com": DomainProfile(strategy_order=["browser", "archive"]),  # ← OVERWRITTEN
    ...
    "reuters.com": DomainProfile(strategy_order=["direct"]),  # ← wins at runtime
}
```
Two entries with same key "reuters.com" → second silently overrides first. Verify with:
```bash
grep -n '"reuters.com"' config/domain_profiles.py  # should be exactly 1 match
```

## Root Causes Identified

### 1. httpx 0.28.1 http2=True SSL handshake hang (Windows + proxy)
- `python -c "import httpx; print(httpx.__version__)"` → `0.28.1`
- Environment `HTTPS_PROXY=http://127.0.0.1:10808`
- httpx with `http2=True` (default in v0.28) causes intermittent `ConnectTimeout: _ssl.c:989 handshake timed out`
- **Fix**: `http2=False`

### 2. Batch size too large (50 URLs × ~30s each = cascade death)
- Failed URL runs all 6 strategies before giving up
- Strategy timeouts: direct=30, archive=30, google_cache=30, scrapling=45, browser=60s
- Single failed URL worst case: 30+30+30+45+60 = ~195s
- 50 URLs at 2% success = ~49 failed × 30s = ~1470s → always hits 600s timeout
- **Fix**: `LIMIT 50 → LIMIT 5` in auto-pipeline.py

### 3. No per-strategy hard timeout
- `_make_client` sets client-level timeout, but individual fetch functions hang inside that client
- No signal.alarm or ThreadPoolExecutor wrapper on individual strategy calls
- **Fix**: Add `future.result(timeout=N)` per strategy in `extract_single()`

### 4. SOCKS5_stable but HTTP CONNECT was set via env
- `_make_client` read `HTTPS_PROXY=http://127.0.0.1:10808` → httpx HTTP CONNECT proxy
- `curl -x socks5://127.0.0.1:10808` works, `curl -x http://127.0.0.1:10808` also works but httpx HTTP CONNECT has issues
- **Fix**: Switch to `SOCKS5_PROXY=socks5://127.0.0.1:10808` as separate env var

### 5. Browser strategy absent from all successful runs
- `from playwright.sync_api import sync_playwright` → OK (installed)
- But `browser` never appeared in pipeline log as a successful strategy
- Reason: Domain profiles list browser first for bloomberg/WSJ/FT, but Playwright browser launch takes 3-5s + page load can hang for 60s. No evidence it was actually invoked — cascade likely timed out on earlier strategies.

## Verification Commands

```bash
# 1. Check httpx version
python -c "import httpx; print('httpx:', httpx.__version__)"

# 2. Test SOCKS5 + no-http2 stability (10 iterations)
for i in $(seq 10); do
  python -c "import httpx; httpx.Client(proxy='socks5://127.0.0.1:10808', http2=False, timeout=10).get('https://www.bbc.com')" && echo "OK $i" || echo "FAIL $i"
done

# 3. Test individual strategy performance
cd /path/to/scripts
python -c "
from core.fetchers import fetch_direct, RateLimiter
rl = RateLimiter(default_delay=0)
t = fetch_direct('https://www.techcrunch.com', rl)
print('TechCrunch:', len(t) if t else 'None')
"

# 4. Check Playwright availability
python -c "from playwright.sync_api import sync_playwright; print('OK')"

# 5. Check SearXNG
curl -s 'http://100.107.117.23:8080/search?q=test&format=json' | head -c 200

# 6. Verify proxy connectivity
curl -x socks5://127.0.0.1:10808 -s -o /dev/null -w '%{http_code}' --max-time 10 https://www.bbc.com

# 7. Check env proxy variables
echo "HTTPS_PROXY=$HTTPS_PROXY"
echo "SOCKS5_PROXY=$SOCKS5_PROXY"
```

## Configs Modified

| File | Change |
|------|--------|
| `auto-pipeline.py:125` | `LIMIT 50 → LIMIT 5` |
| `core/fetchers.py:230` | Added `http2: False` |
| `core/fetchers.py:233` | `HTTPS_PROXY env → SOCKS5_PROXY env or socks5://127.0.0.1:10808` |

## Observability

- Pipeline log: `scripts/pipeline.log`
- Per-URL cost traces: `scripts/news_intel/_fetch_tmp.jsonl`
- Domain profiles: `config/domain_profiles.py`
- Strategy timeouts: `config/settings.py`

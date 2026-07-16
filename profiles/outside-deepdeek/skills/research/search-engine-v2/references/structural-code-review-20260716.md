# Structural Root-Cause Fixes (2026-07-16 Code Review)

Six structural issues identified in `core/fetchers.py`, `batch.py`, and `pipeline_check.py`.
All fixed in commit `27bca74`.

---

## 1. RateLimiter Thread Safety

**Problem**: `wait()` used check-then-act (`read _last_request → sleep → write _last_request`) without a lock.
`fetch_browser()` also directly read/wrote `rate_limiter._last_request` private dict — double race.

**Fix**: Added `threading.Lock()` to `RateLimiter`. `wait()` split into two critical sections:
```python
with self._lock:
    last = self._last_request.get(domain, 0)
    remaining = delay - (time.monotonic() - last)
if remaining > 0:
    time.sleep(remaining)
with self._lock:
    self._last_request[domain] = time.monotonic()
```
New `wait_for(key, delay)` method handles browser cooldowns atomically.

---

## 2. Scrapling Cold-Start Per-URL

**Problem**: `fetch_scrapling()` called `StealthyFetcher()` fresh per URL. The browser context/TLS init
happens outside `timeout` control, causing ~20s per URL even on fast sites.

**Fix**: `ScraplingPool` class — lazy singleton with double-checked locking, like `DirectClientPool`:
```python
class ScraplingPool:
    def __init__(self):
        self._fetcher = None
        self._init_error = None  # cache import/init errors
        self._lock = threading.Lock()

    def get(self):
        if self._init_error: return None
        if self._fetcher is not None: return self._fetcher
        with self._lock:
            if self._fetcher is not None: return self._fetcher
            try:
                from scrapling import StealthyFetcher
                self._fetcher = StealthyFetcher()
            except ImportError as e:
                self._init_error = str(e)
        return self._fetcher
```
Pattern is reusable for any expensive resource that needs lazy singleton initialization.

---

## 3. fetch_browser: networkidle → domcontentloaded

**Problem**: `page.goto(url, wait_until="networkidle")` never resolves on news sites with analytics
trackers/ads that keep pinging. Browser strategy eats full 60s timeout every time.
`browser.chromium.launch()` and `new_page()` had no timeout protection.

**Fix**: 
- `wait_until="domcontentloaded"` — resolves when DOM is ready, not when network is idle
- Added `page.wait_for_selector("article, [role='main'], .article-body, .post-content", timeout=…)` 
  as a best-effort second wait
- `browser = p.chromium.launch(headless=True, timeout=int(timeout * 1000))` — launch now has timeout
- Browser cooldown switched from raw dict access to `rate_limiter.wait_for(f"browser:{domain}", delay=5.0)`

---

## 4. Dead Timeout Parameters

**Problem**: `fetch_direct(url, timeout=30.0)` / `fetch_archive(url, timeout=30.0)` / `fetch_google_cache(url, timeout=30.0)` 
all accepted a `timeout` parameter that was **never wired** to the actual HTTP request.
`_make_client()` hardcoded `httpx.Timeout(connect=5, read=15, write=10, pool=5)`.
`batch.py` called these with `settings.direct_timeout` etc. — never took effect.

**Fix**: Removed dead `timeout` parameter from all three functions.
`_make_client()` now accepts optional `httpx.Timeout` arg for future use.

---

## 5. Duplicate Cascade Logic

**Problem**: `batch.py.extract_url()` and `core/fetchers.extract_single()` were two independent
copies of the same cascade engine (~90 lines each), with subtle differences:
- batch.py used `settings.min_content_len_for(profile.domain)`, fetchers used `min_content_len=200`
- batch.py included `total_cost` and `domain` in output; fetchers didn't
- batch.py set `failing |= {"computer_use", "browser"}` but NOT scrapling in `skip_expensive`

**Fix**: `batch.py.extract_url()` now delegates to `fetchers.extract_single()`:
```python
def extract_url(url, rate_limiter, settings, ...):
    from core.fetchers import extract_single as _extract_single
    profile = get_profile(url)
    return _extract_single(
        url=url, rate_limiter=rate_limiter,
        skip_expensive=skip_expensive,
        min_content_len=settings.min_content_len_for(profile.domain),
        ...
    )
```
88 lines of duplicate code removed, 7 unused imports cleaned up from batch.py.

---

## 6. True Coverage Metric (No Exhausted Exclusion)

**Problem**: "Content fill rate 100%" was misleading — `283 rows / 283 rows = 100%`
because the 214 exhausted rows were excluded from denominator.
True coverage was `283 / 497 = 57%`.

**Fix**: `pipeline_check.py` now reports:
- `exhausted=N` — count of rows marked exhausted
- `true_coverage=283/497 (57.1%)` — coverage including exhausted in denominator
- New error code `FETCHER_EXHAUSTED` distinct from `FETCHER_EMPTY_CONTENT`

Rule: **100% fill rate is as suspicious as 0% — always check what's excluded from the denominator.**

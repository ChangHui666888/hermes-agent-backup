# Cascade Engine Production Optimization

> Production-level cascade engine (`core/fetchers.py`) for the news intelligence pipeline.
> Complement to the agent-level fallback strategy in the main SKILL.md.

## Three-layer separation

```
auto-pipeline.py          ← 编排层：查DB → 调子进程 → 写DB → 记日志
  └── subprocess(batch.py) ← 调度层：CLI params → ThreadPoolExecutor → JSONL
       └── extract_single() ← 级联引擎 core/fetchers.py
            ├── fetch_direct()       httpx, SOCKS5 proxy, http2=False
            ├── fetch_archive()      web.archive.org
            ├── fetch_google_cache() webcache.googleusercontent.com
            ├── fetch_scrapling()    TLS fingerprinting (deprecated, hangs)
            ├── fetch_browser()      Playwright via BrowserPool singleton
            ├── fetch_jina_reader()  r.jina.ai via curl -4
            ├── fetch_tavily()       api.tavily.com via curl -4
            └── fetch_searxng_alt()  SearXNG → alternate source
```

**Golden rule**: auto-pipeline.py must NEVER contain HTTP requests to target sites.
Only `httpx.post` to `CLOUD_API` (own cloud service) is allowed.

## Structural invariants

1. **try/except blocks are per-step**: Step 3 and Step 3.5 must be separate `try` blocks.
2. **intel_id is carried at query time**: Step 3's candidate SELECT includes `ni.id`.
3. **Empty JSONL is handled**: `if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0`.
4. **Temp files use NamedTemporaryFile**: Not hardcoded paths.

## httpx 0.28 + Windows + Proxy: The SSL Hang

### Symptom
```
ConnectTimeout: _ssl.c:989: The handshake operation timed out
```

### Root cause
httpx 0.28 defaults to `http2=True`. On Windows, HTTP CONNECT proxy combined with HTTP/2 causes intermittent SSL handshake failures.

### Fixes

**Primary**: `http2=False` in `_make_client()`

**Secondary**: SOCKS5 proxy instead of HTTP CONNECT env var:
```python
proxy = "socks5://127.0.0.1:10808"
```
Do NOT use `HTTPS_PROXY` env var (it's `http://127.0.0.1:10808` which causes SSL issues).

**Tertiary**: Aggressive per-request timeouts (`connect=5, read=15`).

## BrowserPool Singleton

```python
class BrowserPool:
    _instance = None
    _launch_count = 0  # class-level stats
    _crash_count = 0

    @classmethod
    def get_browser(cls):
        # lazy init singleton, auto-rebuild on crash
```

- Avoids 3-5s browser launch per call
- `_ensure_browser()` checks `is_connected()` before returning
- Crash detected in except block → `_crash_count++` → re-launch
- `atexit.register(BrowserPool.close_all)` for clean shutdown

## Cascade Timeout (Soft Deadline)

```python
def extract_single(..., cascade_timeout=90.0):
    deadline = time.monotonic() + cascade_timeout
    for strategy in order:
        if time.monotonic() >= deadline:
            # Soft cutoff: checked BETWEEN strategies, not mid-strategy
            # Actual time may exceed cascade_timeout by longest strategy's
            # own timeout (~30s max)
            break
```

- Prevents one URL from occupying a worker indefinitely
- Partial content preserved if already obtained
- Cost trace includes `cascade_timeout` marker

## Process Lock

### Problem: Windows os.kill(pid,0) raises WinError 87 for alive processes

POSIX signal 0 is not supported on Windows.

### Fix: Timestamp-based lock

```python
LOCK_FILE = ".pipeline.lock"
BATCH_TIMEOUT = 600

def acquire_lock():
    try:
        fd = os.open(LOCK_FILE, O_CREAT|O_EXCL|O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd); return True
    except FileExistsError:
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age < BATCH_TIMEOUT:
            return False  # active lock
        os.remove(LOCK_FILE)
        return acquire_lock()  # expired, retry
```

## Jina Reader: IPv6 + SNI Workaround

`r.jina.ai` has IPv6 unreachable. httpx with raw IP has SNI issues.

Fix: `curl -4` subprocess (handles both IPv4 forcing and SNI correctly).

## Domain Profile Patterns

### Current production profiles (as of 2026-07-28)

| Domain | Strategy Order | known_failing | Notes |
|--------|---------------|---------------|-------|
| bloomberg.com | archive→google_cache→jina→tavily→search | direct, scrapling, browser | DataDome, browser 30s too short |
| reuters.com | archive→google_cache→jina→tavily→search | scrapling, browser | Target crashed |
| marketwatch.com | direct→archive→google_cache→jina→tavily→search | scrapling, browser | All local fail, only Jina/Tavily work |
| bbc.co.uk | direct→jina→tavily→search | scrapling, browser | Scrapling hangs 60s |
| **investing.com** | **browser→jina→tavily→search** | **scrapling, direct, google_cache, archive** | Cloudflare, browser ~50% success |
| **seekingalpha.com** | **browser→jina→tavily→search** | **scrapling, direct, google_cache, archive** | Same as investing.com |
| **investors.com** | **browser→jina→tavily→search** | **scrapling, direct, google_cache, archive** | Same pattern |
| dw.com | direct→archive→google_cache→search | scrapling, browser | Friendly direct |
| ft.com | browser→archive→google_cache→search | scrapling | Paywall, browser works |

### Cloudflare unified pattern (2026-07-29)

For sites protected by Cloudflare where `direct/google_cache/archive` ALL return 403/429/404:
```python
strategy_order = ["browser", "jina", "tavily", "search_snippet"]
known_failing = ["scrapling", "direct", "google_cache", "archive"]
```
Browser may succeed (~50%). When it fails, jina/tavily provide 10-20s fast fallback instead of wasting 45s on three known-dead strategies.

### DEFAULT_STRATEGY_ORDER (no scrapling/browser)

```python
DEFAULT_STRATEGY_ORDER = [
    "direct", "archive", "google_cache",
    "jina", "tavily", "search_snippet",
]
```
scrapling and browser removed from default. scrapling hangs 60s; browser detected by most sites.
Specific domains can opt in via their own profile.

## Strategy Effectiveness

| Strategy | Count | Avg chars | Useful % |
|----------|-------|-----------|----------|
| direct | 106 | 4,940 | 100% |
| searxng_alt | 15 | 4,163 | 100% |
| archive | 3 | 910 | 100% |
| rss_fulltext | 357 | 283 | 100% |
| tavily | 3 | 260 | 100% |
| jina | varies | 265-753 | 100% |

## Concurrency Tuning Results (2026-07-28)

Test methodology: extract from DB, mix of easy+hard URLs, 2 rounds each phase.

| Phase | Workers | LIMIT | R1 | R2 | Verdict |
|-------|---------|-------|----|----|---------|
| 1 | 2 | 5 | 63s | — | < 180s ✅ |
| 2 | 3 | 5 | 94s | 62s | < 120s ✅ |
| 3 | 3 | 8 | ~60s | 7/0 | < 240s ✅ |

Decision tree used: Phase increment only if current phase passes both rounds.
Final params: `max-workers=3, LIMIT=8`.

## Testing a Single URL

```bash
python batch.py --urls SINGLE_URL.txt --out result.jsonl --rate-delay 0 --verbose
# Check cost_trace for cascade path
```

## Checking Failed URL Patterns from Logs

Pipeline Step 3 now outputs:

```
❌ [search_snippet] 返回 None  chain=browser→direct→google_cache→archive→search_snippet
```

If the same failing chain appears for multiple URLs from the same domain:
→ Add that domain to `domain_profiles.py` with those strategies in `known_failing`.

## Clean Architecture: Recovery as Cascade Strategy

**Before**: auto-pipeline.py Step 3.5 had inline httpx calls (SearXNG, Tavily) + bare credential.

**After**: All HTTP calls in `core/fetchers.py`. Step 3.5 = pure orchestration via `batch.py --force-strategy`.

Verification:
```bash
grep -n "httpx\." auto-pipeline.py | grep -v "CLOUD_API"
# Should return nothing (or only cloud API calls)
```

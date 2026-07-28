# Cascade Engine Production Optimization

> Production-level cascade engine (`core/fetchers.py`) for the news intelligence pipeline.
> Complement to the agent-level fallback strategy in the main SKILL.md.

## Architecture Boundary

```
auto-pipeline.py          ← 编排层：查DB → 调子进程 → 写DB → 记日志
  └── subprocess(batch.py) ← 调度层：CLI params → ThreadPoolExecutor → JSONL
       └── extract_single() ← 级联引擎 core/fetchers.py
            ├── fetch_direct()       httpx, SOCKS5 proxy
            ├── fetch_archive()      web.archive.org
            ├── fetch_google_cache() webcache.googleusercontent.com
            ├── fetch_scrapling()    TLS fingerprinting
            ├── fetch_browser()      Playwright (30s timeout, resource blocking)
            ├── fetch_jina_reader()  r.jina.ai via curl -4
            ├── fetch_tavily()       api.tavily.com via curl -4
            └── fetch_searxng_alt()  SearXNG → alternate source
```

**Golden rule**: auto-pipeline.py must NEVER contain HTTP requests to target sites.
Only `httpx.post` to `CLOUD_API` (own cloud service) is allowed in the orchestration layer.

## httpx 0.28 + Windows + Proxy: The SSL Hang

### Symptom
```log
ConnectTimeout: _ssl.c:989: The handshake operation timed out
```
Intermittent — same URL sometimes works, sometimes hangs.

### Root cause
httpx 0.28 defaults to `http2=True`. On Windows, HTTP CONNECT proxy (`http://127.0.0.1:10808`) combined with HTTP/2 causes intermittent SSL handshake failures in `httpcore`. The proxy (Clash/V2Ray) handles HTTP/2 CONNECT poorly on Windows.

### Fixes applied

**Primary fix**: `http2=False` in `_make_client()`
```python
kwargs = {"http2": False, ...}
```
This is the single most impactful change. Eliminated all SSL timeouts.

**Secondary fix**: SOCKS5 proxy instead of HTTP CONNECT
```python
proxy = "socks5://127.0.0.1:10808"
```
SOCKS5 is more compatible with httpx than HTTP CONNECT on this network.
Env var `SOCKS5_PROXY` overrides this. Do NOT fall back to `HTTPS_PROXY` — it's `http://127.0.0.1:10808` which causes the SSL issue.

**Tertiary fix**: Aggressive per-request timeouts
```python
timeout = httpx.Timeout(connect=5, read=15, write=10, pool=5)
```
Fast fail — don't wait 30s for a blocked connection.

### Verification
```bash
# Before: hangs
python -c "import httpx; httpx.Client(http2=True).get('https://www.bbc.com')"
# After: OK
python -c "import httpx; httpx.Client(http2=False).get('https://www.bbc.com')"
```

## Jina Reader: Overcoming IPv6 + SNI Issues

`r.jina.ai` resolves to both IPv4 (`154.83.14.134`) and IPv6 (`2a03:2880:...`).
IPv6 is unreachable from this network. httpx with raw IP + Host header has SNI issues.

### Fix: Use `curl -4` via subprocess
```python
subprocess.run(["curl", "-4", "-s", "--max-time", "10", reader_url], ...)
```
`curl -4` forces IPv4 and handles SNI correctly.
Timeout: 10s (fast fail if unreachable).

### Alternative: Tavily for search-based fallback
Same `curl -4` approach. Tavily returns AI-generated summaries (100-500 chars).
Key: `tvly-dev-*` — free dev key, works well.

## Process Lock: Prevent Concurrent Pipeline Instances

### Problem
Multiple `auto-pipeline.py` instances running simultaneously, overwriting each other's temp files and DB connections.

### Solution: File-based lock with PID validation
```python
LOCK_FILE = ".pipeline.lock"

def acquire_lock():
    # O_EXCL atomic create + PID write
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True
    # On FileExistsError: check PID, clean up if dead, retry

atexit.register(release_lock)
```

**Windows caveat**: `atexit` doesn't fire when killed by `timeout` command or SIGKILL.
PID validation in `acquire_lock()` handles orphaned locks from dead processes.

## Strategy Effectiveness vs Content Quality

### DB Query Pattern
```sql
SELECT nc.fetch_strategy, COUNT(*),
       SUM(CASE WHEN length(nc.content_md) >= 2000 THEN 1 ELSE 0 END) as good
FROM news_content nc
GROUP BY nc.fetch_strategy;
```

### Measured effectiveness (from production DB)

| Strategy | Avg chars | Usefulness | Notes |
|----------|-----------|------------|-------|
| `direct` | 4,940 | 100% | Full article body |
| `searxng_alt` | 4,163 | 100% | Alternate source recovery |
| `archive` | 910 | 100% | Wayback Machine snapshots |
| `rss_fulltext` | 283 | 100% | Zero-cost RSS descriptions |
| `tavily` | 260 | 100% | AI search summary |
| `jina` | 265-753 | 100% | Third-party reader API |

## Domain Profile Patterns

### Hard targets (anti-bot / paywall)

```python
"reuters.com": strategy_order=["archive", "google_cache", "jina", "tavily"]
"marketwatch.com": strategy_order=["direct", "archive", "google_cache", "jina", "tavily"]
"bloomberg.com": strategy_order=["browser", "archive", "google_cache"]
```

**Bloomberg**: Playwright browser CAN bypass (DataDome detection evaded with resource blocking + WebGL spoofing).
**Reuters**: Playwright `Target crashed` — site detects headless browser aggressively. Browser strategy in `known_failing`.
**MarketWatch**: All local strategies fail. Only Jina/Tavily provide any content.

### Strategy removal pattern
When a strategy is proven to fail for a domain, add it to `known_failing`:
```python
known_failing=["scrapling", "browser"]  # Skip these entirely
```
This prevents wasting 30-60s per URL on strategies known to fail.

## Clean Architecture: Recovery as Cascade Strategy

### Before (violation)
`auto-pipeline.py` Step 3.5 contained:
- Inline `httpx.get("http://searxng:8080/search")` — HTTP request in orchestration
- Inline `httpx.post("https://api.tavily.com/search")` — duplicated the already-broken httpx pattern
- `from core.fetchers import _extract_main_text` — extraction logic in orchestration
- Hardcoded Tavily API key — credential in wrong layer

### After (fixed)
1. `fetch_searxng_alt()` and `fetch_tavily(title=...)` in `core/fetchers.py`
2. `batch.py` gets `--force-strategy` and `url\ttitle` support
3. `auto-pipeline.py` Step 3.5: pure orchestration — query candidates → write temp file → subprocess(batch.py) → parse JSONL → write DB → log

### Verifying the boundary
```bash
# auto-pipeline.py should have ZERO httpx.get/post (except CLOUD_API)
grep -n "httpx\.\(get\|post\)" auto-pipeline.py | grep -v "CLOUD_API\|100.107.117.23"

# core/fetchers.py is WHERE all HTTP calls belong
grep -c "httpx\.\(get\|post\)\|curl -4" core/fetchers.py
```

---
name: python-network-troubleshooting
description: "Debug Python network code: concurrent global state races, SOCKS/proxy integration, HTTP client selection (urllib/httpx), RSS/feed parsing failures."
version: 1.0.0
author: agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [debugging, python, networking, concurrency, socks, proxy, http-clients, rss]
  related_skills: [systematic-debugging, scrapling]
---

# Python Network Troubleshooting

## When to Use

When Python network code has:
- Non-deterministic failures that come and go
- ThreadPoolExecutor + socket/global state issues
- SOCKS5 proxy integration problems
- RSS/feed fetching failures (intermittent or consistent)
- HTTP client library selection decisions
- Reverse proxy/Web UI binding configuration

## Core Pattern: Global State in Concurrent Contexts

**Symptom:** A network function works in isolation but fails non-deterministically under `ThreadPoolExecutor` — different endpoints fail on each run with no code change.

**Root Cause:** Python module-level state (`socket.socket`, `os.environ`, module-level caches) is **process-global, not thread-local**. When one thread modifies it and another thread reads it simultaneously, the second thread sees the wrong value.

**The Classic Example: `socket.socket = socks.socksocket`**

```python
def fetch_feed(url):
    if needs_proxy(url):
        sock.set_default_proxy(socks.SOCKS5, HOST, PORT)
        socket.socket = socks.socksocket  # ← process-global!
        resp = urllib.request.urlopen(url)  # uses patched socket
        socket.socket = socket._socket
    else:
        resp = urllib.request.urlopen(url)  # expects REAL socket
```

Thread A sets `socket.socket → SOCKS` → Thread B reads `socket.socket` (now SOCKS) → B's non-proxy request fails routing through SOCKS.

### Diagnostic

| Test | Result if Global-State Race |
|------|-----------------------------|
| `max_workers=1` (serial) | All failures disappear |
| `max_workers=N` (parallel) | Random different failures each run |
| Log thread ID at entry/exit | Multiple threads in mutation section simultaneously |

### Fixes (preference order)

| Fix | Approach | Tradeoff |
|-----|----------|----------|
| **Use library with native proxy support** | httpx: `Client(proxy=httpx.Proxy(url="socks5://..."))` — no global patching | Need `httpx[socks]` extras |
| **threading.Lock** | Wrap mutation in `with lock:` | Serializes patching section |
| **Sequential fetch** | No ThreadPoolExecutor | Slow for many endpoints |
| **Per-thread state** | `threading.local()` + store original in thread-local | More complex |

## httpx 0.28 on Windows: http2=False Fix

**Critical finding for Windows + proxy environments.**

### Symptom
httpx requests to HTTPS URLs intermittently fail with:
```
ConnectTimeout: _ssl.c:989: The handshake operation timed out
```
The same URL works 50-70% of the time, fails the rest — no pattern, no code change.

### Root Cause
httpx 0.28+ defaults `http2=True` (HTTP/2 enabled). On Windows, when routing through an HTTP CONNECT proxy (`http://127.0.0.1:10808`), the HTTP/2 connection initialization causes intermittent SSL handshake failures. Testing confirmed:
- `http2=True` + HTTP CONNECT proxy → **intermittent** SSL timeout
- `http2=True` + SOCKS5 proxy → **works** (no SSL timeout)
- `http2=False` + any proxy → **works** (no SSL timeout)

### Fix

```python
# In _make_client() or wherever httpx clients are created:
client = httpx.Client(
    http2=False,  # ← critical: disable HTTP/2 on Windows + proxy
    proxy=proxy_url,
    timeout=httpx.Timeout(connect=5, read=15, write=10, pool=5),
)
```

### When to Keep http2=True
- Linux/macOS (not affected by this bug)
- Direct connections (no proxy) or SOCKS5 proxy
- When you explicitly need HTTP/2 multiplexing

### Diagnostic
```bash
# Run 10x to verify stability:
for i in {1..10}; do python -c "import httpx; httpx.Client(proxy='http://127.0.0.1:10808', http2=False, timeout=8).get('https://www.bbc.com')" || echo "FAIL $i"; done
```

## SOCKS5 vs HTTP CONNECT Proxy for httpx

| Aspect | SOCKS5 | HTTP CONNECT |
|--------|--------|-------------|
| SOCKS5 | ✅ **Stable** | ❌ Intermittent SSL hangs |
| Chinese domains | ✅ Route around GFW | ✅ Same |
| Configuration | `proxy="socks5://127.0.0.1:10808"` | `proxy="http://127.0.0.1:10808"` |
| Env var | `SOCKS5_PROXY` | `HTTPS_PROXY` / `HTTP_PROXY` |

On Windows with Clash/V2Ray:
- The mixed port (e.g. `127.0.0.1:10808`) typically serves both HTTP and SOCKS5
- **Always prefer SOCKS5** for httpx on Windows — it avoids the HTTP/2 SSL handshake issue completely
- **Set a separate env var**: `SOCKS5_PROXY=socks5://127.0.0.1:10808` instead of reusing `HTTPS_PROXY`. This prevents breaking curl and other tools that expect HTTP proxy URLs
- **Validation**: `curl -x socks5://127.0.0.1:10808 -s -o /dev/null -w "%{http_code}" --max-time 10 https://www.bbc.com`

### curl -4 for IPv6-Blocked Sites

Some CDN-hosted APIs (e.g. Jina Reader `r.jina.ai`) resolve to IPv6 addresses that are unreachable from certain networks. When they also have working IPv4:

```bash
# Test: compare IPv4 vs default
curl -4 -s --max-time 10 https://r.jina.ai/https://www.bbc.com/news
curl -6 -s --max-time 10 https://r.jina.ai/https://www.bbc.com/news  # likely fails
```

**Fix in Python via subprocess + curl -4**:
```python
import subprocess
result = subprocess.run(
    ["curl", "-4", "-s", "--max-time", "10", api_url,
     "-H", "Accept: text/plain"],
    capture_output=True, text=True, timeout=12)
```

**Why not httpx with IPv4 address directly?** httpx sets TLS SNI from the URL hostname. When you replace the hostname with a raw IP, the SNI doesn't match, causing SSL errors. curl handles this correctly with `-4` flag.


## Network Cascade Engine Debugging

When a fetch system uses a cascade of strategies (direct → archive → scrapling → browser → search_snippet) with timeouts, failures compound.

### Symptoms of Cascade Overshoot
- A single run takes 10+ minutes
- Most URLs fail with `none:0/N` strategy
- Pipeline log shows near-identical timing per batch regardless of URLs fetched
- Strategy `none` means no strategy returned content — but no per-strategy error logged

### Diagnostic
```python
# Check cost_trace per URL — every strategy's outcome and duration:
result = extract_single(url, rate_limiter)
if not result["ok"]:
    for trace in result.get("cost_trace", []):
        print(f"  {trace['strategy']}: {'OK' if trace['ok'] else 'FAIL'} "
              f"({trace.get('error','')}) cost={trace.get('cost','?')}")
```

### Fixes (preference order)

1. **Reduce batch size** — Don't fetch 50 URLs per batch. 5-10 is more reliable. Each failed URL cascades through all strategies at 15-45s each. With 50 URLs × 30s average fail = 1500s = 25 minutes. With 5 URLs = 150s = manageable.

2. **Add per-strategy hard timeout** — Don't rely on client-level timeout alone. Wrap each strategy call:
   ```python
   with concurrent.futures.ThreadPoolExecutor(1) as ex:
       future = ex.submit(fetch_fn, url, rate_limiter)
       result = future.result(timeout=20)  # per-strategy hard limit
   ```

3. **Log strategy failure reasons** — Each failed strategy should record WHY it failed (timeout vs HTTP status vs empty response):
   ```python
   {strategy: {"ok": false, "error": "ConnectTimeout: 15s", "status_code": null}}
   ```

4. **Use known_failing from domain profiles** — `core/fetchers.py` already has `known_failing` per domain. Ensure browser strategy is excluded when Playwright is not installed or when sites actively kill headless browsers (e.g. Reuters `Target crashed`).

5. **Tune per-strategy timeouts** — Defaults can be too generous:
   ```python
   direct_timeout: float = 15.0   # not 30
   archive_timeout: float = 15.0  # not 30
   scrapling_timeout: float = 20.0  # not 45
   browser_timeout: float = 30.0    # not 60
   ```

### Domain Profile Management

For cascade engines with per-domain strategy profiles:

**Pattern**: `config/domain_profiles.py` maps `domain_in_url → DomainProfile(strategy_order, known_failing)`.

**Critical Python trap**: Duplicate dict keys override silently. If the same domain key appears twice in `KNOWN_PROFILES`:
```python
KNOWN_PROFILES = {
    "reuters.com": DomainProfile(strategy_order=["browser", "archive"]),
    ...
    "reuters.com": DomainProfile(strategy_order=["direct"]),  # ← wins at runtime
}
```
The second occurrence **overwrites** the first when the dict literal is evaluated. Always search for duplicates after adding/modifying:
```bash
grep -n '"domain.com"' config/domain_profiles.py
```

**Testing**: Verify profile loading in a fresh Python process (not a cached import):
```bash
python -c "
import sys; sys.path.insert(0, '.')
from config.domain_profiles import get_profile
p = get_profile('https://www.example.com/article')
print(p.strategy_order)
"
```

**Known failing for anti-bot sites**: When sites detect and kill headless Playwright:
- Bloomberg: ✅ browser works (anti-detection successful)
- Reuters: ❌ `Target crashed` (browser process killed)
- MarketWatch: ❌ returns None (browser detected)
- Add browser to `known_failing` for sites where it fails to skip it and save 45-60s per URL.

### Browser Strategy Pitfalls

Playwright browser strategy (cost=3) is the most powerful but most fragile strategy:

| Site | Browser Result | Fallback |
|------|---------------|----------|
| Bloomberg | ✅ OK (706+ chars) | archive.org |
| WSJ / FT | ✅ Expected (not tested) | archive.org |
| Reuters | ❌ **Target crashed** (browser process killed by anti-detection) | archive.org (old snapshots only) |
| MarketWatch | ❌ None (browser detected) | **No local strategy works** — RSS FullText or Jina Reader/Tavily API needed |

**Lessons**:
- Always test browser on a representative URL before declaring it as default strategy
- Sites that serve via JavaScript SPA need `wait_until='networkidle'` but that adds 30s+ load time
- Some sites detect `navigator.webdriver` override and kill the page via setTimeout or `Target crashed` (Reuters)
- The `page.add_init_script()` anti-detection hooks work on most sites but not all
- If browser fails, mark it in `known_failing` to skip it in future runs

### Playwright Stealth Enhancements

When `fetch_browser` fails (Target crashed, None), try these upgrades:

1. **Block resource-heavy requests** — blocks images/fonts/CSS/media/trackers, reduces detection surface 3-5x:
   ```python
   async def _block_route(route):
       rtype = route.request.resource_type
       if rtype in ('image', 'font', 'media', 'stylesheet'):
           await route.abort()
       else:
           await route.continue_()
   page.route("**/*", _block_route)
   ```

2. **WebGL vendor/renderer spoofing** — prevents WebGL fingerprinting:
   ```js
   const getParameter = WebGLRenderingContext.prototype.getParameter;
   WebGLRenderingContext.prototype.getParameter = function(p) {
       if (p === 37445) return 'Intel Inc.';
       if (p === 37446) return 'Intel Iris OpenGL Engine';
       return getParameter(p);
   };
   ```

3. **Modern Chrome UA** — Use Chrome 131+ UA, not 124:
   ```
   Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36
   ```

4. **Reduce timeout to 30s** — Default 60s is too generous when detection is likely:
   ```python
   def fetch_browser(url, rate_limiter=None, timeout=30.0):
   ```

5. **Use wait_until='commit'** — Fastest load strategy, then wait for content selectors. Avoid `networkidle` unless the page is a SPA that requires full JS render.

6. **Always close browser** — Use `browser.close()` in a finally block, or wrap in a context manager to prevent Playwright process leaks.

## Third-Party API Fallbacks (Jina Reader, Tavily)

When all local cascade strategies fail, two free third-party APIs can serve as ultimate fallbacks:

### Jina Reader (`r.jina.ai`)
- **Strengths**: Built-in anti-bot bypass; works where Playwright fails
- **Unsupported on this network**: `r.jina.ai` resolves to IPv6; use `curl -4` to force IPv4
- **Cost**: Free

### Tavily Search API
- **Strengths**: Search-powered AI summary; works even when URL access fails
- **Cost**: Free dev key (`tvly-dev-*`)
- **Key pattern**: Extract keywords from URL path as search query, returns `answer` field

### Integration Pattern
```python
# Jina Reader — curl -4 bypasses IPv6 + httpx SNI issues
result = subprocess.run(["curl", "-4", "-s", "--max-time", "10",
    f"https://r.jina.ai/{target_url}", "-H", "Accept: text/plain"],
    capture_output=True, text=True)

# Tavily — also curl -4
payload = json.dumps({"api_key": TAVILY_KEY, "query": query,
    "search_depth": "basic", "include_answer": True})
result = subprocess.run(["curl", "-4", "-s", "--max-time", "10",
    "https://api.tavily.com/search", "-H", "Content-Type: application/json",
    "-d", payload], capture_output=True, text=True)
```


## HTTP Client Library Selection

| Aspect | `urllib.request` | `httpx` |
|--------|-----------------|---------|
| Connection pooling | No (per-request TCP) | Yes (keepalive pool) |
| HTTP/2 | No | Yes |
| Native SOCKS5 | No (needs PySocks + socket patch) | Yes (`proxy=httpx.Proxy(...)`, needs `httpx[socks]`) |
| Concurrency safety | Socket patch is process-global ❌ | Per-client connections ✅ |
| Parsing | Manual (`ElementTree`) | -- (use with feedparser) |
| Best for | Simple single requests | Production concurrent fetching |

**Decision rule:** If you have >10 concurrent network requests, especially over SOCKS, use `httpx`. If a single request, `urllib` is fine.

## SOCKS5 Integration Quick Reference

### urllib + PySocks (thread-safe version)
```python
import socks, socket, threading
_socks_lock = threading.Lock()

def proxied_request(url):
    with _socks_lock:
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
        socket.socket = socks.socksocket
        try:
            return urllib.request.urlopen(url, timeout=10).read()
        finally:
            socket.socket = socket._socket
```

### httpx (native, thread-safe)
```python
import httpx
client = httpx.Client(
    proxy=httpx.Proxy(url="socks5://127.0.0.1:10808"),
    http2=True,
    timeout=httpx.Timeout(10)
)
response = client.get(url)
```

### Version Compatibility
- httpx 0.27.x and earlier: `proxies="socks5://..."` (dict/string)
- **httpx 0.28.x**: `proxy=httpx.Proxy(url="socks5://...")` (object, singular)
- Check version: `python -c "import httpx; print(httpx.__version__)"`

## RSS Feed Troubleshooting

### Common Failure Modes

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `SSL: EOF` / `SSL: UNEXPECTED_EOF` | Cloudflare/WAF blocking scraper | Switch to browser-based scraper (Scrapling skill) or use different user-agent |
| `HTTP 403` | WAF/Cloudflare block | Same as above, or use rotating IPs |
| `HTTP 404` | Feed URL moved or decommissioned | Find new URL or remove |
| `HTTP 429` | Rate limited | Add per-domain RPM limiting (rate_limiter.py) |
| Timeout >10s | Slow server or geo-distance | Increase timeout, check proxy latency |
| Parse error | Non-standard XML/HTML feed | Use feedparser (tolerant) instead of ElementTree |

### Incremental Fetch Optimization

Track `last_seen` URL per feed. When parsing, break on encountering the last seen link — everything after it is old.

```python
last_seen = state.get(feed_name, {}).get("last_seen")
for entry in feed_entries:
    if last_seen and entry.link == last_seen:
        break  # remaining entries are old
    # process new entry...
```

### Dead Feed Quarantine (3-strike rule)

```python
failures = state.get(feed_name, {}).get("fail", 0)
if failures >= 3:
    quarantine_until = now + 86400  # 24h isolation
    skip feed until quarantine ends
```

## RSS Scanner Architecture Decision Tree

```
How many feeds?                    → ≤20: urllib+ThreadPoolExecutor (simple)
What proxy needed?                 → SOCKS5: use httpx (not urllib+socket patch)
                                     Direct: either library works
Parsing tolerance?                 → Need feedparser (handles malformed feeds)
Cron timeout? (e.g. 120s)         → Use concurrent with fast-clients
                                     Or batch+rotate if time-limited
Domestic + international mix?      → Route domestic direct, international via proxy
Want dead-feed isolation?          → Add 3-strike quarantine
```

## Pitfalls

1. **`errors` list vs `feeds_detail`**: In RSS scanners, the `errors` list for the report must be built from the actual per-feed error field, not inferred from status alone. Explicitly include `result.get("error", "")` in detail entries.
2. **Socket restore on exception**: Always use `try/finally` when restoring `socket.socket` — an exception leaves it permanently patched.
3. **httpx proxy parameter name**: httpx 0.28+ uses singular `proxy=`, not plural `proxies=`. Check your version.
4. **feedparser installed check**: Not part of stdlib; needs `pip install feedparser`.
5. **Domestic feeds through proxy**: Chinese sites (人民网, 新华网, etc.) are often faster and more reliable direct. Don't route them through international SOCKS proxies.

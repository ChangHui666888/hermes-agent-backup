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

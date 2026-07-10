# SOCKS5 Proxy Thread-Safety in Concurrent Scrapers

> Reference for `news-resilient-retrieval` skill.
> Documents a critical threading bug when using `PySocks` + `urllib` + `ThreadPoolExecutor`.

## The Problem

In a Python scraper using `ThreadPoolExecutor(max_workers=8)`, each thread that needs a SOCKS5 proxy does:

```python
import socks
import socket
socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
socket.socket = socks.socksocket
resp = urllib.request.urlopen(url, timeout=10)
socket.socket = socket._socket  # restore
```

**This is NOT thread-safe.** `socket.socket` is a *module-level global* in Python's `socket` module. When 8 threads run concurrently:
1. Thread A sets `socket.socket = socks.socksocket` for its proxy request
2. Thread B (which doesn't need proxy) also sets `socket.socket = socks.socksocket` (overwrites)
3. Thread A's `urlopen` may now use the wrong socket type
4. Thread A tries to restore with `socket._socket` — but another thread already changed it again
5. Result: **random feeds fail with various errors** (timeout, connection refused, bad file descriptor, SSL errors) — and the failures change every run

## Symptoms

- Same feed succeeds in one run, fails in the next
- ~35-40% of feeds consistently fail while similar feeds succeed
- Error messages are inconsistent (sometimes timeout, sometimes 403, sometimes SSL EOF)
- Debugging single feeds (sequential) shows them all working fine

## The Fix

### Option A: Serialize (recommended for <100 feeds)

Replace `ThreadPoolExecutor` with a sequential loop. For 50-100 feeds at ~3s each, total time is ~2-5 minutes — acceptable for most cron-based scanners.

```python
for name, url in FEEDS:
    feed_results[name] = fetch_feed(name, url)
```

If the total time exceeds the cron timeout, implement **rotation**:

```python
start_idx = state.get("last_feed_index", 0) % len(FEEDS)
batch = len(FEEDS) // 4 + 1  # scan 1/4 of feeds per run
for i in range(batch):
    idx = (start_idx + i) % len(FEEDS)
    feed_results[name] = fetch_feed(name, url)
state["last_feed_index"] = (start_idx + batch) % len(FEEDS)
```

This ensures 4 runs (e.g. 20 minutes at 5-minute intervals) completes a full scan.

### Option B: Threading.Lock (for <50 proxy feeds)

Wrap the socket-patching section in a threading lock. Domestic feeds (direct connection) can still run in parallel.

```python
SOCKS_LOCK = threading.Lock()

def fetch_feed(name, url):
    if needs_proxy(url):
        with SOCKS_LOCK:
            import socks, socket
            socks.set_default_proxy(socks.SOCKS5, PROXY_HOST, PROXY_PORT)
            socket.socket = socks.socksocket
            try:
                resp = urllib.request.urlopen(url, timeout=10)
            finally:
                socket.socket = socket._socket
    else:
        resp = urllib.request.urlopen(url, timeout=10)
```

**Trade-off**: all proxy feeds become sequential (38 feeds × 3-5s ≈ 2-3 min), but domestic feeds stay parallel.

### Option C: Use `requests` with SOCKS (requires `requests[socks]`)

```python
import requests

session = requests.Session()
session.proxies = {
    "http": "socks5://127.0.0.1:10808",
    "https": "socks5://127.0.0.1:10808",
}
resp = session.get(url, timeout=10)
```

This is thread-safe because `requests` creates a new connection per request, but adds a dependency.

## Root Cause

PySocks MUST patch `socket.socket` globally — there is no per-connection SOCKS override in Python's `urllib`. This is a fundamental limitation of the `urllib` + `PySocks` combination. Any concurrent use of this pattern will have this race condition.

## Test Pattern for Isolating Feed Failures

To distinguish "feed is truly dead" from "feed failed due to threading race", test single feeds sequentially outside the scanner:

```python
import socks, socket, urllib.request

socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
socket.socket = socks.socksocket

for name, url in test_feeds:
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        print(f"  ✅ {name}: {len(resp.read())}B")
    except Exception as e:
        print(f"  ❌ {name}: {str(e)[:80]}")
    socket.socket = socket._socket
```

If a feed works sequentially but fails in the concurrent scanner, it's a threading issue, not a dead feed.

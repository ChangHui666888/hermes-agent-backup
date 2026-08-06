# Domain Profiles (DomainProfile)

## Purpose

Avoid running the same cascade strategy order for every domain. Anti-bot sites like Bloomberg need a different strategy chain than friendly sites like BBC.

## Known Profiles

| Domain | Strategy Order | Known Failing | Notes |
|--------|---------------|---------------|-------|
| `bloomberg.com` | archive → google_cache → jina → tavily → search_snippet | direct, scrapling, browser | DataDome, browser 30s timeout not enough |
| `reuters.com` | archive → google_cache → jina → tavily → search_snippet | scrapling, browser | DataDome paywall, direct 401 |
| `marketwatch.com` | direct → archive → google_cache → jina → tavily → search_snippet | scrapling, browser | DataDome, all strategies often fail |
| `wsj.com` | browser → archive → google_cache → search_snippet | scrapling | DataDome, browser needed |
| `ft.com` | browser → archive → google_cache → search_snippet | scrapling | Paywall, browser needed |
| `bbc.co.uk` | direct → jina → tavily → search_snippet | scrapling, browser | direct sometimes SSL timeout, skip scrapling/browser |
| `dw.com` | direct → archive → google_cache → search_snippet | scrapling, browser | Direct-friendly, no special anti-bot |
| `investing.com` | browser → direct → google_cache → archive → search_snippet | scrapling | Cloudflare, browser required |
| `seekingalpha.com` | direct → google_cache → archive → search_snippet | scrapling, browser | Cloudflare, most strategies fail |
| `cnbc.com` | direct → scrapling → archive → search_snippet | — | Cloudflare, scrapling works |
| `investors.com` | direct → google_cache → archive → search_snippet | scrapling, browser | Headless detected |

## Default (Unknown Domains)

```
direct → archive → google_cache → jina → tavily → search_snippet
```

No scrapling or browser in default (they hang/are detected on most sites).

## Windows Process Lock

The `acquire_lock()` function uses file mtime + BATCH_TIMEOUT instead of os.kill(pid,0):

```python
mtime = os.path.getmtime(LOCK_FILE)
age = time.time() - mtime
if age < BATCH_TIMEOUT:
    log(f"[SKIP] pipeline running ({age:.0f}s ago), skipping")
    return False
# stale lock → clean up and retry
os.remove(LOCK_FILE)
return acquire_lock()
```

This avoids WinError 87 (os.kill with signal 0 is not supported on Windows).

## BrowserPool Singleton

```python
class BrowserPool:
    _instance = None
    _launch_count = 0
    _crash_count = 0
    
    @classmethod
    def get_browser(cls):
        # First call launches; subsequent calls reuse
        # Crashes auto-detect and re-launch
```

Key benefit: avoids 3-5s sync_playwright() → launch → close per URL.

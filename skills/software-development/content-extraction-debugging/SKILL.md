---
name: content-extraction-debugging
description: Debug and optimize web content extraction pipelines — cascade engines, proxy networking, Playwright anti-detection, domain profiling, and testing methodology.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [web-scraping, debugging, cascade, proxy, playwright, anti-bot, pipeline]
    related_skills: [systematic-debugging, scrapling, news-resilient-retrieval]
---

# Content Extraction Pipeline Debugging

## When to Use

- Full-text extraction from news/media sites is failing, timing out, or returning empty
- A cascade engine (direct → archive → scrapling → browser → ...) has low success rates
- httpx requests hang or SSL-handshake times out intermittently
- Playwright/headless browser gets detected, crashes, or `Target crashed`
- A specific domain needs a custom strategy profile (anti-bot type, paywall, strategy order)
- You need to distinguish network/proxy issues from site-level blocking (401/403) from content extraction bugs

## Core Architecture: Cascade Engine

Content extraction pipelines typically use a **cascade (fallback chain)** with cost tiers:

```
┌─ Strategy 1 (cost=1) ─── direct HTTP GET → success? → done
├─ Strategy 2 (cost=1) ─── archive.org     → success? → done
├─ Strategy 3 (cost=2) ─── scrapling/StealthyFetcher → success? → done
├─ Strategy 4 (cost=2) ─── Jina Reader API → success? → done
├─ Strategy 5 (cost=3) ─── Playwright browser → success? → done
├─ Strategy 6 (cost=3) ─── Tavily search API → success? → done
├─ Strategy 7 (cost=5) ─── computer_use    → success? → done
└─ Final fallback ───────── search_snippet  → done (low quality)
```

Each strategy has a timeout. If it fails (returns None or content < min_content_len), the next strategy runs.

### Architecture Principle: Single URL > Batch > Pipeline

**This is the foundational design principle, not a performance optimization.**

```
Single URL Engine (extract_single)
    ↓
Batch Scheduler (batch_extract)
    ↓
Pipeline Orchestrator (auto-pipeline)
```

Rules:
1. **Single URL is the only source of truth.** All entry points (RSS, Recovery, API, CLI, batch) call `extract_single()`. Bare HTTP requests outside `extract_single` are forbidden.
2. **Batch is stateless.** It only schedules URLs and collects results. No retry logic, no strategy decisions, no browser management.
3. **Pipeline handles orchestration only.** It queries the DB, feeds URLs to Batch, and writes results back. No network calls to external sites — only to your own cloud API.
4. **One URL cannot block another.** Each URL runs in its own `future.result(timeout=120)`. Cascade timeout (`cascade_timeout=90s`) prevents a single URL from consuming the entire batch budget.

**Violations to watch for:**
- Batch or Pipeline code making bare HTTP requests (httpx.get/post to external sites)
- Recovery logic running outside the cascade engine
- A single URL's cascade consuming more than 90s total

## Phase 1: Diagnostic Checklist

### 1.1 Check the Pipeline Log

Before touching code, look at the pipeline log for:
```bash
grep -E "FETCH|RSS_FULLTEXT|RECOVERY|FAILED|timeout|ConnectTimeout" pipeline.log | tail -30
```

Key patterns:
- **`direct: N/N`** → only direct succeeded. Archive/scrapling/browser never tried.
- **`ConnectTimeout: _ssl.c:989`** → httpx SSL handshake issue (see §2.1)
- **`Target crashed`** → Playwright detected and killed by anti-bot (see §3.2)
- **`none:0/49`** → all cascade strategies returned None. Check cost_trace for why.
- **`RSS_FULLTEXT: 148 ok`** → the free (cost=0) RSS description path is working

### 1.2 Check Success Rate Trend

| Pattern | Diagnosis |
|---------|-----------|
| First run 66%, then 10%, then 2% | Easy content consumed, only hard remaining — normal |
| Consistently 0% | Network/proxy broken or all URLs are anti-bot blocked |
| Alternating 0% and 60% | Intermittent infrastructure failure (proxy, httpx) |

### 1.3 Check the Cascade cost_trace

Each failed URL produces a `cost_trace` array showing what each strategy returned:
```python
for t in result.get("cost_trace", []):
    print(f"{t['strategy']}: ok={t.get('ok')} error={t.get('error','')}")
```

## Core Design Principle: Single URL → Batch → Pipeline

Content extraction systems must be optimized **bottom-up**, not top-down:

```
  1. Single URL Engine (extract_single)  ← most important
  2. Batch Scheduler (batch.py)          ← only concurrency + result collection
  3. Pipeline Orchestrator (pipeline)    ← only throughput
```

### Why

- A broken Single URL Engine cannot be fixed by adding more workers or larger batches
- Batch SHOULD NOT know about strategies, retries, or anti-bot bypass — it submits URLs and collects results
- Pipeline SHOULD NOT contain HTTP requests, search API calls, or extraction logic — only orchestration (check DB → call batch → write DB → push to cloud)

### Violations to Avoid

| Violation | Where It Happens | Fix |
|-----------|-----------------|-----|
| Pipeline calls HTTP directly | `news_intel/pipeline.py` SearXNG/Tavily recovery | Replace with `extract_single(force_strategy=...)` |
| Pipeline owns strategy logic | `auto-pipeline.py` Step 3.5 Recovery | Already fixed: calls `batch.py --force-strategy` |
| Batch contains business-domain DB writes | `batch.py` writing to `news_content` | Keep batch.py output-only (JSONL); callers own DB persistence |

### Single URL Engine Pattern

```
extract_single(url, rate_limiter, force_strategy_order, title, cascade_timeout)
  → dict {ok, url, content, strategy_used, cost_trace, ...}
```

Everything — RSS recovery, API calls, manual CLI test, batch processing — calls the same function. Never duplicate fetch logic.

## Phase 2: Common Failure Modes and Fixes

### 2.0 Windows-Specific Process Lock Failure

**Symptom:** `acquire_lock()` crashes with `OSError: [WinError 87] 参数错误` when checking if a lock-holding process is alive.

**Root cause:** `os.kill(pid, 0)` is Unix-specific. On Windows, signal 0 is unsupported — raises `WinError 87` even for **alive** processes. The `except OSError` handler doesn't catch it (it hits `SystemError` first).

**Fix:** Replace PID-based alive-check with **timestamp-based staleness**:

```python
# Before (broken on Windows):
def acquire_lock():
    ...
    os.kill(pid, 0)  # ProcessLookupError on Unix, WinError 87 on Windows
    ...

# After (Windows-compatible):
def acquire_lock():
    ...
    mtime = os.path.getmtime(LOCK_FILE)
    age = time.time() - mtime
    if age < BATCH_TIMEOUT:
        log(f"[SKIP] pipeline running ({age:.0f}s ago)")
        return False
    # stale lock → clean up and retry
    os.remove(LOCK_FILE)
    return acquire_lock()
```

### 2.1 Step 1 (Sync+Score) Subprocess Timeout

**Symptom:** `SYNC+SCORE: FAILED: Command '...news_intel.pipeline --hours 2' timed out after 120 seconds`

**Root cause:** `news_intel.pipeline` includes LLM enhancement steps that call Qwen3 (local model). When Qwen3 is unavailable (LM Studio loaded gemma not qwen), it retries 3+ times accumulating ~121s of timeout — just over the 120s hard limit.

**Fix:** Increase the subprocess timeout:
```python
# auto-pipeline.py
subprocess.run([..., "-m", "news_intel.pipeline", "--hours", "2"],
               timeout=240, ...)  # was 120
```

### 2.2 httpx Proxy/SSL Issues (Most Common on Windows)

**Symptom:** `ConnectTimeout: _ssl.c:989: The handshake operation timed out` intermittently.

**Root cause:** httpx 0.28 on Windows with HTTP CONNECT proxy has intermittent SSL handshake hangs. SOCKS5 proxy works reliably.

**Fix sequence:**
```python
# 1. Disable HTTP/2 (httpx 0.28 defaults to http2=True)
httpx.Client(http2=False, ...)

# 2. Use SOCKS5 instead of HTTP CONNECT proxy
proxy = "socks5://127.0.0.1:10808"  # not http://127.0.0.1:10808

# 3. Set aggressive per-connection timeouts
httpx.Timeout(connect=5, read=15, write=10, pool=5)
```

**Verification:**
```bash
# Test SOCKS5 with httpx
python -c "
import httpx
client = httpx.Client(proxy='socks5://127.0.0.1:10808', timeout=10, http2=False)
r = client.get('https://www.bbc.com')
print(r.status_code, len(r.text))
"
```

### 2.2 Rate Limiter + Connection Pool Wasting Time

**Symptom:** 50 URLs take 600s when each should take <10s.

**Root cause:** Single-threaded executor (`max_workers=1`) with per-domain 1s rate delay, plus each failed URL runs all cascade strategies (165s per URL worst case).

**Fixes:**
```python
# 1. Reduce batch size so timeout is never hit
LIMIT 50 → LIMIT 5  # each batch finishes in 50-90s

# 2. Reduce per-strategy timeouts so failures fail fast
direct_timeout: 15.0    # not 30
scrapling_timeout: 20.0 # not 45
browser_timeout: 30.0   # not 60

# 3. Put known-failing strategies in known_failing to skip them
known_failing=["scrapling", "browser"]  # tested per-domain
```

### 2.3 Python Module Caching (Trap)

**Symptom:** You edit `config/domain_profiles.py` but `get_profile()` still returns old values in a fresh `python batch.py` process.

**Root cause:** Dict key collision — if two entries have the same key, the SECOND one overwrites the first at dict construction time.

**Fix:** 
```bash
grep -n '"domain-name"' config/domain_profiles.py  # check for duplicates
```

**Verification in a fresh process:**
```bash
python -c "
import sys; sys.path.insert(0, '.')
from config.domain_profiles import get_profile
p = get_profile('https://www.example.com/test')
print(p.strategy_order)  # should show your changes
"
```

## Phase 3: Strategy-Specific Debugging

### 3.1 fetch_direct — HTTP/HTTPS

```python
# Test direct fetch in isolation
from core.fetchers import fetch_direct, RateLimiter
text = fetch_direct("https://site.com/article", RateLimiter())
print("Got", len(text) if text else "None", "chars")
```

| Status | Meaning |
|--------|---------|
| HTTP 200 + content | Success |
| HTTP 401/403 | Paywall or IP blocked → need browser strategy |
| HTTP 429 | Rate limited → increase rate delay |
| ConnectTimeout | Proxy issue or site blocking IP range → test with/without proxy |
| 404/410 | Page deleted → try archive.org |

### 3.2 BrowserPool — Singleton Browser Instance

**Problem:** Each `fetch_browser` call starts `sync_playwright()`, `chromium.launch()`, then `close()`. This adds 3-5s overhead per URL and leaks resources.

**Fix:** Use a process-level singleton `BrowserPool`:

```python
class BrowserPool:
    _instance = None
    @classmethod
    def get_browser(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._ensure_browser()
        else:
            cls._instance._ensure_browser()  # handles crash recovery
        return cls._instance._browser

    def _ensure_browser(self):
        # Check is_connected(), re-launch on crash
        ...
```

Key behaviors:
- Browser launches once, reused for all URLs in the process
- `_ensure_browser()` checks `is_connected()` before each use — if crashed (e.g. `Target crashed`), re-launches automatically
- `atexit.register(BrowserPool.close_all)` ensures cleanup on process exit
- `context.close()` per page (not `browser.close()`) keeps browser alive for next URL

**Placement:** In the fetchers module at module level, just after the `HAS_PLAYWRIGHT` flag. NOT inside `fetch_browser()`.

**Caveat:** On some sites Bloomberg, Reuters) the headless browser still gets detected/killed regardless of pooling — the pool only saves launch overhead, not bypass detection.

### 3.3 Cascade Total Timeout (cascade_timeout)

**Problem:** A single URL can block the entire batch by running all cascade strategies. With 5 strategies at 20-30s each, one URL takes 100-150s. In serial mode, 5 such URLs = 8-12 minutes.

**Fix:** Add a per-cascade soft deadline in `extract_single`:

```python
deadline = time.monotonic() + cascade_timeout  # default 90s
for strategy in order:
    if time.monotonic() >= deadline:
        cost_trace.append({"ok": False, "error": "cascade_timeout"})
        break  # return partial content (or failure)
    result = fn(url)
```

- **Soft deadline**: doesn't interrupt an in-flight strategy call. Only checked between strategies.
- **Partial content preservation**: if a strategy already obtained content, that content is returned even though the full cascade timed out.
- **Per-batch isolation**: combine with `future.result(timeout=120)` in batch.py for full URL-level isolation.

### 3.4 fetch_browser (Playwright) — Anti-Bot Bypass

**Symptom:** `Target crashed` or `Timeout 30000ms exceeded` on otherwise reachable sites.

**Root causes and fixes:**

| Cause | Fix | Code Change |
|-------|-----|-------------|
| WebGL fingerprinting | Spoof vendor/renderer | `getParameter` override in `add_init_script` |
| navigator properties | Override webdriver, plugins, languages | `Object.defineProperty(navigator, ...)` |
| Heavy page resources | Block images/fonts/CSS/media | `page.route("**/*")` → abort heavy types |
| Outdated Chrome UA | Update to latest | `user_agent='Chrome/131...'` |
| Slow page load | Use `wait_until="commit"` not "load" | `page.goto(url, wait_until="commit")` |
| Random crashes | Add `--no-sandbox`, `--disable-dev-shm-usage` | Chromium launch args |

**Known results (from testing on 2026-07-27/28):**
| Site | Browser Strategy | Fallback |
|------|-----------------|----------|
| Bloomberg | ✅ Works (706 chars) | archive.org |
| Reuters | ❌ Target crashed | archive.org (old snapshots) |
| MarketWatch | ❌ Target crashed | None (all strategies fail) |
| WSJ | ❌ Target crashed | archive.org |

### 3.4 Third-Party API Strategies (curl -4 Pattern)

When httpx has SSL/SNI issues with a target API (e.g., Jina Reader `r.jina.ai` resolves to unreachable IPv6), fall back to `subprocess.run(["curl", "-4", ...])`:

```python
def fetch_jina_reader(url, rate_limiter=None, timeout=10.0):
    reader_url = f"https://r.jina.ai/{url}"
    try:
        import subprocess
        result = subprocess.run(
            ["curl", "-4", "-s", "--max-time", str(int(timeout)),
             reader_url, "-H", "Accept: text/plain"],
            capture_output=True, text=True, timeout=timeout + 2)
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        return text if len(text) >= 100 else None
    except Exception as e:
        logger.warning(f"[jina] {type(e).__name__}: {e}")
        return None
```

**Why `curl -4` and not just `httpx` with IPv4?** `r.jina.ai` has both AAAA (IPv6) and A (IPv4) records. On networks where IPv6 is unreachable, curl's happy-eyeballs timeout is long. `curl -4` forces IPv4 immediately. httpx lacks a native "prefer IPv4" option — subprocess curl is the cleanest workaround.

**Also works for Tavily:**
```python
result = subprocess.run(
    ["curl", "-4", "-s", "--max-time", str(int(timeout)),
     "https://api.tavily.com/search",
     "-H", "Content-Type: application/json",
     "-d", json_payload],
    capture_output=True, text=True, timeout=timeout + 2)
```

### 3.5 Incremental Content Push

**Problem:** Pipeline Step 6 pushes ALL articles with content (`WHERE content_len > 0`) every run. With 780+ articles, this creates 16 chunks and overwhelms the cloud API (502/10054/10061 errors).

**Fix:** Only push articles created/updated since the pipeline started:

```python
push_cutoff = datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S")
rows = conn.execute("""
    SELECT ... FROM news_content nc ...
    WHERE nc.content_len > 0
      AND (nc.fetch_at > ? OR nc.created_at > ?)
""", (push_cutoff, push_cutoff)).fetchall()
```

`t0` is `time.time()` captured at pipeline start. Each 15-minute cron cycle typically pushes 5-20 articles (1 chunk).

### 3.6 BrowserPool Singleton

**Problem:** Each `fetch_browser()` call does `sync_playwright() → p.chromium.launch() → ... → browser.close()`. This adds 3-5s startup time per URL and leaks resources.

**Solution:** Process-level singleton that launches once and reuses the browser for all URLs:

```python
class BrowserPool:
    _instance = None
    _lock = threading.Lock()
    _launch_count = 0  # class-level stats
    _crash_count = 0

    @classmethod
    def get_browser(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = cls.__new__(cls)
                    instance._playwright = None
                    instance._browser = None
                    instance._ensure_browser()
                    cls._instance = instance
        else:
            cls._instance._ensure_browser()
        return cls._instance._browser

    def _ensure_browser(self):
        try:
            if self._browser and self._browser.is_connected():
                return
        except Exception:
            self.__class__._crash_count += 1
            logger.warning("[browser_pool] crash detected, re-launching")
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(...)
        self.__class__._launch_count += 1

    @classmethod
    def close_all(cls):
        ...  # cleanup + reset counters
```

**Key details:**
- `_launch_count` and `_crash_count` are **class variables**, not instance variables — they survive `__init__` and are meaningful from any reference
- `__new__` instead of `__init__` avoids double-initialization on second call
- Crashes auto-detect via `is_connected()` exception → log + re-launch
- `atexit.register(BrowserPool.close_all)` ensures cleanup on process exit

**Usage in fetch_browser:**
```python
def fetch_browser(url, rate_limiter=None, timeout=30.0):
    browser = BrowserPool.get_browser()
    context = browser.new_context(...)
    page = context.new_page()
    ...  # anti-detection, goto, scroll, extract
    context.close()  # NOT browser.close() — pool owns the browser
    return text
```

**Verification:**
```python
from core.fetchers import BrowserPool
b = BrowserPool.get_browser()
print(f"Connected: {b.is_connected()}")
print(f"Launches: {BrowserPool._launch_count}")
BrowserPool.close_all()
```

### 3.3 Cascade Timeout (Soft Deadline)

**Problem:** A single URL can cascade through 6+ strategies, each with 15-30s timeout. Total may exceed 200s, blocking a batch worker.

**Solution:** Add `cascade_timeout` parameter to `extract_single`. Check elapsed time **between** strategies (not in-flight):

```python
def extract_single(url, ..., cascade_timeout=90.0):
    deadline = time.monotonic() + cascade_timeout
    for strategy in order:
        # 级联总超时（软截止）：不中断正在执行的单个策略，
        # 仅在策略间检查。实际总耗时可能比 cascade_timeout
        # 多出一个最长策略的自身超时（当前最大约 30s）。
        if time.monotonic() >= deadline:
            attempt = {"ok": False, "error": "cascade_timeout"}
            cost_trace.append(attempt)
            logger.info(f"[cascade] timeout after {cascade_timeout:.0f}s, "
                        f"tried {len(cost_trace)-1} strategies, "
                        f"partial={len(content or ''):d}c")
            break
        ...
```

**Behavior:**
- If content already obtained before timeout → return `ok: True` with partial content ✅
- If no content yet → return `ok: False` with `cost_trace` ending in `cascade_timeout`
- Normal (fast) URLs finish in <90s → unaffected
- Hard URLs that would have taken 200s → now terminate at ~90-120s (soft) ### 3.4 fetch_jina_reader — Zero-Cost Third-Party API
|------|-----------------|----------|
| Bloomberg | ✅ Works (706 chars) | archive.org |
| Reuters | ❌ Target crashed | archive.org (old snapshots) |
| MarketWatch | ❌ Target crashed | None (all strategies fail) |
| WSJ | ❌ Target crashed | archive.org |

### 3.3 fetch_jina_reader — Zero-Cost Third-Party API

Jina Reader (`https://r.jina.ai/URL`) is free but may be unreachable from some networks (China/GFW). Set a tight timeout (5s) so failure is fast:

```python
# Test availability
curl -s --max-time 5 https://r.jina.ai/https://example.com
```

### 3.4 Domain Profiles (config/domain_profiles.py)

Domain profiles control which strategies are tried and in what order:

```python
"example.com": DomainProfile(
    domain="example.com",
    anti_bot="datadome",      # none | datadome | cloudflare | unknown
    paywall=True,             # False if content is free
    strategy_order=["browser", "archive", "google_cache", "search_snippet"],
    known_failing=["scrapling"],  # skip these entirely
    is_live_blog_domain=False,
    notes="Why this config exists",
)
```

**Strategy Order Design Principles:**
1. Cheapest first (`direct` cost=1, then `archive` cost=1)
2. Medium cost next (`scrapling` cost=2, `jina` cost=2)
3. Expensive only when necessary (`browser` cost=3)
4. Ultimate fallback (`search_snippet` cost=1 — low quality but better than nothing)
5. Skip proven failures via `known_failing` (saves full strategy timeout)

## Phase 4: Testing Methodology

### 4.1 Round Structure

Each test round should:
1. Fetch exactly 5 URLs (not 50 — avoids timeout masking)
2. Record: success/fail, strategy used, content length, duration
3. Track: which strategies were tried per-URL (cost_trace)

```bash
# Extract 5 real pending URLs from DB
python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
urls = conn.execute('''SELECT DISTINCT rr.article_url FROM news_intelligence ni
  JOIN rss_raw rr ON ni.raw_id = rr.id
  LEFT JOIN news_content nc ON nc.intel_id=ni.id
  WHERE ni.tier IN ('A','B') AND nc.id IS NULL
  ORDER BY ni.score_total DESC LIMIT 5''').fetchall()
conn.close()
with open('_t.txt','w') as f: f.write('\n'.join(u[0] for u in urls))
"
python batch.py --urls _t.txt --out _r.jsonl --max-workers 1 --rate-delay 0.3 --verbose
```

### 4.2 Acceptance Criteria

| Metric | Target |
|--------|--------|
| Per-batch (5 URLs) duration | ≤ 120s (indicates no stalled strategies) |
| Reachable site success rate | ≥ 80% (some blocked sites acceptable) |
| SSL ConnectTimeout count | 0 (indicates proxy/httpx fix working) |
| Cascade fallback activation | archive/browser/jina appear in cost_trace for blocked sites |

### 4.3 Progression Steps

1. Start with LIMIT 5, run 5+ rounds to establish baseline
2. Verify no SSL/network regressions across rounds
3. If stable, incrementally increase LIMIT: 5 → 10 → 20
4. Only increase concurrency after LIMIT scaling is verified stable

## References

See `references/content-extraction-session-2026-07-27.md` for the initial debugging session that produced this skill.

See `references/content-extraction-session-2026-07-28.md` for P0 implementation details including:
- BrowserPool singleton design and crash recovery
- cascade_timeout soft deadline mechanism and measurements
- Windows process lock fix (timestamp-based, not os.kill)
- Incremental CONTENT_PUSH optimization (full→delta)
- Step1 sync+score timeout 120→240s (Qwen3 unavailable)
- V2 Fetcher architecture principles documentation

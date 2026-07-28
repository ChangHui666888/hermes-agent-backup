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
├─ Strategy 6 (cost=5) ─── computer_use    → success? → done
└─ Final fallback ───────── search_snippet  → done (low quality)
```

Each strategy has a timeout. If it fails (returns None or content < min_content_len), the next strategy runs.

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

## Phase 2: Common Failure Modes and Fixes

### 2.1 httpx Proxy/SSL Issues (Most Common on Windows)

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

### 3.2 fetch_browser (Playwright) — Anti-Bot Bypass

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

**Verification:**
```python
from core.fetchers import fetch_browser, RateLimiter
text = fetch_browser("https://heavy-anti-bot-site.com/article", RateLimiter(), timeout=30)
print("Got", len(text) if text else "None", "chars")
```

**Known results (from testing on 2026-07-27):**
| Site | Browser Strategy | Fallback |
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

See `references/content-extraction-session-2026-07-27.md` for the full debugging session that produced this skill, including:
- httpx 0.28 + Windows + proxy diagnostics
- 8-round test results with before/after metrics
- Domain profile evolution (why browser was removed from Reuters/MarketWatch)
- Jina Reader availability test on restricted networks

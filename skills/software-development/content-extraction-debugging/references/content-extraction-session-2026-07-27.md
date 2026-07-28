# Content Extraction Debugging Session — 2026-07-27

## System Context

- **Profile:** outside-deepdeek (deepseek-v4-pro, gateway running)
- **Pipeline:** `auto-pipeline.py` at `C:\Users\ChangHui\AppData\Local\hermes\profiles\outside-deepdeek\skills\research\search-engine-v2\scripts\`
- **Cascade engine:** `core/fetchers.py` — extract_single() function
- **Domain config:** `config/domain_profiles.py`
- **Pipeline log:** `scripts/pipeline.log`
- **DB:** `scripts/news_intel/news_intel.db` — 8,636 articles, 820 with content
- **Environment:** Windows 11, Clash/V2Ray proxy on 127.0.0.1:10808

## Before Fix — Problem Profile

| Metric | Value |
|--------|-------|
| Batch size | 50 URLs |
| Per-batch duration | 453-615s (frequently timeout at 600s) |
| Success rate | 66% → 44% → 10% → **2%** over consecutive runs |
| SSL errors | Multiple per round: `ConnectTimeout: _ssl.c:989` |
| Working strategies | Only `direct` (archive/scrapling/browser never appeared in output) |

## Changes Applied

### 1. `auto-pipeline.py:125` — LIMIT 50 → 5
- Effect: Each Fetch batch processes only 5 URLs, completing in 50-90s instead of timing out
- Rationale: Better to process small batches reliably than large batches that timeout to zero

### 2. `core/fetchers.py:_make_client()` — http2=False + SOCKS5 + tight timeouts
- `http2: False` — httpx 0.28 on Windows with proxy has intermittent SSL hangs with http2=True
- SOCKS5 proxy (`socks5://127.0.0.1:10808`) instead of HTTP CONNECT from env var
- Timeouts: connect=5, read=15, write=10, pool=5

### 3. `core/fetchers.py:fetch_browser()` — Anti-detection upgrade
- timeout 60→30s (fail fast when detected)
- UA Chrome 124→131
- Resource blocking (images/fonts/CSS/media via page.route)
- WebGL vendor/renderer spoofing
- Extra content selectors: main, .story-body, .story-content
- Safer domcontentloaded fallback

### 4. `core/fetchers.py` — New jina strategy
- Added `fetch_jina_reader()` with 5s timeout
- Registered in STRATEGY_FN and COST dict
- Jina Reader is a free API (https://r.jina.ai/URL) — unreachable from this network but kept for future use

### 5. `config/domain_profiles.py` — Reuters/MarketWatch profiles
- Reuters: archive→google_cache→jina→search_snippet (browser ❌ Target crashed)
- MarketWatch: direct→archive→google_cache→jina→search_snippet (browser ❌ Target crashed, all strategies fail)
- Default: jina added as fallback after browser

## After Fix — 8-Round Test Profile

| Round | URLs | Success | Fail | Duration | Strategies Used |
|-------|------|---------|------|----------|-----------------|
| 1 | DB pending (Bloomberg+CBS+BBC) | 5/5 | 0 | 70.7s | browser(1), direct(4) |
| 2 | Same + extra | 5/5 | 0 | ~153s* | browser, direct(4) *fake URL stalled |
| 3 | Real media (Reuters+CNBC+Ars+BBC+NPR) | 4/5 | 1 | 50.0s | direct(4) |
| 4 | Real media (Guardian+TC+Wired+Space+Newsweek) | 5/5 | 0 | 54.1s | direct(5) |
| 5 | Real media (AlJazeera+WaPo+MarketWatch+NBC+Economist) | 5/5 | 0 | 65.2s | direct(3), archive(2) |
| 6 | DB pending | 3/3 | 0 | ~120s* | browser, direct(2) *timeout |
| 7 | DB pending (CBS×3+AlJazeera) | 5/5 | 0 | 72.9s | direct(5) |
| 8 | DB pending (CBS×4+AlJazeera) | 5/5 | 0 | 92.0s | direct(5) |

**Total:** 37/39 URLs succeeded (95%), avg duration ~67s/batch, **zero SSL errors**

## Strategy Viability by Domain

| Domain | direct | archive.org | browser | jina | Best Path |
|--------|--------|-------------|---------|------|-----------|
| Bloomberg.com | ❌ 401 | ❌ | ✅ 706c | N/A | browser |
| Reuters.com | ❌ 401 | ✅ 2103c(aged) | ❌ Crashed |❌ Unreachable | RSS FullText (cost=0) |
| MarketWatch.com | ❌ 401 | ❌ 404 | ❌ Crashed | ❌ Unreachable | RSS FullText (cost=0) |
| CBS News | ✅ ~14Kc | ❌ | N/A | N/A | direct |
| BBC/BBC Sounds | ✅ ~700-7Kc | ❌ 404 | N/A | N/A | direct |
| CNBC | ✅ 5Kc | N/A | N/A | N/A | direct |
| Guardian | ✅ 1Kc | N/A | N/A | N/A | direct |
| WaPo | ✅ 2Kc | N/A | N/A | N/A | direct |
| NBC News | ✅ 14Kc | N/A | N/A | N/A | direct |
| Al Jazeera | ✅ ~500c | N/A | N/A | N/A | direct |
| TechCrunch | ✅ 1Kc | N/A | N/A | N/A | direct |
| Ars Technica | ✅ 3Kc | N/A | N/A | N/A | direct |
| Space.com | ✅ 3Kc | N/A | N/A | N/A | direct |
| NPR | ✅ ~500c | N/A | N/A | N/A | direct |
| Economist | ❌ 403 | ✅ 953c | N/A | N/A | archive |
| Wired | ✅ 1Kc | N/A | N/A | N/A | direct |
| Newsweek | ✅ 1Kc | N/A | N/A | N/A | direct |
| SpaceNews | N/A | N/A | N/A | N/A | RSS FullText |

## Key Insights

### Browser Strategy is Not Universal
Playwright bypasses Bloomberg DataDome but fails on Reuters and MarketWatch. The difference may be:
- Bloomberg uses `wait_until="commit"` friendly loading
- Reuters/MarketWatch have more sophisticated detection (WebGL, navigator checks)

### Domain Profiles Must Be Individually Verified
The `known_failing` set is critical for performance. Each domain's strategy viability must be TESTED, not assumed. A strategy that takes 60s to fail on 50 URLs wastes 50 minutes.

### Python Module Caching
Always verify changes take effect in a fresh process. The `config/domain_profiles.py` had a duplicate key (`reuters.com` appeared twice) causing the second occurrence to silently override the first.

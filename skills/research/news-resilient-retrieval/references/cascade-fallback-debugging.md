# Debugging Cascade / Fallback-Chain Pipelines

> A reusable methodology for systems like the fetch cascade
> (direct → archive.org → google_cache → scrapling → browser → search_snippet).
> Core problem: when failure rate climbs from 66% to 2% across consecutive runs,
> it's infrastructure/config, not bad luck.

## When to Use

Any system where:
- Multiple fallback strategies are tried in order (cascade)
- Each strategy has its own timeout, proxy, and failure mode
- The pipeline processes items in batches and failure rate escalates between runs
- You need to distinguish "transient network error" from "permanent anti-bot block"

## Phase 1: Gather Real Failure Data

**Do NOT start by reading the cascade code. Start by reading the production log.**

```bash
# Check recent pipeline runs
cat pipeline.log | grep -E "FETCH|FAILED|DONE"
```

Build per-run statistics from log output:

```
FETCH: 33 ok, 17 fail (66%) 50 URLs [direct:30/30 | none:0/17]
FETCH: 5 ok, 45 fail (10%) 50 URLs [direct:5/5 | none:0/45]
FETCH: 1 ok, 49 fail (2%) 50 URLs [direct:1/1 | none:0/49]
```

## Phase 2: Track Progressive Failure Rate

| Time | Success Rate | Strategy | Duration | Key Insight |
|------|-------------|----------|----------|-------------|
| 10:58 | 0% | timeout | 615s | batch.py 600s timeout — parallelism=1 |
| 11:09 | 66% | direct:30, archive:3 | 530s | first run, all easy targets |
| 18:49 | 44% | direct:22 | 453s | harder targets remain |
| 19:18 | 10% | direct:5 | 552s | most remaining URLs need other strategies |
| 19:36 | 2% | direct:1 | 576s | only trivial ones succeed |

**Pattern: success rate dropping across runs is NOT a pipeline bug.**
The easy URLs were consumed first. Remaining URLs require strategies that are silently failing (browser uninstalled, Tavily key expired, proxy throttled).

## Phase 3: Identify Silent Strategy Failures

For each cascade strategy, check ONE command:

```bash
# Browser strategy (Playwright)
python -c "from playwright.sync_api import sync_playwright; print('OK')"
# If OK → playwright install chromium

# Scrapling strategy
python -c "from scrapling import StealthyFetcher; f=StealthyFetcher(); print('OK')"

# Proxy health
curl -x socks5://127.0.0.1:10808 -s -o /dev/null -w "%{http_code}" https://reuters.com

# API keys
echo ${TAVILY_API_KEY:0:8}...
# Jina Reader: curl -4 -s --max-time 10 "https://r.jina.ai/https://www.bbc.com/news" -H "Accept: text/plain"

# IPv6 connectivity check (r.jina.ai / api.tavily.com often fail over IPv6)
curl -4 -s -o /dev/null -w "%{http_code}" --max-time 5 https://r.jina.ai
curl -6 -s -o /dev/null -w "%{http_code}" --max-time 5 https://r.jina.ai  # ❌ expected from this network
```

Also check the `config/domain_profiles.py` — `known_failing` lists can silently skip strategies:

```python
# If browser is in known_failing but also the FIRST strategy in strategy_order,
# the cascade falls through to the second strategy immediately without trying browser.
# If ALL strategies are in known_failing → cascade returns empty immediately.
# Solution: use jina/tavily as non-browser fallbacks for hard anti-bot sites.
```

### New Strategy: Jina Reader + Tavily

Both are third-party APIs accessed via `curl -4` subprocess (httpx has SSL/SNI issues with raw IPs on this network):

```
Why curl -4?
  r.jina.ai / api.tavily.com resolve to IPv6 → unreachable → SSL timeout.
  curl -4 forces IPv4 → works.
```

| Strategy | API | Content | Cost | Reliability | 
|----------|-----|---------|------|-------------|
| `jina` | r.jina.ai (free) | Full-page Markdown | Free tier | Good for most sites |
| `tavily` | api.tavily.com (dev key) | AI summary (100-500 chars) | Dev key free | Good for any searchable topic |

## Phase 4: Measure Per-Strategy Timing

Add timing instrumentation to find which strategy fails fast vs slow:

```python
for strategy, fetch_fn in self.strategies:
    t0 = time.monotonic()
    result = fetch_fn(url, ...)
    elapsed = time.monotonic() - t0
    if result:
        logger.info(f"[{strategy}] ✅ {elapsed:.1f}s")
        return result
    else:
        logger.warning(f"[{strategy}] ❌ {elapsed:.1f}s")
```

- "fast fail" (403 in 2s) → proxy/IP blocked, not timeout
- "slow die" (timeout after 60s) → DNS/connectivity issue, reduce timeout
- "silent skip" (0s, no log) → skipped by `known_failing` config

## Phase 5: Prioritize Fixes by Impact

| Priority | Fix | Expected Impact | Effort |
|----------|-----|----------------|--------|
| P0 | Increase parallelism (1→3 workers) | 3x throughput | 5 min |
| P0 | Install missing binary (playwright chromium) | Unlocks browser strategy for 5+ domains | 10 min |
| P1 | Reduce per-strategy timeout (30→15s) | Save ~100s per failed URL | 10 min |
| P1 | Replace expired API key | Restores recovery channel (Tavily) | 15 min |
| P2 | Add strategy-failure-reason logging | Better diagnostics next time | 30 min |
| P2 | Add fallback strategy_order for known_failing | Avoid silent empty cascade | 1 hr |

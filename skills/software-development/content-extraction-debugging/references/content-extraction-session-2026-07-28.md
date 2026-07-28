# Session 2026-07-28: P0 Implementation + Pipeline Tuning

## Changes Applied

### P0-1 BrowserPool
- `core/fetchers.py`: Class `BrowserPool` with singleton + auto-recovery
- `atexit.register(BrowserPool.close_all)` for cleanup
- Stats `_launch_count` / `_crash_count` are class-level (not instance)
- `cls.__new__` avoids `__init__` re-entry

### P0-2 cascade_timeout=90s
- `extract_single` parameter `cascade_timeout: float = 90.0`
- Soft deadline: checked between strategy calls, not in-flight
- Partial content preserved on timeout
- Log: `[cascade] timeout after 90s, tried 3 strategies, got partial=452c`

### P0-3 Unified Recovery
- `news_intel/pipeline.py` SearXNG/Tavily → `extract_single(force_strategy_order=...)`
- Eliminated bare `import httpx` from pipeline.py
- Same curl -4 fix, SOCKS5 proxy, error handling as auto-pipeline

## Windows Process Lock Fix
- `os.kill(pid, 0)` → `WinError 87` on Windows (unsupported signal 0)
- Replaced with timestamp-based staleness: `os.path.getmtime(LOCK_FILE)` < `BATCH_TIMEOUT`

## CONTENT_PUSH Incremental
- Before: `WHERE nc.content_len > 0` (pushed all ~780 articles, 16 chunks)
- After: `AND (nc.fetch_at > ? OR nc.created_at > ?)` (pushes only new, ~5-20 articles)

## Step1 timeout
- `news_intel.pipeline --hours 2` timeout 120→240s (Qwen3 unavailability causes ~121s)

## Batch Parameter Tuning Results
- 15 URLs serial: ~9min — too slow (2+ hard URLs blocked batch)
- 10 URLs serial: ~6min — borderline
- 5 URLs serial: ~90s — safe, keeps BATCH_TIMEOUT=600s unused
- max-workers=2: didn't help enough (browser strategy still hangs)
- Browser removed from many domain profiles (known_failing increases

## Domain Profile Updates
- bloomberg.com: drop browser, jina/tavily fallback
- bbc.co.uk: new profile, skip scrapling/browser, jina/tavily direct
- reuters.com: browser→known_failing
- marketwatch.com: browser→known_failing

## Measured Per-Strategy Timeouts (after tuning)
- direct: ~5-15s (SSL/handshake)
- archive: ~5-15s (Wayback Machine response)
- google_cache: ~5-15s (sometimes returns empty)
- jina: ~10s (curl -4 subprocess)
- tavily: ~10s (curl -4 subprocess)
- scrapling: ~20-60s (StealthyFetcher initialization hangs)
- browser: ~30s (Playwright launch + page load timeout)

## V2 Design Principles Captured
See SKILL.md §"Core Design Principle: Single URL → Batch → Pipeline" section.

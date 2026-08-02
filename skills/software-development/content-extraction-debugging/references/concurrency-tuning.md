# Concurrency Tuning — 2026-07-28 Session

## Problem

auto-pipeline.py ran Step 3 (batch.py) with `max-workers=1, LIMIT=5`. 5 URLs serial, each with cascade up to 90s. Total batch time: 150-224s for 5 URLs.

## Constraints

- SOCKS5 proxy shared with rss-scanner (8 workers, every 5 min)
- `cascade_timeout=90s` per URL (soft deadline)
- `BATCH_TIMEOUT=600s`
- `rate-delay=0.3s`

## Test Design (4-Phase Decision Tree)

```
Phase 1: workers=2, LIMIT=5  → <180s → Phase 2
Phase 2: workers=3, LIMIT=5  → <120s → Phase 3
Phase 3: workers=3, LIMIT=8  → <240s → Phase 4
Phase 4: workers=3, LIMIT=10 → <300s → adopt
```

Each phase: 2 rounds from real DB pending URLs (mix of easy + hard).

## Results

| Phase | Config | Round 1 | Round 2 | Verdict |
|-------|--------|---------|---------|---------|
| 1 | workers=2, LIMIT=5 | 63s, 5/5 | — | Phase 2 |
| 2 | workers=3, LIMIT=5 | 94s, 4/5 | 62s, 4/5 | Phase 3 |
| 3 | workers=3, LIMIT=8 | ~60s, 4/8 | 7/0 (partial) | good enough |

Phase 4 not executed — Phase 3 results satisfactory for cron interval (every 15 min).

## Lessons

### Domain Profile Gap Causes Batch Hangs

`dw.com` URL had no profile, so it ran default cascade including `scrapling` (45s hang) + `browser` (30s). Blocked a worker for 75s.

Fix: Add `dw.com` profile with `known_failing=["scrapling","browser"]`.

### scrapling/browser Removed from Default Cascade

Both strategies hang on most sites. Moved to per-domain profiles only (e.g., `investing.com` has browser in its custom profile).

New default: `direct -> archive -> google_cache -> jina -> tavily -> search_snippet`

### Final Parameters

```
max-workers    = 3
LIMIT          = 8/批
rate-delay     = 0.3s
DEFAULT cascade = direct -> archive -> google_cache -> jina -> tavily -> search_snippet
```

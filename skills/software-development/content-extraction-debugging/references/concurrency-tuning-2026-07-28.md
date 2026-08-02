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
| 1 | workers=2, LIMIT=5 | 63s, 5/5 | — | ✅ → Phase 2 |
| 2 | workers=3, LIMIT=5 | 94s, 4/5 | 62s, 4/5 | ✅ → Phase 3 |
| 3 | workers=3, LIMIT=8 | ~60s, 4/8 | 7/0 (partial) | ✅ (stopped here) |

Phase 4 not executed — Phase 3 results were satisfactory for cron interval (every 15 min).

## Lessons Learned

### Domain Profile Gap Causes Batch Hangs

During Phase 2 R2, `dw.com` URL used the default cascade including `scrapling` (45s hang) + `browser` (30s timeout). This blocked a worker for 75s despite `cascade_timeout=90s`.

**Fix:** Added `dw.com` domain profile with `known_failing=["scrapling", "browser"]` and `strategy_order=["direct", "archive", "google_cache", "search_snippet"]`.

### scrapling and browser Should Not Be in DEFAULT_STRATEGY_ORDER

Both strategies:
- `scrapling` (StealthyFetcher): ~45s timeout initialization, only works on specific sites
- `browser` (Playwright): ~30s timeout, most sites detect headless and crash

**Fix:** Removed both from `DEFAULT_STRATEGY_ORDER`. They remain available for domain-specific profiles (e.g., `investing.com` has `browser` in its custom profile and it works).

New default cascade:
```
direct → archive → google_cache → jina → tavily → search_snippet
```

### Concurrency Gains Plateau at workers=3

- workers=1: ~224s (baseline)
- workers=2: ~63s (3.5x improvement — easy URLs parallelized)
- workers=3: ~62-94s (diminishing returns — hard URL cascade is the bottleneck, not workers)

With workers=3, a batch of 8 URLs completes in ~60-100s. Cron fires every 15 min. No need for LIMIT >8.

## Final Parameters

```
max-workers    = 3
LIMIT          = 8/批
rate-delay     = 0.3s
BATCH_TIMEOUT  = 600s
cascade_timeout = 90s (软截止)
DEFAULT cascade = direct → archive → google_cache → jina → tavily → search_snippet
                (scrapling/browser removed — use per-domain profiles only)
```

## Test Command

```bash
# Extract N pending URLs from DB
python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
urls = conn.execute('''SELECT DISTINCT rr.article_url FROM news_intelligence ni
  JOIN rss_raw rr ON ni.raw_id=rr.id
  LEFT JOIN news_content nc ON nc.intel_id=ni.id
  WHERE ni.tier IN (\"A\",\"B\") AND (nc.id IS NULL OR nc.content_md='')
  AND (nc.fetch_strategy IS NULL OR nc.fetch_strategy!=\"exhausted\")
  ORDER BY ni.score_total DESC LIMIT N''').fetchall()
conn.close()
with open('_urls.txt','w') as f:
  for u in urls: f.write(u[0]+'\n')
print('OK, %d URLs' % len(urls))
"

# Run batch
timeout 300 python batch.py --urls _urls.txt --out _result.jsonl \
  --rate-delay 0.3 --max-workers M

# Parse results
python -c "
import json
ok=fail=0
with open('_result.jsonl') as f:
  for line in f:
    r=json.loads(line)
    if r.get('ok'): ok+=1
    else: fail+=1
print('%d ok, %d fail' % (ok,fail))
"
```

# auto-pipeline.py Control-Flow Bug Patterns (2026-07-16)

## Bug 1: `else` bound to wrong `try/except`

**Symptom**: Every pipeline run prints a fake `FETCH: 0 ok, 0 fail (no URLs to fetch)` alongside the real FETCH result. `stats["steps"]` has two FETCH entries — one real, one always 0/0.

**Root cause**: Python `else:` clause binds to the nearest `try/except` at the SAME indentation level.

```python
# WRONG — else belongs to recovery try, not if urls:
try:                          # outer try
    if urls:
        ...subprocess...
        step_result("FETCH", 20, 5, ...)   # real result
    try:                      # recovery try
        ...searxng/tavily...
    except Exception: ...
    else:                     # BUG: attached to recovery try, not if urls:
        step_result("FETCH", 0, 0, "no URLs to fetch")  # fake result every time
except Exception: ...
```

**Fix**: Restructure to `if not urls: step_result(...); else: ...` — put the `step_result` directly inside the `if not urls:` branch, NOT dangling after a try/except.

```python
# CORRECT
if not urls:
    step_result("FETCH", 0, 0, "no URLs to fetch")
else:
    ...subprocess...
    step_result("FETCH", ok_count, fail_count, ...)

# Recovery always runs (same indent as if not urls:/else:)
try:
    ...searxng/tavily...
except Exception as e:
    log(f"  Recovery: {e}")
```

## Bug 2: subprocess.run return value discarded

**Symptom**: batch.py exits non-zero but auto-pipeline logs "FETCH: 0 ok, 0 fail" with no error indication. stderr is silently swallowed.

**Fix**:
```python
result = subprocess.run([...], timeout=600, capture_output=True, text=True)
if result.returncode != 0:
    log(f"  batch.py exited {result.returncode}: {(result.stderr or '')[-500:]}")
```

## Bug 3: TimeoutExpired kills recovery

**Symptom**: If batch.py times out (600s), the exception propagates past Step 3.5 — SearXNG/Tavily recovery never runs. This is the exact scenario where recovery is most needed.

**Fix**: Wrap subprocess.run in its own try/except:
```python
try:
    result = subprocess.run([...], timeout=600, ...)
except subprocess.TimeoutExpired:
    log(f"  batch.py timed out after 600s — recovery will still run")
# Recovery Step 3.5 runs regardless
```

## Bug 4: Step 5/6 silent failure when TOKEN unset

**Symptom**: If `NEWS_API_TOKEN` env var is not set (e.g. cron didn't source it), Cloud Sync and Content Push silently fail with `0 ok, 0 fail` — indistinguishable from "no new events".

**Fix**:
```python
if not TOKEN:
    log("  CLOUD_SYNC skipped: NEWS_API_TOKEN not set")
    step_result("CLOUD_SYNC", 0, 0, "no token configured")
else:
    r = httpx.post(...)
    if r.status_code >= 400:
        log(f"  CLOUD_SYNC: HTTP {r.status_code}: {r.text[:200]}")
        step_result("CLOUD_SYNC", 0, len(events), f"HTTP {r.status_code}")
    else:
        step_result("CLOUD_SYNC", result.get("ok", 0), result.get("fail", 0), ...)
```

## Bug 5: Hardcoded secrets in source code

**Pattern to avoid**:
```python
# DANGEROUS — secret is now in git history forever
TOKEN = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "tvly-dev-1HUFDN-mQCQcNLjj0AK...")
```

**Pattern to use**:
```python
# CORRECT — fail or skip gracefully if not configured
TOKEN = os.environ.get("NEWS_API_TOKEN") or ""
_TAVILY_KEY = os.environ.get("TAVILY_API_KEY") or ""
if not _TAVILY_KEY:
    log("  Tavily recovery disabled: TAVILY_API_KEY not set")
```

**Note**: Removing the fallback from code does NOT un-leak a key already pushed to git — the key must be rotated on the provider side.

## Bug 6: true_coverage double-counting (pipeline_check.py)

**Symptom**: `true_coverage` shows 283/711 ≈ 40% instead of 283/497 ≈ 57%.

**Root cause**: `content_total` is an unconditional `COUNT(*)` — it already includes rows with `fetch_strategy='exhausted'`. Adding `content_exhausted` on top double-counts them:
```python
# WRONG — exhausted rows counted twice
content_total = COUNT(*) FROM news_content          # = 497 (includes 214 exhausted)
content_exhausted = COUNT(*) WHERE exhausted        # = 214
total_accounted = content_total + content_exhausted  # = 711 (double-counted!)

# CORRECT
total_accounted = content_total                     # = 497 (already includes exhausted)
true_coverage = f"{content_ok}/{content_total}"     # = "283/497"
```

# Structural Bug Patterns (Code Review Findings)

Recurring bug classes found across multiple rounds of pipeline code review.
These are NOT one-off errors — they repeat across files because the same
anti-pattern was copy-pasted.

## 1. else-binding: wrong try/except attachment

**Pattern**: An `else:` clause intended for an `if` block is accidentally
attached to a nested `try/except` instead, due to matching indentation.

```python
# ❌ BUG: else attaches to recovery try, not if urls:
if urls:
    ...fetch...
try:                          # recovery try
    ...recovery...
except: ...
else:                         # ← bound to recovery try, NOT if urls:
    step_result("FETCH", 0, 0, "no URLs to fetch")  # fires every run

# ✅ FIX: Explicit if-not pattern
if not urls:
    step_result("FETCH", 0, 0, "no URLs to fetch")
else:
    ...fetch...
```

**Found in**: `auto-pipeline.py` Step 3 (line 336), `pipeline.py`

## 2. sqlite3.Row has no .get() method

**Pattern**: `db.execute().fetchall()` returns `sqlite3.Row` objects,
not dicts. `.get(key, default)` is a dict method; Row uses `row["key"]`.

```python
# ❌ BUG: AttributeError: 'sqlite3.Row' object has no attribute 'get'
desc = row.get("description") or ""

# ✅ FIX: Bracket access
desc = (row["description"] or "")
```

**Found in**: `pipeline.py` lines 82, 137, 176

## 3. RateLimiter: sleep outside lock = no serialization

**Pattern**: Check-then-act across two critical sections.
Thread A reads timestamp, computes delay, exits lock. Thread B also reads
the OLD timestamp (A hasn't written yet), computes same delay. Both sleep
in parallel — zero serialization.

```python
# ❌ BUG: Two lock sections = race window
with self._lock:
    remaining = delay - (now - last)
if remaining > 0:           # Thread B can enter here before A writes
    time.sleep(remaining)
with self._lock:
    self._last_request[domain] = now
# 8 threads complete in 0.05s instead of 0.35s minimum

# ✅ FIX: One lock section
with self._lock:
    remaining = delay - (now - last)
    if remaining > 0:
        time.sleep(remaining)    # Holds lock — intentional for rate limiters
    self._last_request[domain] = time.monotonic()
```

**Verification test**: `T2` in `test_e2e.py` — 8 concurrent workers must
complete in >=0.30s (0.05s × 6 gaps).

**Found in**: `core/fetchers.py` RateLimiter.wait()

## 4. true_coverage denominator double-counting

**Pattern**: Adding a subset count to its superset.

```python
# ❌ BUG: content_total (unconditional COUNT(*)) already includes exhausted rows
total_accounted = content_total + content_exhausted  # double-counts exhausted

# ✅ FIX: content_total IS the total
total_accounted = content_total
```

**Impact**: 283/497=57% true coverage would report as 283/(497+214)=39.8%.
The buggy formula adds exhausted rows TWICE.

**Found in**: `pipeline_check.py` line 787

## 5. Test assertions too strict for legitimate failure states

**Pattern**: Testing for "FAIL not in output" when the system SHOULD
report FAIL under normal operating conditions (e.g., articles with
unfilled content).

```python
# ❌ Anti-pattern: Assuming zero failures forever
check("CHECK FETCHER: FAIL" not in output, "FETCHER no longer reports FAIL")

# ✅ Correct: Distinguish bug-failure from legitimate-failure
if "CHECK FETCHER: FAIL" in output:
    check("FETCHER_DB_ERROR" not in output, "Not a schema bug")
    check("content_ok=0" not in output, "Not all-empty")
    ok("Legitimate unfilled rows — expected state")
else:
    ok("All content filled")
```

**Principle**: FAIL is a SIGNAL, not always a BUG. The test should verify
the ERROR_TYPE, not the presence/absence of FAIL itself.

**Found in**: `test_e2e.py` T1

## 6. subprocess.TimeoutExpired not caught

**Pattern**: `subprocess.run(..., timeout=N)` without try/except lets
timeout propagate as unhandled exception, crashing the entire pipeline.

```python
# ❌ BUG: Timeout crashes pipeline
subprocess.run([...], timeout=300)

# ✅ FIX: Catch + continue with partial results
try:
    subprocess.run([...], timeout=batch_timeout)
except subprocess.TimeoutExpired:
    log(f"batch.py timed out after {batch_timeout}s — using partial results")
# Still read tmp_out — batch.py writes JSONL progressively
```

**Found in**: `pipeline.py` line 118, `auto-pipeline.py` line 136

## 7. Duplicate cascade logic

**Pattern**: The same URL extraction cascade (strategy loop, cost tracking,
structured extraction, temporal validation) implemented independently in
two places. Bug fixes applied to one miss the other.

```python
# ❌ BUG: Two copies of identical cascade
batch.py:     extract_url()     — 88 lines of cascade
fetchers.py:  extract_single()  — 94 lines of same cascade

# ✅ FIX: Delegate
batch.py.extract_url() → calls fetchers.extract_single()
```

**Found in**: `batch.py` extract_url, `core/fetchers.py` extract_single

## 8. Hardcoded secrets in default fallback values

**Pattern**: `os.environ.get("KEY", "hardcoded-secret")` as default.
The secret enters git history on first commit.

```python
# ❌ BUG: Secret in git
TOKEN = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-...")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "tvly-dev-...")

# ✅ FIX: Empty default + guard
TOKEN = os.environ.get("NEWS_API_TOKEN") or ""
TAVILY_KEY = os.environ.get("TAVILY_API_KEY") or ""

if not TOKEN:
    log("Step skipped: TOKEN not configured")
    return
```

**Note**: Removing from code does NOT remove from git history.
Must rotate the actual API keys separately.

**Found in**: `auto-pipeline.py` line 19, `news_intel/pipeline.py` line 33

## 9. API port mismatch between files

**Pattern**: One file uses the correct port (matching Docker compose mapping),
another uses a stale/old port.

```python
# auto-pipeline.py: http://100.107.117.23          ← correct (nginx :80)
# news-pipeline.py: http://100.107.117.23:8001     ← wrong (old FastAPI port)
```

**Impact**: All 156 article pushes silently fail — response may be empty
or 502, but code doesn't check HTTP status before calling `.json()`.

**Found in**: `news-pipeline.py` line 12 vs `auto-pipeline.py` line 18

## 10. Fetch concurrency triggers rate limiting

**Pattern**: ThreadPoolExecutor with many workers hits the same domain
simultaneously → anti-bot systems detect abnormal concurrency → 403/429.

```python
# ❌ BUG: 8 workers → Bloomberg: 403, Google Cache: 429, WinError 10054
"--max-workers", "8", "--rate-delay", "0.1"

# ✅ FIX: Serial fetch with 1s delay between requests
"--max-workers", "1", "--rate-delay", "1.0"
```

**For LLM**: Concurrency is fine (local API, no rate limits).
Use ThreadPoolExecutor with separate DB writes (single-threaded after all calls).

**Found in**: `pipeline.py`, `auto-pipeline.py` batch.py invocation

## 11. Redundant stage in pipeline run

**Pattern**: pipeline_check.py `run` included a standalone `fetcher` stage
with no URL arguments. batch.py requires `--urls`, `--url`, or `--stdin`.

```python
# ❌ BUG: batch.py called with no input
stages = ["rss", "pipeline", "fetcher", "aggregator", "sync"]
# fetcher stage: cmd = ["python", "batch.py"]  — no --urls

# ✅ FIX: Remove redundant stage
stages = ["rss", "pipeline", "aggregator", "sync"]
# pipeline already runs batch.py internally via --fetch flag
```

**Found in**: `pipeline_check.py` line 1358

## 12. DataDome: optimizing strategy_order is counterproductive

**Pattern**: Bloomberg/WSJ/FT use DataDome + PerimeterX. ALL automated tools
are blocked — httpx (403), headless Playwright ("Are you a robot?"),
Google Cache (429). Only a real desktop browser on residential IP works.

Attempting to "optimize" by reducing strategy_order (e.g., dropping direct
and google_cache) is WRONG — archive.org SOMETIMES works for older articles,
and google_cache occasionally succeeds. The full cascade has value, even if
most attempts fail. Let the cascade run; mark scrapling+browser as known_failing.

**DO NOT**: Reduce strategy_order for DataDome domains.
**DO**: Let SearXNG/Tavily recovery find alternative coverage from other sources.

**Found in**: `config/domain_profiles.py` bloomberg.com, wsj.com, ft.com

## 13. LLM concurrency: DB writes must be sequential

**Pattern**: ThreadPoolExecutor parallelizes route() calls (which may call
Qwen API), but sqlite3 connections are NOT thread-safe. Collect all results
in memory, then write sequentially:

```python
# ✅ CORRECT: Parallel LLM, sequential DB
results = {}
with ThreadPoolExecutor(max_workers=3) as ex:
    futures = {ex.submit(route, ...): row for row in rows}
    for fut in as_completed(futures):
        results[fut] = fut.result()

for row, result in results.items():   # DB writes: single-threaded
    upsert_content(db, ...)
```

Also: global `_qwen_available` flag needs `threading.Lock()` protection.

**Found in**: `pipeline.py` line 227-264

## 14. LLM max_tokens tradeoff: output length vs timeout

**Pattern**: Qwen3-1.7B on CPU: 1024 max_tokens → ~20s per article.
17 Tier B articles × 20s = 340s → exceeds pipeline timeout.

Reducing to 500 tokens cuts per-article time to ~10s without quality loss
for the task (tags + entities + summary + tone). The JSON output is <300
tokens in practice.

**Found in**: `enhancers.py` enhance_qwen() max_tokens parameter

## Verification Checklist

After fixing ANY of the above, verify:
1. `python test_e2e.py -v` — all tests pass
2. `python -c "compile(open('file.py').read(), ...)"` — syntax OK
3. For timing bugs: run with VERBOSE to see actual delay values
4. For test assertion bugs: simulate both states (full vs partial data)

# Round 4: pipeline.py fixes + investing.com + E2E T8 (2026-07-16)

## Background

`pipeline_check.py run` → `news-pipeline.py` → `run_pipeline()` crashed:

1. `AttributeError: 'sqlite3.Row' object has no attribute 'get'` at line 82
2. `subprocess.TimeoutExpired` — batch.py 147 URLs with 3 workers × Scrapling 45s retries → >300s

## Fix 1: sqlite3.Row vs dict (3 call sites)

```python
# ❌ Bug — sqlite3.Row doesn't have .get()
desc = (row.get("description") or "").strip()
score = row.get("score_total", 0)

# ✅ Fix — bracket notation
desc = (row["description"] or "").strip()
score = (row["score_total"] or 0)
```

**Root cause**: `db.execute().fetchall()` returns `sqlite3.Row` objects when `row_factory` is default.
These support `row["key"]` and `row[n]` but NOT `.get()`.

**Cross-project pattern**: Any time you see `row.get(...)`, immediately verify whether `row` is a `dict` or a `sqlite3.Row`.

## Fix 2: TimeoutExpired handled + partial results

```python
# ❌ Bug — timeout propagates as unhandled exception
subprocess.run([...], cwd=SCRIPT_DIR, timeout=300)

# ✅ Fix — caught, logged, partial results processed
try:
    subprocess.run([...], cwd=SCRIPT_DIR, timeout=batch_timeout)
except subprocess.TimeoutExpired:
    print(f"  [fetch] batch.py timed out after {batch_timeout}s — using partial results")
# Read partial results from jsonl (batch.py writes progressively)
if os.path.exists(out_file):
    with open(out_file) as f:
        for line in f:
            data = json.loads(line)
            if data.get("ok"):
                fetched_content[data["url"]] = data.get("content", "")
```

## Fix 3: Params synced with auto-pipeline.py

```python
# ❌ Old (stale)
"--rate-delay", "0.5", "--max-workers", "3"

# ✅ New (matches auto-pipeline.py)
"--rate-delay", "0.1", "--max-workers", "8"
```

## Fix 4: TAVILY_KEY hardcoded fallback removed

```python
# ❌ Before
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "tvly-dev-1HUFDN-...")

# ✅ After
TAVILY_KEY = os.environ.get("TAVILY_API_KEY") or ""
```

## Fix 5: investing.com domain profile

Added to `config/domain_profiles.py`:

```python
"investing.com": DomainProfile(
    domain="investing.com",
    anti_bot="cloudflare",
    strategy_order=["direct", "google_cache", "archive", "search_snippet"],
    known_failing=["scrapling", "browser"],
    notes="Cloudflare强防护。direct返回403；scrapling超时(45s×3)。用archive+search_snippet兜底",
),
```

**Impact**: Each investing.com URL previously wasted 135s (45s×3 Scrapling retries).
With 147 URLs in a batch and only 3 workers, 5 investing.com URLs = 675s total.
Now they fail fast after direct/google_cache/archive.

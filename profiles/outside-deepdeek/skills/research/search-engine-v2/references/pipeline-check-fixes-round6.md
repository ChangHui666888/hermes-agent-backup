# Round 6 Fixes: pipeline_check.py run + API port (2026-07-16)

## Bug 1: fetcher stage always fails in `pipeline_check.py run`

**Symptom**: `python pipeline_check.py run` stops at fetcher stage with:
```
error: 需要 --url, --urls, 或 --stdin 提供 URL
```

**Root cause**: `COMMANDS["fetcher"]["cmd"]` (line 253-261) is just `["python", "batch.py"]` — no URL source argument. batch.py requires at least one of `--url`, `--urls`, or `--stdin`.

**Deeper issue**: The `"pipeline"` stage already runs `news-pipeline.py --fetch`, which internally calls `batch.py` as a subprocess. The standalone `"fetcher"` stage is redundant — all fetching happens inside the pipeline stage.

**Fix**: Remove `"fetcher"` from the `stages` list in `run_all_stages()`:
```python
# BEFORE (line 1358-1370)
stages = ["rss", "pipeline", "fetcher", "aggregator", "sync"]

# AFTER
stages = ["rss", "pipeline", "aggregator", "sync"]
```

**Impact**: `pipeline_check.py run` no longer crashes after pipeline stage. Runs: RSS → Pipeline → Aggregator → Sync.

---

## Bug 2: All 156 article pushes fail with port 8001

**Symptom**: `[WinError 10054] 远程主机强迫关闭了一个现有的连接` — all pushes fail.

**Root cause**: `news-pipeline.py:12` hardcodes `NEWS_API_BASE` default to `http://100.107.117.23:8001`. The Docker Compose setup maps the backend to port 80 (with nginx reverse proxy). Port 8001 was the old FastAPI port, now closed.

**Fix**:
```python
# BEFORE
os.environ.setdefault("NEWS_API_BASE", "http://100.107.117.23:8001")

# AFTER
os.environ.setdefault("NEWS_API_BASE", "http://100.107.117.23")
```

**Verification**: `curl -X POST http://100.107.117.23/internal/events/batch -d "[]"` returns HTTP 200 on port 80.

**Pattern**: Port mismatches between development and Docker deployment are a recurring issue. Always verify with curl before assuming the API is unreachable.

---

## Bug 3: LLM enhancement is purely sequential (no concurrency)

**Symptom**: 17 Tier B articles × 20s each = 340s spent waiting on LLM. Pipeline hits 600s timeout.

**Root cause**: `pipeline.py:215` was a plain `for row in rows:` loop — each Qwen3-1.7B call blocks the entire pipeline.

**Fix** (Round 5):
1. `enhancers.py`: `_qwen_lock` (threading.Lock) on `_qwen_available` flag
2. `pipeline.py`: `ThreadPoolExecutor(max_workers=4)` for route() calls
   - Pre-fetch entities/tags from DB
   - Submit all route() calls to thread pool
   - Collect results via `as_completed()`
   - Write to DB sequentially (sqlite3 not thread-safe)
3. Configurable via `LLM_CONCURRENCY` env var (default 4)

```python
llm_concurrency = int(os.environ.get("LLM_CONCURRENCY", "4"))
with ThreadPoolExecutor(max_workers=llm_concurrency) as executor:
    futures = {}
    for row, entities, tags, content_md in row_data:
        fut = executor.submit(route, ...)
        futures[fut] = row
    for fut in as_completed(futures):
        ...
```

**Time projection**: 8 Tier B / 4 workers × 10s ≈ 20s (was 160s).

---

## Lessons

| Pattern | Description |
|---------|-------------|
| Redundant stage | Before adding a pipeline stage, verify it's not already handled internally by a previous stage |
| Port drift | Docker port mappings change over time. The `NEWS_API_BASE` default in code must match the current Docker Compose configuration |
| Sequential LLM | Any `for row: route()` loop processing N articles through a local LLM is a timeout risk. Always use ThreadPoolExecutor |

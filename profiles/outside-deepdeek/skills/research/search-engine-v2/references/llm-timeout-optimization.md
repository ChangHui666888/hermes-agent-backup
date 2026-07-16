# LLM Timeout Optimization (2026-07-16 Round 5)

## Problem

Pipeline timed out at 600s during LLM enhancement phase. Qwen3-1.7B on CPU
took 15-25s per Tier B article (max_tokens=1024), 200 articles per batch.

```
Time breakdown:  340s LLM (17 B articles) + 165s fetch + 55s search ≈ 560s
                 → hits 600s pipeline_check.py timeout → crash
```

## Root Cause Chain

1. `enhance_qwen()` called `_call_qwen(QMERGE_PROMPT, text, max_tokens=1024)`
   → Qwen3-1.7B on CPU: ~20s per 1024-token generation
2. `news-pipeline.py --limit 200` → up to 48 Tier B articles in one batch
3. `pipeline_check.py subprocess.run(timeout=600)` → total pipeline timeout

## Fixes (3 files)

| File | Change | Rationale |
|------|--------|-----------|
| `enhancers.py:175` | `max_tokens: 1024 → 500` | 50% faster per article; JSON output fields (tags/cos/persons/summary/tone) fit in 500 tokens |
| `news-pipeline.py:64` | `--limit: 200 → 100` | Half batch → half LLM calls; ~8 Tier B per run |
| `pipeline_check.py:1215` | `timeout: 600 → 1200` | Headroom for LLM tail latency + retry storms |

## Time Projection (After Fixes)

```
100 articles → ~8 Tier B × (20s × 0.5) ≈ 80s LLM
+ fetch ~90s + search ~30s ≈ 200s total — well within 1200s window
```

## Two Independent Timeout Guards (Both Must Exist)

The pipeline has TWO timeout layers, both were affected:

1. **Inner**: `pipeline.py:118` — `subprocess.run(batch.py, timeout=300)` — catches TimeoutExpired, reads partial results (fixed in Round 4)
2. **Outer**: `pipeline_check.py:1215` — `subprocess.run(news-pipeline.py, timeout=1200)` — catches TimeoutExpired at pipeline run level

Both needed separate fixes because they protect different scopes:
- Inner: protects batch.py from slow Scrapling/investing.com
- Outer: protects entire pipeline from slow LLM enhancement

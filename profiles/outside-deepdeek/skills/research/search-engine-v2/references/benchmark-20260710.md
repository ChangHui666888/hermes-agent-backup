# Pipeline Efficiency Benchmark (2026-07-10)

200 real RSS articles, Qwen3-1.7B (2.74s/call avg).

## Three approaches compared

| Scheme | Time | LLM calls | Articles processed |
|------|:--:|:--:|:--:|
| **A: Score first → selective enhance (current)** | **48s** | **48** | 16 (8% Tier A/B) |
| B: Score + enhance all | 600s | 600 | 200 (100%) |
| C: Extract first → score (rules only) | 0.02s | 0 | 200 (100%, no AI summary) |

## Conclusion

**Scheme A is optimal — DO NOT change.**

- Scoring uses RSS title + description only (in-memory lookup, <1ms/article)
- LLM enhancement triggers only for 8% of articles (Tier A/B)
- Saves 92% compute vs full-enhance approach
- Scheme C is fastest but produces no AI-quality summaries

## Key optimizations applied

1. Merged 3 Qwen calls → 1 (QMERGE_PROMPT)
2. Fail-fast: first Qwen failure skips all remaining
3. Scoring dedup: skip already-scored articles
4. Enhancement dedup: skip already-enhanced articles
5. Cloud push fail-fast: 3 consecutive failures → break

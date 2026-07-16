# Pipeline Gap Diagnosis — SQL Method

Diagnose content gaps (articles scored but no content fetched) with structured SQL queries.

## The Three-Gap Analysis

When pipeline_check.py reports `FETCHER: FAIL (intel=N content=M content_ok=K missing=M-K)`,
run this diagnostic chain:

### Gap 1: RSS → Pipeline (expected drop)

```sql
-- RSS raw vs pipeline scored
SELECT (SELECT COUNT(*) FROM rss_raw) as rss_total,
       (SELECT COUNT(*) FROM news_intelligence) as intel_total,
       (SELECT COUNT(*) FROM news_intelligence WHERE tier IN ('A','B')) as ab_count;
```
**Normal**: Most articles are tier C (not fetched). Only A+B participate in fetch.

### Gap 2: Pipeline → content rows

```sql
-- Tier A+B with vs without content rows
SELECT
  COUNT(*) as total_ab,
  COUNT(CASE WHEN nc.id IS NULL THEN 1 END) as no_content_row,
  COUNT(CASE WHEN nc.id IS NOT NULL THEN 1 END) as has_row
FROM news_intelligence ni
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A','B');
```
**Target**: `no_content_row` should be 0 for A tier, <10% for B tier.

### Gap 3: Content rows → actual content (core fault)

```sql
-- By strategy, how many rows actually have content?
SELECT COALESCE(fetch_strategy, 'NULL') as strategy,
       COUNT(*) as total,
       COUNT(CASE WHEN content_md IS NOT NULL AND content_md != '' THEN 1 END) as has_content
FROM news_content
GROUP BY strategy
ORDER BY total DESC;
```

**Red flag**: `fetch_strategy IS NULL` rows with `content_md = ''`. These are placeholder rows
that were created without content and are blocking re-fetch.

### Placeholder rows detail

```sql
-- Placeholder rows: when were they created, do they have Qwen summaries?
SELECT id, intel_id, article_url, content_md IS NULL, content_md = '',
       content_len, summary_cn, summary_en, extraction_method, llm_model, created_at
FROM news_content
WHERE fetch_strategy IS NULL
LIMIT 5;
```

**Typical pattern**: Qwen3-generated summaries (`extraction_method=qwen3`, `llm_model=qwen3-1.7b-instruct`)
but `content_md = ''` and `content_len = 0`. These were created by an old pipeline version.

### Root cause fix

```sql
-- Delete placeholder rows to free URLs for re-fetch
DELETE FROM news_content
WHERE fetch_strategy IS NULL
  AND (content_md IS NULL OR content_md = '')
  AND retry_count >= 3;
```

After cleanup, re-run `pipeline_check.py check` — FETCHER should return to healthy state,
and next cron run will re-queue the URLs through RSS_FULLTEXT + batch.py.

## Per-Strategy Health

```sql
-- Strategy success rate
SELECT COALESCE(fetch_strategy, 'none') as strategy,
       COUNT(*) as total,
       COUNT(CASE WHEN content_md IS NOT NULL AND content_md != '' THEN 1 END) as ok,
       ROUND(COUNT(CASE WHEN content_md IS NOT NULL AND content_md != '' THEN 1 END) * 100.0 / COUNT(*), 1) as pct
FROM news_content
GROUP BY strategy
ORDER BY total DESC;
```

## Remaining Fetch Queue

```sql
-- How many A+B articles still need fetching (excluding exhausted)
SELECT COUNT(*) FROM news_intelligence ni
JOIN rss_raw rr ON ni.raw_id = rr.id
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A','B')
  AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
  AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
  AND rr.article_url IS NOT NULL
  AND rr.article_url != '';
```

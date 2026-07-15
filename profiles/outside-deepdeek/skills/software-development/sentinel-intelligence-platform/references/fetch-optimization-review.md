# Fetch Pipeline Optimization Review

## Data Facts (from 4245 articles)

- `content_encoded` (RSS full text): 0 — RSS feeds don't send full text
- `description > 200 chars`: 998 (23%) — usable RSS summaries can skip HTTP fetch

## Evaluated Suggestions

### ✅ 1. RSS FullText — Implement immediately

998 articles (23%) have RSS description >200 chars. Adding `rss_fulltext` as first strategy
in the cascade skips HTTP fetch entirely for these articles. Zero cost, immediate benefit.

```python
STRATEGY_FN = {
    "rss_fulltext": lambda: fetch_rss_fulltext(url, article_row),  # NEW — cost=0
    "direct": ...,
    "archive": ...,
    ...
}
```

### ✅ 2. Quality Validator — Implement immediately

Current check: only `len(result) > min_len`. This misses:
- Login pages (3000+ chars of HTML, not content)
- Cookie popups (long text, no real content)
- JS placeholder pages

Add 2 quick checks:
- `html_ratio`: tag density > 30% → reject
- `line_density`: 5 consecutive lines without punctuation → likely JS/JSON

### ✅ 3. known_failing Enhancement — V2

domain_profiles already has `known_failing` lists. Enhance with auto-learning
from domain_statistics (see below).

### ❌ 4. Extractor Router — Not needed

`_extract_main_text()` already has 3-level fallback:
trafilatura → readability → regex. No need for separate router module.

### ✅ 5. Domain Statistics — V2

Track per-domain per-strategy success rates. After enough data, auto-populate
`known_failing` and reorder `strategy_order`. Simple SQLite table:

```sql
CREATE TABLE fetch_stats (
    domain TEXT,
    strategy TEXT,
    success INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    last_used TEXT,
    PRIMARY KEY (domain, strategy)
);
```

### ❌ 6. Search Snippet Reordering — Don't do

SAO extraction needs >200 chars. Search snippets may not provide enough.
Keep as last-resort fallback.

## Implementation Priority

| Priority | Item | Hours | Impact |
|:--:|------|:--:|------|
| 1 | RSS FullText | 0.25h | -23% HTTP requests |
| 2 | Quality Validator | 0.5h | Fewer false positives |
| 3 | known_failing automation | 0.25h | Fewer failed attempts |
| 4 | Domain Statistics | 1h | Auto-optimizing cascade |

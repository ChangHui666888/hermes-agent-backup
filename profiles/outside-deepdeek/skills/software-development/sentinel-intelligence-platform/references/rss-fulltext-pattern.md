# RSS FullText Strategy

## Problem
998 of 4245 articles (23%) have usable RSS descriptions (200-500 chars) but still go through full HTTP fetch cascade (direct→archive→scrapling→browser).

## Solution
Pre-check RSS description in pipeline.py before calling batch.py. If description is long enough and not HTML-heavy, write directly to DB with strategy="rss_fulltext", cost=0.

## Implementation (pipeline.py)
```python
for row in rows:
    url = row["article_url"]
    desc = (row.get("description") or "").strip()
    if url and len(desc) >= 200:
        html_ratio = (desc.count("<") + desc.count(">")) / max(len(desc), 1)
        if html_ratio < 0.3:
            db.execute("""
                INSERT INTO news_content (intel_id, article_url, content_md, content_len,
                    fetch_strategy, fetch_cost, fetch_at)
                VALUES (?, ?, ?, ?, 'rss_fulltext', 0, datetime('now','localtime'))
                ON CONFLICT(article_url) DO UPDATE SET
                    content_md=excluded.content_md, content_len=excluded.content_len,
                    fetch_strategy='rss_fulltext', fetch_cost=0
            """, (row["intel_id"], url, desc, len(desc)))
            rss_skip += 1
            continue
    if url:
        urls_to_fetch.append((url, row["intel_id"], row["tier"]))
```

## Effect
- Saves ~23% HTTP requests
- Cost=0 (no network, no proxy)
- HTML density check prevents boilerplate storage

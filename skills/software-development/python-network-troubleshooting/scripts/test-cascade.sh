# RSS Pipeline Cascade — Test Procedure

## Prerequisites
```bash
cd "C:/Users/ChangHui/AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2/scripts"
```

## Step 1: Verify Playwright
```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

## Step 2: Verify Proxy
```bash
# SOCKS5 (recommended for httpx)
curl -x socks5://127.0.0.1:10808 -s -o /dev/null -w "%{http_code}" --max-time 10 https://www.bbc.com
```

## Step 3: Check Pending URLs
```bash
python -c "
import sqlite3
db_path = 'news_intel/news_intel.db'
conn = sqlite3.connect(db_path)
pending = conn.execute('''
    SELECT COUNT(*) FROM news_intelligence ni
    JOIN rss_raw rr ON ni.raw_id = rr.id
    LEFT JOIN news_content nc ON nc.intel_id = ni.id
    WHERE ni.tier IN (\"A\",\"B\")
      AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
      AND rr.article_url IS NOT NULL AND rr.article_url != ''
''').fetchone()[0]
total = conn.execute('SELECT COUNT(*) FROM news_intelligence').fetchone()[0]
content = conn.execute('SELECT COUNT(*) FROM news_content').fetchone()[0]
conn.close()
print(f'Total: {total}  Cached: {content}  Pending: {pending}')
"
```

## Step 4: Fetch Batch
```bash
python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
urls = conn.execute('''
    SELECT DISTINCT rr.article_url FROM news_intelligence ni
    JOIN rss_raw rr ON ni.raw_id = rr.id
    LEFT JOIN news_content nc ON nc.intel_id = ni.id
    WHERE ni.tier IN (\"A\",\"B\")
      AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
      AND rr.article_url IS NOT NULL AND rr.article_url != ''
    ORDER BY ni.score_total DESC
    LIMIT 5
''').fetchall()
conn.close()
with open('_urls.txt', 'w') as f:
    for u in urls: f.write(u[0] + '\n')
print(f'Extracted {len(urls)} URLs')
"

python batch.py --urls _urls.txt --out _result.jsonl --max-workers 1 --rate-delay 0.3 --verbose
```

## Step 5: Inspect Results
```bash
python -c "
import json
with open('_result.jsonl') as f:
    for line in f:
        if not line.strip(): continue
        r = json.loads(line)
        ok = r.get('ok', False)
        strat = r.get('strategy_used', 'N/A')
        ct = r.get('cost_trace', [])
        tried = ['%s(%s)' % (t['strategy'], 'OK' if t.get('ok') else str(t.get('error',''))[:20]) for t in ct]
        url_s = r.get('url', '')[:60]
        if ok:
            print('  ✅ %-15s | %5d chars | %s' % (strat, len(r.get('content','')), url_s))
        else:
            print('  ❌ %s' % '; '.join(tried))
            print('     %s' % url_s)
"
```

## Step 6: Cleanup
```bash
rm -f _urls.txt _result.jsonl
```

## Acceptance Criteria
| Criterion | Expected |
|-----------|----------|
| 5 URLs completion time | ≤ 120s (was ≥ 600s) |
| Accessible URL success rate | ≥ 80% |
| SSL ConnectTimeout errors | 0 |
| Cascade fallback | archive/browser as fallback for direct 403/404 |

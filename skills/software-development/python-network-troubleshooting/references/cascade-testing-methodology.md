# Cascade Pipeline Testing Methodology

## Why This Exists

Standard "does the pipeline run?" verification only validates the happy path. 
This methodology tests boundaries, failure independence, and data integrity 
that only show up in edge cases.

## Batch Tests (5 Scenarios)

```bash
cd /path/to/scripts
```

### 1. Regression — Plain URLs, Default Cascade

```bash
echo "https://www.bbc.com/news" > urls.txt
echo "https://arstechnica.com" >> urls.txt
echo "https://www.theguardian.com/world" >> urls.txt
python batch.py --urls urls.txt --out t1.jsonl --max-workers 2 --verbose
python -c "
import json
for line in open('t1.jsonl'):
    r = json.loads(line)
    print('✅' if r['ok'] else '❌', r.get('strategy_used','?'), r['url'][:60])
"
```

Validates: Existing behavior not broken by refactoring.

### 2. Multi-Candidate Cascade — `url\ttitle` + `--force-strategy`

```bash
printf "https://www.reuters.com/world/middle-east/\tGaza ceasefire Middle East\n" > urls.txt
printf "https://www.bloomberg.com/news/articles/2026-07-13/test\tGold holds decline\n" >> urls.txt
python batch.py --urls urls.txt --out t2.jsonl \
  --force-strategy searxng_alt,tavily --max-workers 1 --verbose
python -c "
import json
for line in open('t2.jsonl'):
    r = json.loads(line)
    ct = r.get('cost_trace',[])
    chain = '→'.join([t['strategy']+('✅' if t.get('ok') else '❌') for t in ct])
    print('✅' if r['ok'] else '❌', chain, r['url'][:55])
"
```

Validates: When `searxng_alt` finds an alternate source, content is returned. 
When it fails, `tavily` runs as fallback. Strategy name in `strategy_used` is correct.

### 3. Single-Strategy — Tavily Only

```bash
printf "https://www.marketwatch.com/story/test\tMarketWatch stock market\n" > urls.txt
python batch.py --urls urls.txt --out t3.jsonl \
  --force-strategy tavily --max-workers 1 --verbose
python -c "
import json
for line in open('t3.jsonl'):
    r = json.loads(line)
    print(r.get('strategy_used'), len(r.get('content','') or ''), r['url'][:60])
"
```

Validates: `strategy_used = "tavily"` (not null, not fallback label).

### 4. Mixed Input Format — `url\ttitle` + Plain URL

```bash
cat > urls.txt << 'EOF'
https://www.bbc.com/news
https://www.reuters.com/world/middle-east/	Gaza ceasefire
https://arstechnica.com
EOF
python batch.py --urls urls.txt --out t4.jsonl --max-workers 1
python -c "
import json
with open('t4.jsonl') as f:
    for line in f:
        r = json.loads(line)
        print(r['ok'], r.get('strategy_used','?'), r['url'][:55])
"
```

Validates: `_parse_url_line` handles mixed tab/no-tab lines without crashing.

### 5. All-Fail Boundary — Non-Existent Domains

```bash
cat > urls.txt << 'EOF'
https://www.this-domain-definitely-does-not-exist-12345.com/article
https://www.reuters.com/nonexistent-page-987654321
EOF
python batch.py --urls urls.txt --out t5.jsonl \
  --force-strategy searxng_alt,tavily --verbose
python -c "
import json
with open('t5.jsonl') as f:
    for line in f:
        r = json.loads(line)
        ct = r.get('cost_trace',[])
        missing = [f for f in ['ok','url','error','cost_trace'] if f not in r]
        print('field check:', '✅' if not missing else '❌ missing '+str(missing))
        for t in ct:
            print('  %s: %s' % (t['strategy'], 'OK' if t.get('ok') else t.get('error','')[:30]))
"
```

Validates: Error fields are present (`error`, `cost_trace`). No `KeyError` from missing `content` field.

## Pipeline Tests (5 Scenarios)

```bash
cd /path/to/scripts
```

### A. Step Independence — Step3 Fails, Step3.5 Still Runs

```bash
mv batch.py batch.py.DISABLED
timeout 180 python auto-pipeline.py 2>&1 | grep -E 'Step 3|FAILED|Recovery'
mv batch.py.DISABLED batch.py
```

Expected log:
```
Step 3/6: Fetch (batch.py)
Step 3.5: Recovery (SearXNG + Tavily)   ← Step3 failure did NOT skip this
```

Validates: Step3 and Step3.5 are in independent `try` blocks.

### B. Data Integrity — intel_id NOT NULL

```bash
python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
nulls = conn.execute('''
    SELECT COUNT(*) FROM news_content
    WHERE intel_id IS NULL
      AND fetch_at > datetime('now','-2 hours','localtime')
''').fetchone()[0]
conn.close()
print('intel_id IS NULL:', nulls, '✅' if nulls == 0 else '❌')
"
```

Expected: `intel_id IS NULL: 0 ✅`

### C. Strategy Name Accuracy

```bash
python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
rows = conn.execute('''
    SELECT fetch_strategy, COUNT(*)
    FROM news_content
    WHERE fetch_at > datetime('now','-2 hours','localtime')
    GROUP BY fetch_strategy
    ORDER BY COUNT(*) DESC
''').fetchall()
for s, c in rows:
    print('  %-15s %d' % (s or 'NULL', c))
conn.close()
"
```

Expected strategy names: `searxng_alt`, `tavily`, `rss_fulltext`, `direct` (not empty/null).

### D. Process Lock

```bash
cd /path/to/scripts
python -c "
import os, time
fd = os.open('.pipeline.lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
os.write(fd, b'test')
os.close(fd)
now = time.time()
os.utime('.pipeline.lock', (now-2, now-2))
print('fake lock 2s old')
"
timeout 10 python auto-pipeline.py 2>&1 | grep -E 'SKIP|PIPELINE START'
rm -f .pipeline.lock
```

Expected: `[SKIP] 已有 pipeline 在跑` then exit (no actual pipeline execution).

### E. TOKEN Missing Regression

```bash
NEWS_API_TOKEN="" timeout 300 python auto-pipeline.py 2>&1 | grep -E 'skipped|FAILED'
```

Expected:
```
CLOUD_SYNC skipped: NEWS_API_TOKEN not set
CONTENT_PUSH skipped: NEWS_API_TOKEN not set
```
No crashes, no uncaught exceptions.

## Timing / Performance Test

For tuning batch parameters:

```bash
cd /path/to/scripts

# Select 5 representative pending URLs
python -c "
import sqlite3
conn = sqlite3.connect('news_intel/news_intel.db')
urls = conn.execute('''
    SELECT DISTINCT rr.article_url FROM news_intelligence ni
    JOIN rss_raw rr ON ni.raw_id=rr.id
    LEFT JOIN news_content nc ON nc.intel_id=ni.id
    WHERE ni.tier IN (\"A\",\"B\")
      AND (nc.id IS NULL OR nc.content_md='')
    ORDER BY ni.score_total DESC LIMIT 5
''').fetchall()
with open('_timing_urls.txt','w') as f:
    for u in urls: f.write(u[0]+'\n')
"
time_start=$(date +%s)
python batch.py --urls _timing_urls.txt --out _timing.jsonl \
  --rate-delay 0.3 --max-workers 2 --no-progress
time_end=$(date +%s)
echo "Batch duration: $((time_end - time_start))s"
python -c "
import json
with open('_timing.jsonl') as f:
    for line in f:
        r = json.loads(line)
        ct = r.get('cost_trace',[])
        chain = '→'.join([t['strategy'] for t in ct])
        print('✅' if r.get('ok') else '❌', chain, len(r.get('content','') or ''), r['url'][:55])
"
rm -f _timing_urls.txt _timing.jsonl
```

## Verification SQL

```sql
-- intel_id completeness (must be 0)
SELECT COUNT(*) AS null_intel_id
FROM news_content
WHERE intel_id IS NULL
  AND fetch_at > datetime('now','-2 hours','localtime');

-- Strategy distribution (last 2 hours)
SELECT fetch_strategy, COUNT(*) AS cnt
FROM news_content
WHERE fetch_at > datetime('now','-2 hours','localtime')
GROUP BY fetch_strategy
ORDER BY cnt DESC;

-- JOIN integrity (should equal total recent rows)
SELECT COUNT(*) AS joinable
FROM news_content nc
JOIN news_intelligence ni ON nc.intel_id = ni.id
WHERE nc.fetch_at > datetime('now','-2 hours','localtime');
```

# Pipeline Logging + Statistics Pattern

## Per-Step Logging

`auto-pipeline.py` writes structured logs to `pipeline.log` with per-step ok/fail counts:

```
[2026-07-14 18:30:00] PIPELINE START
[2026-07-14 18:30:03]   SYNC+SCORE: 22 ok, 0 fail (100%) total=4267
[2026-07-14 18:30:03]   RSS_FULLTEXT: 156 ok, 0 fail (100%) skipped HTTP fetch
[2026-07-14 18:35:21]   FETCH: 123 ok, 42 fail (74%) 200 URLs [direct:80/90 archive:15/25 scrapling:5/15]
[2026-07-14 18:35:21]   Strategy breakdown: direct:80/90 archive:15/25 scrapling:5/15
[2026-07-14 18:35:30]   SEARXNG_RECOVERY: 3 ok, 7 fail (30%)
[2026-07-14 18:35:35]   TAVILY_RECOVERY: 1 ok, 1 fail (50%)
[2026-07-14 18:35:36]   AGGREGATE: 71 ok, 0 fail (100%) 300 articles
[2026-07-14 18:35:37]   CLOUD_SYNC: 71 ok, 0 fail (100%) 71 events
[2026-07-14 18:35:38]   CONTENT_PUSH: 84 ok, 0 fail (100%) 84 articles
[2026-07-14 18:35:38] DONE in 323s
```

## Implementation

```python
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def step_result(name: str, ok: int, fail: int, detail: str = ""):
    pct = f"{ok*100//max(ok+fail,1)}%"
    log(f"  {name}: {ok} ok, {fail} fail ({pct}) {detail}")
```

## Strategy Breakdown in FETCH Step

Parse batch.py JSONL output, aggregate per-strategy counts across all domains:

```python
domain_stats = defaultdict(lambda: defaultdict(lambda: {"ok": 0, "fail": 0}))
source_stats = defaultdict(lambda: defaultdict(lambda: {"ok": 0, "fail": 0}))

for line in jsonl_lines:
    r = json.loads(line)
    domain = r.get("domain", "?")
    strategy = r.get("strategy_used") or "none"
    src_name = lookup_source_name(r["url"])
    if r.get("ok"):
        domain_stats[domain][strategy]["ok"] += 1
        source_stats[src_name][strategy]["ok"] += 1
    else:
        domain_stats[domain][strategy]["fail"] += 1
        source_stats[src_name][strategy]["fail"] += 1

# Format breakdown string
breakdown = " | ".join(
    f"{s}:{c['ok']}/{c['ok']+c['fail']}"
    for s, c in sorted(strat_summary.items())
)
```

## Pushing to PG fetch_stats Table

```sql
CREATE TABLE fetch_stats (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(100),
    source_name VARCHAR(200),
    strategy VARCHAR(50),
    ok_count INT DEFAULT 0,
    fail_count INT DEFAULT 0,
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Push both domain and source stats in one batch:

```python
stats_body = []
# Domain stats
for domain, strategies in domain_stats.items():
    for strategy, counts in strategies.items():
        stats_body.append({"domain": domain, "source_name": None, "strategy": strategy, ...})
# Source stats
for src_name, strategies in source_stats.items():
    for strategy, counts in strategies.items():
        stats_body.append({"domain": None, "source_name": src_name, "strategy": strategy, ...})

httpx.post(f"{CLOUD_API}/internal/fetch_stats", json=stats_body, ...)
```

## Query Examples

```sql
-- Per-source success rate
SELECT source_name, strategy,
       SUM(ok_count) as ok, SUM(fail_count) as fail,
       ROUND(SUM(ok_count)*100.0/MAX(SUM(ok_count+fail_count),1),1) as rate
FROM fetch_stats WHERE source_name IS NOT NULL
GROUP BY source_name, strategy ORDER BY SUM(ok_count+fail_count) DESC;

-- Per-domain success rate
SELECT domain, strategy,
       SUM(ok_count) as ok, SUM(fail_count) as fail,
       ROUND(SUM(ok_count)*100.0/MAX(SUM(ok_count+fail_count),1),1) as rate
FROM fetch_stats WHERE domain IS NOT NULL
GROUP BY domain, strategy ORDER BY SUM(ok_count+fail_count) DESC;
```

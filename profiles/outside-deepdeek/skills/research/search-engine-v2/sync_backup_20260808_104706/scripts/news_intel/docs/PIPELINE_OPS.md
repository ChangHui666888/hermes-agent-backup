# Pipeline 操作手册

## 完整流程

```
RSS Scanner (cron 30min)
    │
    ▼
① sync + score
    │
    ▼
② fetch content
    │
    ▼
③ aggregate events
    │
    ▼
④ cloud sync
```

## 命令

### 方式一：一键执行（含抓取）

```bash
cd C:\Users\ChangHui\AppData\Local\hermes\profiles\outside-deepdeek\skills\research\search-engine-v2\scripts

# 全流程（RSS→Score→Fetch→Aggregate）
python -m news_intel.pipeline --hours 48 --fetch
```

⚠️ 超时问题：batch.py 处理 200 URL 需 5-10 分钟，pipeline.py 默认 300s 超时。如超时：

```bash
# 仅抓取（跳过 sync/score，直接用已有数据）
python batch.py --urls <URL_LIST> --out news_intel/_fetch_tmp.jsonl --rate-delay 0.5 --max-workers 3

# 导入结果到 DB
python -c "
import json, sqlite3
db = sqlite3.connect('news_intel/news_intel.db')
with open('news_intel/_fetch_tmp.jsonl') as f:
    lines = [json.loads(l) for l in f if l.strip()]
for l in [l for l in lines if l.get('ok')]:
    r = db.execute('SELECT intel_id FROM news_content WHERE article_url=?', (l['url'],)).fetchone()
    if r:
        db.execute('UPDATE news_content SET content_md=?, content_len=?, fetch_strategy=?, fetch_cost=?, fetch_at=datetime(\"now\",\"localtime\") WHERE article_url=?',
                   (l['content'], len(l['content']), l.get('strategy_used',''), l.get('total_cost',0), l['url']))
db.commit(); print('done')
"

# 聚合
python -c "
from news_intel.db import init_db, get_db
from news_intel.aggregator import aggregate_events
init_db(); db = get_db()
db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
rows = db.execute('SELECT nc.id, rr.title, nc.summary_cn, rr.description, ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name FROM news_content nc JOIN news_intelligence ni ON nc.intel_id=ni.id JOIN rss_raw rr ON ni.raw_id=rr.id WHERE ni.tier IN (\"A\",\"B\") ORDER BY nc.id DESC LIMIT 300').fetchall()
events = aggregate_events(rows, window_hours=48)
print(f'{len(events)} events'); db.close()
"

# 同步到云端
python -c "
import json, httpx, sqlite3
db = sqlite3.connect('news_intel/news_intel.db'); db.row_factory = sqlite3.Row
rows = db.execute('SELECT * FROM event_registry').fetchall()
events = []
for r in rows:
    ev = dict(r)
    for f in ['article_ids','doc_refs','actors','keywords','related_entities','evidence','source_chain','timeline','llm_analysis']:
        if isinstance(ev.get(f), str):
            try: ev[f] = json.loads(ev[f])
            except: pass
    events.append({'event_id': ev.get('event_id'), 'title': ev.get('title',''), 'summary': ev.get('summary'), 'event_type': ev.get('event_type'), 'stage': ev.get('stage','active'), 'confidence': ev.get('confidence',0), 'coherence': ev.get('coherence',0), 'subject': {'name': ev.get('subject_name',''), 'type': ev.get('subject_type','Other')}, 'action': {'type': ev.get('action_type','OTHER'), 'detail': ev.get('action_detail')}, 'object': {'name': ev.get('object_name',''), 'type': ev.get('object_type','Other')}, 'location': {'country': ev.get('location_country')}, 'source': {'primary_source_id': ev.get('primary_source_id'), 'source_count': ev.get('source_count',0)}, 'article_count': ev.get('article_count',0), 'article_ids': ev.get('article_ids',[]), 'doc_refs': ev.get('doc_refs',[]), 'actors': ev.get('actors',[]), 'keywords': ev.get('keywords',[]), 'related_entities': ev.get('related_entities',[]), 'evidence': ev.get('evidence',[]), 'source_chain': ev.get('source_chain',[]), 'timeline': ev.get('timeline',[]), 'llm_analysis': ev.get('llm_analysis'), 'first_seen': ev.get('first_seen'), 'last_updated': ev.get('last_updated')})
db.close()
r = httpx.post('http://100.107.117.23/internal/events/batch', json=events, headers={'X-Internal-Token': 'v8-pipeline-token-2026-xK9mP2sR7wQ'}, timeout=60)
print(r.json())
"
```

### 方式二：分步执行

```bash
# 1. 仅同步评分（不抓取）
python -m news_intel.pipeline --hours 48

# 2. 查看待抓取数量
python -c "import sqlite3; db=sqlite3.connect('news_intel/news_intel.db'); r=db.execute(\"SELECT COUNT(*) FROM news_intelligence ni LEFT JOIN news_content nc ON nc.intel_id=ni.id WHERE ni.tier IN ('A','B') AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md='')\").fetchone(); print(f'{r[0]} to fetch')"

# 3. 健康检查
python news_intel/pipeline_check.py check

# 4. 查看抓取日志
# 文件: news_intel/_fetch_tmp.jsonl (每行一个JSON)
python -c "import json; lines=[json.loads(l) for l in open('news_intel/_fetch_tmp.jsonl')]; ok=sum(1 for l in lines if l.get('ok')); print(f'{len(lines)} total, {ok} ok')"
```

## GAP: 云端 PG 表缺列

云端 `events` 表缺少 `evidence`/`source_chain`/`timeline` 等字段，HTTP 推送被拒。需在云端执行：

```bash
cd /home/administrator/news-platform-v8
docker exec news-platform-v8-backend-1 python3 -c "
from apps.api.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    for col, typ in [('evidence','JSONB'),('source_chain','JSONB'),('timeline','JSONB'),('article_ids','JSONB'),('doc_refs','JSONB'),('actors','JSONB'),('keywords','JSONB'),('related_entities','JSONB'),('llm_analysis','JSONB')]:
        try: conn.execute(text(f'ALTER TABLE events ADD COLUMN IF NOT EXISTS {col} {typ}')); print(f'+ {col}')
        except: print(f'skip {col}')
    conn.commit()
"
```

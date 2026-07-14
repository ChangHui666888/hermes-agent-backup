#!/usr/bin/env python3
"""
auto-pipeline.py — 全自动最小延时管线 (RSS→Score→Fetch→Aggregate→Cloud)

触发: Hermes cron 每30分钟
延迟: ~2-5min (取决于抓取量)
输出: 实时推送到云端, Dashboard 即时更新
"""

import sys, os, time, json, sqlite3, subprocess, httpx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "news_intel"))

CLOUD_API = "http://100.107.117.23"
TOKEN = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")
BATCH_TIMEOUT = 480  # 8 minutes max for batch.py

t0 = time.time()
db_path = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# ── 1. Sync + Score (fast, ~3s) ──────────────────────────────
log("Step 1/5: Sync + Score")
subprocess.run([sys.executable, "-m", "news_intel.pipeline", "--hours", "2"],
               cwd=SCRIPT_DIR, timeout=60)
log("Done")

# ── 2. Check what needs fetching ─────────────────────────────
conn = sqlite3.connect(db_path)
to_fetch = conn.execute("""
    SELECT COUNT(*) FROM news_intelligence ni
    LEFT JOIN news_content nc ON nc.intel_id = ni.id
    WHERE ni.tier IN ('A','B')
      AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
""").fetchone()[0]
conn.close()

if to_fetch == 0:
    log("Step 2/5: Fetch — nothing to fetch, skip")
else:
    # ── 2. Fetch (batch.py, ~2-5min) ─────────────────────────
    log(f"Step 2/5: Fetch — {to_fetch} articles")
    
    # Generate URL list
    conn = sqlite3.connect(db_path)
    urls = conn.execute("""
        SELECT DISTINCT rr.article_url FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
          AND rr.article_url IS NOT NULL
          AND rr.article_url != ''
        LIMIT 200
    """).fetchall()
    conn.close()
    
    if urls:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write('\n'.join(u[0] for u in urls))
            url_file = f.name
        
        tmp_out = os.path.join(SCRIPT_DIR, "news_intel", "_fetch_tmp.jsonl")
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "batch.py"),
             "--urls", url_file, "--out", tmp_out,
             "--rate-delay", "0.5", "--max-workers", "3", "--no-progress"],
            cwd=SCRIPT_DIR, timeout=BATCH_TIMEOUT, capture_output=True, text=True
        )
        os.unlink(url_file)
        
        # Import results to DB
        if os.path.exists(tmp_out):
            ok_count = 0
            conn = sqlite3.connect(db_path)
            with open(tmp_out) as f:
                for line in f:
                    if not line.strip(): continue
                    l = json.loads(line)
                    if not l.get('ok'): continue
                    r = conn.execute("SELECT intel_id FROM news_content WHERE article_url=?", (l['url'],)).fetchone()
                    if r:
                        conn.execute("""
                            UPDATE news_content SET content_md=?, content_len=?,
                            fetch_strategy=?, fetch_cost=?,
                            fetch_at=datetime('now','localtime')
                            WHERE article_url=?
                        """, (l['content'], len(l['content']),
                              l.get('strategy_used',''), l.get('total_cost',0), l['url']))
                        ok_count += 1
            conn.commit()
            conn.close()
            log(f"Fetch done: {ok_count} imported")
    else:
        log("Fetch: no URLs")

# ── 3. Aggregate (fast, ~0.1s) ──────────────────────────────
log("Step 3/5: Aggregate")
from news_intel.db import init_db, get_db
from news_intel.aggregator import aggregate_events
init_db()
db = get_db()
db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
rows = db.execute("""
    SELECT nc.id, rr.title, nc.summary_cn, rr.description,
           ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name
    FROM news_content nc
    JOIN news_intelligence ni ON nc.intel_id = ni.id
    JOIN rss_raw rr ON ni.raw_id = rr.id
    WHERE ni.tier IN ('A','B')
    ORDER BY nc.id DESC LIMIT 300
""").fetchall()
events = aggregate_events(rows, window_hours=48)
db.close()
log(f"Aggregate: {len(events)} events")

# ── 4. Cloud Sync (HTTP, ~5s) ───────────────────────────────
log("Step 4/5: Cloud Sync")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM event_registry").fetchall()
push_events = []
for r in rows:
    ev = dict(r)
    for f in ['article_ids','doc_refs','actors','keywords','related_entities','evidence','source_chain','timeline','llm_analysis']:
        if isinstance(ev.get(f), str):
            try: ev[f] = json.loads(ev[f])
            except: pass
    push_events.append({
        'event_id': ev.get('event_id'), 'title': ev.get('title',''), 'summary': ev.get('summary'),
        'event_type': ev.get('event_type'), 'stage': ev.get('stage','active'),
        'confidence': ev.get('confidence',0), 'coherence': ev.get('coherence',0),
        'subject': {'name': ev.get('subject_name',''), 'type': ev.get('subject_type','Other')},
        'action': {'type': ev.get('action_type','OTHER'), 'detail': ev.get('action_detail')},
        'object': {'name': ev.get('object_name',''), 'type': ev.get('object_type','Other')},
        'location': {'country': ev.get('location_country')},
        'source': {'primary_source_id': ev.get('primary_source_id'), 'source_count': ev.get('source_count',0)},
        'article_count': ev.get('article_count',0), 'article_ids': ev.get('article_ids',[]),
        'doc_refs': ev.get('doc_refs',[]), 'actors': ev.get('actors',[]),
        'keywords': ev.get('keywords',[]), 'related_entities': ev.get('related_entities',[]),
        'evidence': ev.get('evidence',[]), 'source_chain': ev.get('source_chain',[]),
        'timeline': ev.get('timeline',[]), 'llm_analysis': ev.get('llm_analysis'),
        'first_seen': ev.get('first_seen'), 'last_updated': ev.get('last_updated'),
    })
conn.close()

try:
    r = httpx.post(f"{CLOUD_API}/internal/events/batch", json=push_events,
                   headers={'X-Internal-Token': TOKEN}, timeout=30)
    log(f"Cloud sync: {r.json()}")
except Exception as e:
    log(f"Cloud sync failed: {e}")

# ── 5. Summary ──────────────────────────────────────────────
elapsed = time.time() - t0
log(f"Done in {elapsed:.0f}s")

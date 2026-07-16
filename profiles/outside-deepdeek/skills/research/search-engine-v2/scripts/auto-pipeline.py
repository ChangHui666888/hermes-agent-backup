#!/usr/bin/env python3
"""
auto-pipeline.py — 全自动管线 (RSS→Score→Fetch→Aggregate→Cloud)

Features:
- Per-step statistics written to pipeline.log
- Per-domain strategy stats pushed to PG fetch_stats table
"""

import sys, os, time, json, sqlite3, subprocess, httpx
from collections import defaultdict, Counter
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "news_intel"))

CLOUD_API = "http://100.107.117.23"
TOKEN = os.environ.get("NEWS_API_TOKEN") or ""
BATCH_TIMEOUT = 600
LOG_FILE = os.path.join(SCRIPT_DIR, "pipeline.log")
db_path = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")

stats = {"steps": []}


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def step_result(name: str, ok: int, fail: int, detail: str = ""):
    pct = f"{ok*100//max(ok+fail,1)}%"
    log(f"  {name}: {ok} ok, {fail} fail ({pct}) {detail}")
    stats["steps"].append({"step": name, "ok": ok, "fail": fail, "detail": detail, "time": datetime.now().isoformat()})


# ═══════════════════════════════════════════════════════════════
t0 = time.time()
log("=" * 60)
log("PIPELINE START")
log("=" * 60)

# ── 0. Cleanup: delete empty placeholder rows ──────────────
log("Step 0: Cleanup placeholder rows")
try:
    conn = sqlite3.connect(db_path)
    deleted = conn.execute("""
        DELETE FROM news_content
        WHERE fetch_strategy IS NULL
          AND (content_md IS NULL OR content_md = '')
          AND retry_count >= 3
    """).rowcount
    conn.commit()
    conn.close()
    if deleted:
        log(f"  CLEANUP: {deleted} exhausted placeholder rows deleted")
except Exception as e:
    log(f"  Cleanup: {e}")

# ── 1. Sync + Score ────────────────────────────────────────
log("Step 1/6: Sync + Score")
try:
    subprocess.run([sys.executable, "-m", "news_intel.pipeline", "--hours", "2"],
                   cwd=SCRIPT_DIR, timeout=120, capture_output=True)
    conn = sqlite3.connect(db_path)
    new_scored = conn.execute("SELECT COUNT(*) FROM news_intelligence WHERE scored_at > datetime('now','-10 minutes','localtime')").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM news_intelligence").fetchone()[0]
    conn.close()
    step_result("SYNC+SCORE", new_scored, 0, f"total={total}")
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("SYNC+SCORE", 0, 1, str(e)[:80])

# ── 2. RSS FullText pre-check ──────────────────────────────
log("Step 2/6: RSS FullText")
try:
    conn = sqlite3.connect(db_path)
    rss_ok = 0
    rows = conn.execute("""
        SELECT ni.id, rr.article_url, rr.description
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
          AND rr.description IS NOT NULL AND length(rr.description) >= 200
    """).fetchall()
    for row in rows:
        desc = (row[2] or "").strip()
        html_ratio = (desc.count("<") + desc.count(">")) / max(len(desc), 1)
        if html_ratio < 0.3:
            conn.execute("""
                INSERT INTO news_content (intel_id, article_url, content_md, content_len,
                    fetch_strategy, fetch_cost, retry_count, fetch_at)
                VALUES (?, ?, ?, ?, 'rss_fulltext', 0, 0, datetime('now','localtime'))
                ON CONFLICT(article_url) DO UPDATE SET
                    content_md=excluded.content_md, content_len=excluded.content_len,
                    fetch_strategy='rss_fulltext', fetch_cost=0, retry_count=0,
                    fetch_at=datetime('now','localtime')
            """, (row[0], row[1], desc, len(desc)))
            rss_ok += 1
    conn.commit()
    conn.close()
    step_result("RSS_FULLTEXT", rss_ok, 0, "skipped HTTP fetch")
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("RSS_FULLTEXT", 0, 0, str(e)[:80])

# ── 3. Fetch (batch.py) ────────────────────────────────────
log("Step 3/6: Fetch (batch.py)")
try:
    conn = sqlite3.connect(db_path)
    urls = conn.execute("""
        SELECT DISTINCT rr.article_url FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
          AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
          AND rr.article_url IS NOT NULL AND rr.article_url != ''
        LIMIT 50
    """).fetchall()
    conn.close()

    if not urls:
        log("  FETCH: no URLs to fetch (all candidates exhausted or already fetched)")
        step_result("FETCH", 0, 0, "no URLs to fetch")
    else:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write('\n'.join(u[0] for u in urls))
            url_file = f.name

        tmp_out = os.path.join(SCRIPT_DIR, "news_intel", "_fetch_tmp.jsonl")
        try:
            result = subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, "batch.py"),
                                     "--urls", url_file, "--out", tmp_out,
                                     "--rate-delay", "0.5", "--max-workers", "4", "--no-progress"],
                                    cwd=SCRIPT_DIR, timeout=BATCH_TIMEOUT, capture_output=True, text=True)
            if result.returncode != 0:
                stderr_tail = (result.stderr or "")[-500:]
                log(f"  batch.py exited {result.returncode}: {stderr_tail}")
        except subprocess.TimeoutExpired:
            log(f"  batch.py timed out after {BATCH_TIMEOUT}s — recovery will still run")
        os.unlink(url_file)

        if os.path.exists(tmp_out):
            ok_count = 0
            fail_count = 0
            domain_stats = defaultdict(lambda: defaultdict(lambda: {"ok": 0, "fail": 0}))
            source_stats = defaultdict(lambda: defaultdict(lambda: {"ok": 0, "fail": 0}))

            conn = sqlite3.connect(db_path)
            with open(tmp_out) as f:
                for line in f:
                    if not line.strip(): continue
                    r = json.loads(line)
                    domain = r.get("domain", "?")
                    strategy = r.get("strategy_used") or "none"
                    # Look up RSS source name
                    src_row = conn.execute("""
                        SELECT rr.source_name FROM rss_raw rr
                        JOIN news_intelligence ni ON ni.raw_id = rr.id
                        JOIN news_content nc ON nc.intel_id = ni.id
                        WHERE nc.article_url = ?
                    """, (r["url"],)).fetchone()
                    src_name = src_row[0] if src_row else "?"
                    if r.get("ok"):
                        ok_count += 1
                        domain_stats[domain][strategy]["ok"] += 1
                        source_stats[src_name][strategy]["ok"] += 1
                        conn.execute(
                            "INSERT INTO news_content (intel_id, article_url, content_md, content_len, fetch_strategy, fetch_cost, retry_count, fetch_at) VALUES (?, ?, ?, ?, ?, ?, 0, datetime('now','localtime')) ON CONFLICT(article_url) DO UPDATE SET content_md=excluded.content_md, content_len=excluded.content_len, fetch_strategy=excluded.fetch_strategy, fetch_cost=excluded.fetch_cost, retry_count=0, fetch_at=excluded.fetch_at",
                            (intel_row[0], r["url"], r["content"], len(r["content"]), strategy, r.get("total_cost", 0))
                        ) if (intel_row := conn.execute("SELECT intel_id FROM news_content WHERE article_url=?", (r["url"],)).fetchone()) else conn.execute(
                            "INSERT INTO news_content (article_url, content_md, content_len, fetch_strategy, fetch_cost, retry_count, fetch_at) VALUES (?, ?, ?, ?, ?, 0, datetime('now','localtime'))",
                            (r["url"], r["content"], len(r["content"]), strategy, r.get("total_cost", 0))
                        )
                    else:
                        fail_count += 1
                        domain_stats[domain][strategy]["fail"] += 1
                        source_stats[src_name][strategy]["fail"] += 1
                        # Increment retry; mark exhausted after 3 failures
                        conn.execute("""
                            UPDATE news_content SET retry_count = COALESCE(retry_count,0) + 1
                            WHERE article_url = ?
                        """, (r["url"],))
                        conn.execute("""
                            UPDATE news_content SET fetch_strategy = 'exhausted'
                            WHERE article_url = ? AND COALESCE(retry_count,0) >= 3
                        """, (r["url"],))
            conn.commit()
            conn.close()

            # Strategy breakdown
            strat_summary = defaultdict(lambda: {"ok": 0, "fail": 0})
            for d in domain_stats.values():
                for s, c in d.items():
                    strat_summary[s]["ok"] += c["ok"]
                    strat_summary[s]["fail"] += c["fail"]
            breakdown = " | ".join(
                f"{s}:{c['ok']}/{c['ok']+c['fail']}"
                for s, c in sorted(strat_summary.items())
            )
            step_result("FETCH", ok_count, fail_count, f"{len(urls)} URLs [{breakdown}]")
            log(f"  Strategy breakdown: {breakdown}")

            # Push domain + source stats to PG
            if TOKEN:
                try:
                    stats_body = []
                    for domain, strategies in domain_stats.items():
                        for strategy, counts in strategies.items():
                            stats_body.append({
                                "domain": domain, "source_name": None, "strategy": strategy,
                                "ok": counts["ok"], "fail": counts["fail"],
                                "run_at": datetime.now().isoformat(),
                            })
                    for src_name, strategies in source_stats.items():
                        for strategy, counts in strategies.items():
                            stats_body.append({
                                "domain": None, "source_name": src_name, "strategy": strategy,
                                "ok": counts["ok"], "fail": counts["fail"],
                                "run_at": datetime.now().isoformat(),
                            })
                    if stats_body:
                        httpx.post(f"{CLOUD_API}/internal/fetch_stats", json=stats_body,
                                   headers={"X-Internal-Token": TOKEN}, timeout=10)
                        log(f"  Domain stats pushed: {len(stats_body)} records")
                except Exception:
                    pass

    # ── 3.5 Comprehensive Recovery Pass ──────────────────────
    # Covers ALL empty content rows (not just those in current batch).
    # Always runs — even if batch.py timed out or no URLs were fetched.
    log("Step 3.5: Recovery (SearXNG + Tavily)")
    _TAVILY_KEY = os.environ.get("TAVILY_API_KEY") or ""
    if not _TAVILY_KEY:
        log("  Tavily recovery disabled: TAVILY_API_KEY not set")
    searxng_ok = searxng_fail = tavily_ok = tavily_fail = 0

    def _recover_searxng(title: str, intel_id: int, url: str) -> bool:
        q = (title or url)[:80]
        resp = httpx.get("http://100.107.117.23:8080/search",
                          params={"q": q, "format": "json"},
                          headers={"User-Agent": "NewsIntelBot/1.0"}, timeout=10)
        data = resp.json()
        for alt in data.get("results", [])[:2]:
            alt_url = alt.get("url", "")
            if alt_url and alt_url != url:
                r2 = httpx.get(alt_url, headers={"User-Agent": "Mozilla/5.0 Chrome/131"}, timeout=10)
                if r2.status_code == 200 and len(r2.text) > 500:
                    from core.fetchers import _extract_main_text
                    content = _extract_main_text(r2.text, url=alt_url)
                    if content and len(content) > 200:
                        c = sqlite3.connect(db_path)
                        c.execute("""
                            INSERT INTO news_content (intel_id, article_url, content_md, content_len, fetch_strategy, fetch_cost, retry_count, fetch_at)
                            VALUES (?, ?, ?, ?, 'searxng_alt', 2, 0, datetime('now','localtime'))
                            ON CONFLICT(article_url) DO UPDATE SET content_md=excluded.content_md, content_len=excluded.content_len,
                            fetch_strategy='searxng_alt', fetch_cost=2, retry_count=0, fetch_at=excluded.fetch_at
                        """, (intel_id, url, content, len(content)))
                        c.commit(); c.close()
                        return True
        return False

    def _recover_tavily(title: str, intel_id: int, url: str) -> bool:
        if not _TAVILY_KEY:
            return False
        q = (title or url)[:100]
        resp = httpx.post("https://api.tavily.com/search", json={
            "api_key": _TAVILY_KEY, "query": q, "search_depth": "basic",
            "max_results": 2, "include_answer": True,
        }, timeout=15)
        data = resp.json()
        answer = data.get("answer", "")
        if answer and len(answer) > 100:
            content = f"[Tavily]\n\n{answer}"
            c = sqlite3.connect(db_path)
            c.execute("""
                INSERT INTO news_content (intel_id, article_url, content_md, content_len, fetch_strategy, fetch_cost, retry_count, fetch_at)
                VALUES (?, ?, ?, ?, 'tavily', 5, 0, datetime('now','localtime'))
                ON CONFLICT(article_url) DO UPDATE SET content_md=excluded.content_md, content_len=excluded.content_len,
                fetch_strategy='tavily', fetch_cost=5, retry_count=0, fetch_at=excluded.fetch_at
            """, (intel_id, url, content, len(content)))
            c.commit(); c.close()
            return True
        return False

    try:
        conn = sqlite3.connect(db_path)
        # SearXNG: score 80-89, max 10
        searxng_candidates = conn.execute("""
            SELECT rr.article_url, ni.id, ni.score_total, rr.title
            FROM news_intelligence ni
            JOIN rss_raw rr ON ni.raw_id = rr.id
            LEFT JOIN news_content nc ON nc.intel_id = ni.id
            WHERE ni.tier IN ('A','B') AND ni.score_total >= 80 AND ni.score_total < 90
              AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
              AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
              AND (nc.retry_count IS NULL OR nc.retry_count < 3)
            LIMIT 10
        """).fetchall()

        for url, intel_id, score, title in searxng_candidates:
            try:
                if _recover_searxng(title, intel_id, url):
                    searxng_ok += 1
                else:
                    searxng_fail += 1
                    conn.execute("UPDATE news_content SET retry_count = COALESCE(retry_count,0)+1 WHERE article_url=?", (url,))
            except Exception:
                searxng_fail += 1

        # Tavily: score >=90, max 5 (only if key is configured)
        if _TAVILY_KEY:
            tavily_candidates = conn.execute("""
                SELECT rr.article_url, ni.id, ni.score_total, rr.title
                FROM news_intelligence ni
                JOIN rss_raw rr ON ni.raw_id = rr.id
                LEFT JOIN news_content nc ON nc.intel_id = ni.id
                WHERE ni.tier IN ('A','B') AND ni.score_total >= 90
                  AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
                  AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
                  AND (nc.retry_count IS NULL OR nc.retry_count < 3)
                LIMIT 5
            """).fetchall()

            for url, intel_id, score, title in tavily_candidates:
                try:
                    if _recover_tavily(title, intel_id, url):
                        tavily_ok += 1
                    else:
                        tavily_fail += 1
                        conn.execute("UPDATE news_content SET retry_count = COALESCE(retry_count,0)+1 WHERE article_url=?", (url,))
                except Exception:
                    tavily_fail += 1

        conn.commit()
        conn.close()

        if searxng_ok + searxng_fail > 0:
            step_result("SEARXNG_RECOVERY", searxng_ok, searxng_fail)
        if tavily_ok + tavily_fail > 0:
            step_result("TAVILY_RECOVERY", tavily_ok, tavily_fail)
    except Exception as e:
        log(f"  Recovery: {e}")
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("FETCH", 0, 1, str(e)[:80])

# ── 4. Aggregate ───────────────────────────────────────────
log("Step 4/6: Aggregate")
try:
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
    step_result("AGGREGATE", len(events), 0, f"{len(rows)} articles")
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("AGGREGATE", 0, 1, str(e)[:80])

# ── 5. Cloud Sync ──────────────────────────────────────────
log("Step 5/6: Cloud Sync")
try:
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
    if not TOKEN:
        log("  CLOUD_SYNC skipped: NEWS_API_TOKEN not set")
        step_result("CLOUD_SYNC", 0, 0, "no token configured")
    else:
        r = httpx.post(f"{CLOUD_API}/internal/events/batch", json=push_events,
                       headers={'X-Internal-Token': TOKEN}, timeout=30)
        if r.status_code >= 400:
            log(f"  CLOUD_SYNC: HTTP {r.status_code}: {r.text[:200]}")
            step_result("CLOUD_SYNC", 0, len(push_events), f"HTTP {r.status_code}")
        else:
            result = r.json()
            step_result("CLOUD_SYNC", result.get("ok", 0), result.get("fail", 0), f"{len(push_events)} events")
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("CLOUD_SYNC", 0, 1, str(e)[:80])

# ── 6. Article content push ────────────────────────────────
log("Step 6/6: Article content to PG")
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT rr.article_url, rr.title, nc.content_md, nc.content_len,
               ni.score_total, ni.tier, rr.source_name, rr.source_domain
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE nc.content_len > 0
    """).fetchall()
    if rows:
        if not TOKEN:
            log("  CONTENT_PUSH skipped: NEWS_API_TOKEN not set")
            step_result("CONTENT_PUSH", 0, 0, "no token configured")
        else:
            body = [{'url':r[0],'title':r[1],'content_md':r[2],'score_total':r[4],'tier':r[5],
                     'source_name':r[6],'source_domain':r[7]} for r in rows]
            r = httpx.post(f"{CLOUD_API}/internal/news/batch", json=body,
                            headers={'X-Internal-Token': TOKEN}, timeout=30)
            if r.status_code >= 400:
                log(f"  CONTENT_PUSH: HTTP {r.status_code}: {r.text[:200]}")
                step_result("CONTENT_PUSH", 0, len(rows), f"HTTP {r.status_code}")
            else:
                result = r.json()
                step_result("CONTENT_PUSH", result.get("ok", 0), result.get("fail", 0), f"{len(rows)} articles")
    conn.close()
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("CONTENT_PUSH", 0, 1, str(e)[:80])

# ── Summary ─────────────────────────────────────────────────
elapsed = time.time() - t0
log(f"DONE in {elapsed:.0f}s")
log("=" * 60)

#!/usr/bin/env python3
"""
auto-pipeline.py — 全自动管线 (RSS→Score→Fetch→Aggregate→Cloud)

Features:
- Per-step statistics written to pipeline.log
- Per-domain strategy stats pushed to PG fetch_stats table
- 配置从本地 ~/.hermes/pipeline-config.json 读取 (由 config-agent 同步)
"""

import sys, os, time, json, sqlite3, subprocess, httpx
from collections import defaultdict, Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "news_intel"))

# 读取本地配置（VPS挂了也能用最近配置）
try:
    from config.loader import load_config, get_setting
    CONFIG = load_config()
except Exception:
    CONFIG = {}

def cfg(key, default):
    return get_setting(CONFIG, key, default) if CONFIG else default

# 环境参数（IP 等不硬编码）
try:
    from config.env import CLOUD_API, INTERNAL_TOKEN
except Exception:
    CLOUD_API = "http://100.107.117.23"
    INTERNAL_TOKEN = "v8-pipeline-token-2026-xK9mP2sR7wQ"

TOKEN = os.environ.get("NEWS_API_TOKEN") or INTERNAL_TOKEN
BATCH_TIMEOUT = cfg("pipeline.batch_timeout", 600)
LOG_FILE = os.path.join(SCRIPT_DIR, "pipeline.log")
db_path = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")

stats = {"steps": []}

# ── 进程锁（防多实例并发）────────────────────────────────────
LOCK_FILE = os.path.join(SCRIPT_DIR, ".pipeline.lock")

def acquire_lock() -> bool:
    """非阻塞获取进程锁。已有实例在跑则返回 False。

    Windows-compatible: 不使用 os.kill(pid,0)（Windows 不支持 signal 0，
    对存活进程也会报错）。改用文件时间戳 + BATCH_TIMEOUT 判断：
    如果锁文件存在且修改时间距今 < BATCH_TIMEOUT，视为活跃锁。
    """
    import time
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            mtime = os.path.getmtime(LOCK_FILE)
            age = time.time() - mtime
            if age < BATCH_TIMEOUT:
                log(f"[SKIP] 已有 pipeline 在跑 ({age:.0f}s 前开始)，跳过本次")
                return False
        except OSError:
            pass
        # 锁文件已过期，清理并重试
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass
        return acquire_lock()

def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

import atexit
atexit.register(release_lock)


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

# 进程锁：已有实例则跳过
if not acquire_lock():
    sys.exit(0)

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

# ── 0.5. Backlog Report ───────────────────────────────────
log("Step 0.5: Backlog report")
try:
    conn = sqlite3.connect(db_path)
    backlog_rows = conn.execute("""
        SELECT
            CASE
                WHEN ni.score_total >= 90 THEN 'A (90-100)'
                WHEN ni.score_total >= 80 THEN 'B+ (80-89)'
                WHEN ni.score_total >= 70 THEN 'B (70-79)'
                WHEN ni.score_total >= 60 THEN 'B- (60-69)'
                ELSE 'C (<60)'
            END as bucket,
            COUNT(*) as cnt
        FROM news_intelligence ni
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
        GROUP BY bucket
        ORDER BY AVG(ni.score_total) DESC
    """).fetchall()
    exhausted = conn.execute("""
        SELECT COUNT(*) FROM news_content
        WHERE (content_md IS NULL OR content_md = '')
          AND retry_count >= 3
    """).fetchone()[0]
    conn.close()
    parts = ['{}={}'.format(bucket, int(cnt)) for bucket, cnt in backlog_rows if int(cnt) > 0]
    log("  BACKLOG: " + ' | '.join(parts))
    log("  EXHAUSTED: {} (3次失败, 不再重试)".format(exhausted))
except Exception as e:
    log("  Backlog: " + str(e))

# ── 1. Sync + Score ────────────────────────────────────────
log("Step 1/6: Sync + Score")
try:
    subprocess.run([sys.executable, "-m", "news_intel.pipeline", "--hours", str(cfg("pipeline.sync_hours", 2))],
                   cwd=SCRIPT_DIR, timeout=240, capture_output=True)
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
# auto-pipeline.py 只负责：查候选 → 调 batch.py 子进程 → 解析结果写 DB → 记日志。
# 任何实际抓取（HTTP 请求、搜索 API、正文抽取）都必须在 batch.py / core.fetchers 里实现。
log("Step 3/6: Fetch (batch.py)")
try:
    conn = sqlite3.connect(db_path)
    candidates = conn.execute("""
        SELECT DISTINCT rr.article_url, ni.id FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
          AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
          AND rr.article_url IS NOT NULL AND rr.article_url != ''
          AND rr.article_url NOT LIKE '%/video/%'
          AND rr.article_url NOT LIKE '%/videos/%'
        LIMIT {}
    """.format(cfg("pipeline.batch_size", 20))).fetchall()
    conn.close()
    # url -> intel_id，直接来自本次查询，落库时不再反查，避免漏写 intel_id
    url_to_intel = {u: i for u, i in candidates}

    if not candidates:
        log("  FETCH: no URLs to fetch (all candidates exhausted or already fetched)")
        step_result("FETCH", 0, 0, "no URLs to fetch")
    else:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write('\n'.join(u for u, i in candidates))
            url_file = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
            tmp_out = f.name

        try:
            result = subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, "batch.py"),
                                     "--urls", url_file, "--out", tmp_out,
                                     "--rate-delay", str(cfg("pipeline.rate_delay", 0.3)),
                                     "--max-workers", str(cfg("pipeline.max_workers", 5)), "--no-progress"],
                                    cwd=SCRIPT_DIR, timeout=BATCH_TIMEOUT, capture_output=True, text=True)
            if result.returncode != 0:
                stderr_tail = (result.stderr or "")[-500:]
                log(f"  batch.py exited {result.returncode}: {stderr_tail}")
        except subprocess.TimeoutExpired:
            log(f"  batch.py timed out after {BATCH_TIMEOUT}s")
        finally:
            os.unlink(url_file)

        if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
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
                    intel_id = url_to_intel.get(r["url"])
                    # Look up RSS source name (for stats breakdown only)
                    src_row = conn.execute("""
                        SELECT rr.source_name FROM rss_raw rr
                        JOIN news_intelligence ni ON ni.raw_id = rr.id
                        WHERE ni.id = ?
                    """, (intel_id,)).fetchone() if intel_id is not None else None
                    src_name = src_row[0] if src_row else "?"
                    if r.get("ok"):
                        ok_count += 1
                        domain_stats[domain][strategy]["ok"] += 1
                        source_stats[src_name][strategy]["ok"] += 1
                        conn.execute(
                            "INSERT INTO news_content (intel_id, article_url, content_md, content_len, fetch_strategy, fetch_cost, retry_count, fetch_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, 0, datetime('now','localtime')) "
                            "ON CONFLICT(article_url) DO UPDATE SET content_md=excluded.content_md, content_len=excluded.content_len, "
                            "fetch_strategy=excluded.fetch_strategy, fetch_cost=excluded.fetch_cost, retry_count=0, fetch_at=excluded.fetch_at",
                            (intel_id, r["url"], r["content"], len(r["content"]), strategy, r.get("total_cost", 0))
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
            step_result("FETCH", ok_count, fail_count, f"{len(candidates)} URLs [{breakdown}]")
            log(f"  Strategy breakdown: {breakdown}")

            # URL 列表日志（成功+失败）
            for line in open(tmp_out):
                if not line.strip(): continue
                r = json.loads(line)
                url = r.get("url", "")[:65]
                if r.get("ok"):
                    strat = r.get("strategy_used", "?")
                    clen = len(r.get("content", "") or "")
                    log(f"    ✅ [{strat}] {clen}c {url}")
                else:
                    ct = r.get("cost_trace", [])
                    # 取最后一个尝试的策略和错误
                    last = ct[-1] if ct else {}
                    last_strat = last.get("strategy", "?")
                    last_err = (last.get("error", "") or "")[:30]
                    # 策略链摘要
                    chain = "→".join([t["strategy"] for t in ct])
                    log(f"    ❌ [{last_strat}] {last_err}  chain={chain}  {url}")

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
        os.unlink(tmp_out)
except Exception as e:
    log(f"  FAILED: {e}")
    step_result("FETCH", 0, 1, str(e)[:80])

# ── 3.5 Comprehensive Recovery Pass ──────────────────────
# 独立的 try 块：Step 3 出异常不会跳过本步骤。
# 覆盖全部空内容行（不只是本轮 batch 里的），batch.py 超时或没有可抓 URL 时也照常执行。
# 本步骤只做：查候选 → 调 batch.py（--force-strategy 走恢复策略）→ 解析结果写 DB → 记日志。
# 不在这里直接发任何 HTTP 请求 —— 抓取逻辑全部在 core/fetchers.py 的 searxng_alt / tavily 策略里。
log("Step 3.5: Recovery (SearXNG + Tavily)")


def _run_recovery_batch(candidates, strategy_order, timeout_s, label, video=False, workers=3):
    """调用 batch.py 子进程完成一批恢复抓取，返回 (ok_count, fail_count)。
    candidates: [(article_url, intel_id, title), ...]
    video=True → 传 --video 走视频专用链路 (browser+stealth 抓转写)。
    """
    if not candidates:
        return 0, 0

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        for url, intel_id, title in candidates:
            f.write(f"{url}\t{(title or '').replace(chr(9), ' ')}\n")
        url_file = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
        out_file = f.name

    try:
        cmd = [sys.executable, os.path.join(SCRIPT_DIR, "batch.py"),
               "--urls", url_file, "--out", out_file,
               "--force-strategy", strategy_order,
               "--rate-delay", "0.3", "--max-workers", str(workers), "--no-progress"]
        if video:
            cmd.append("--video")
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, timeout=timeout_s, capture_output=True, text=True)
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-500:]
            log(f"  {label} batch.py exited {result.returncode}: {stderr_tail}")
    except subprocess.TimeoutExpired:
        log(f"  {label} batch.py timed out after {timeout_s}s")
    finally:
        os.unlink(url_file)

    url_to_intel = {u: i for u, i, t in candidates}
    ok = fail = 0
    strat_summary = defaultdict(lambda: {"ok": 0, "fail": 0})
    if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
        conn2 = sqlite3.connect(db_path)
        with open(out_file) as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                intel_id = url_to_intel.get(r["url"])
                url_short = (r.get("url") or "")[:65]
                if r.get("ok"):
                    ok += 1
                    strat = r.get("strategy_used") or label
                    strat_summary[strat]["ok"] += 1
                    conn2.execute("""
                        INSERT INTO news_content (intel_id, article_url, content_md, content_len, fetch_strategy, fetch_cost, retry_count, fetch_at)
                        VALUES (?, ?, ?, ?, ?, ?, 0, datetime('now','localtime'))
                        ON CONFLICT(article_url) DO UPDATE SET content_md=excluded.content_md, content_len=excluded.content_len,
                        fetch_strategy=excluded.fetch_strategy, fetch_cost=excluded.fetch_cost, retry_count=0, fetch_at=excluded.fetch_at
                    """, (intel_id, r["url"], r["content"], len(r["content"]), strat, r.get("total_cost", 0)))
                    log(f"    ✅ [{strat}] {len(r['content'])}c {url_short}")
                else:
                    fail += 1
                    ct = r.get("cost_trace", [])
                    last = ct[-1] if ct else {}
                    last_strat = last.get("strategy", "?")
                    last_err = (last.get("error", "") or "")[:30]
                    chain = "→".join([t["strategy"] for t in ct]) or "?"
                    strat_summary[last_strat]["fail"] += 1
                    conn2.execute("UPDATE news_content SET retry_count = COALESCE(retry_count,0)+1 WHERE article_url=?", (r["url"],))
                    log(f"    ❌ [{last_strat}] {last_err}  chain={chain}  {url_short}")
        conn2.commit()
        conn2.close()
        # 策略明细 (类似 Step 3)
        breakdown = " | ".join(f"{s}:{c['ok']}/{c['ok']+c['fail']}" for s, c in sorted(strat_summary.items()))
        if breakdown:
            log(f"  {label} Strategy breakdown: {breakdown}")
    if os.path.exists(out_file):
        os.unlink(out_file)
    return ok, fail


try:
    conn = sqlite3.connect(db_path)
    # SearXNG 替代源: score 80-89, max 10
    searxng_candidates = conn.execute("""
        SELECT rr.article_url, ni.id, rr.title
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B') AND ni.score_total >= 80 AND ni.score_total < 90
          AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
          AND (nc.retry_count IS NULL OR nc.retry_count < 3)
          AND rr.article_url NOT LIKE '%/video/%' AND rr.article_url NOT LIKE '%/videos/%'
        LIMIT 10
    """).fetchall()
    # Tavily: score >=90, max 5 (视频由 Step 3.6 专属处理)
    tavily_candidates = conn.execute("""
        SELECT rr.article_url, ni.id, rr.title
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B') AND ni.score_total >= 90
          AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
          AND (nc.retry_count IS NULL OR nc.retry_count < 3)
          AND rr.article_url NOT LIKE '%/video/%' AND rr.article_url NOT LIKE '%/videos/%'
        LIMIT 5
    """).fetchall()
    conn.close()

    if not searxng_candidates and not tavily_candidates:
        log("  RECOVERY: no backlog articles to recover (all caught up)")
    else:
        if searxng_candidates:
            searxng_ok, searxng_fail = _run_recovery_batch(
                searxng_candidates, "searxng_alt,tavily", BATCH_TIMEOUT, "SEARXNG_RECOVERY")
            if searxng_ok + searxng_fail > 0:
                step_result("SEARXNG_RECOVERY", searxng_ok, searxng_fail)
        if tavily_candidates:
            tavily_ok, tavily_fail = _run_recovery_batch(
                tavily_candidates, "tavily", BATCH_TIMEOUT, "TAVILY_RECOVERY")
            if tavily_ok + tavily_fail > 0:
                step_result("TAVILY_RECOVERY", tavily_ok, tavily_fail)
except Exception as e:
    log(f"  Recovery: {e}")


# ── 3.6. Video Fetch (browser+stealth, 受预算上限) ──────────
# 视频 URL 在 Step 3 主批被 SQL 排除，单独在此处理：
# 仅 A/B 级、score≥video_min_score、无内容、非 exhausted、每轮上限 video_batch_size。
# 走 browser+stealth 抓转写，2 worker 并发，子批超时最多 5 分钟，防撑爆 15 分钟 cron 预算。
log("Step 3.6: Video Fetch (browser)")
if cfg("crawl.video_enabled", True):
    try:
        video_patterns = cfg("crawl.video_patterns", ["/video/", "/videos/"])
        like_conds = " OR ".join("rr.article_url LIKE ?" for _ in video_patterns)
        like_params = [f"%{p}%" for p in video_patterns]
        conn = sqlite3.connect(db_path)
        vids = conn.execute(f"""
            SELECT rr.article_url, ni.id, rr.title
            FROM news_intelligence ni
            JOIN rss_raw rr ON ni.raw_id = rr.id
            LEFT JOIN news_content nc ON nc.intel_id = ni.id
            WHERE ni.tier IN ('A','B')
              AND ni.score_total >= ?
              AND (nc.fetch_strategy != 'exhausted' OR nc.fetch_strategy IS NULL)
              AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
              AND (nc.retry_count IS NULL OR nc.retry_count < 3)
              AND ({like_conds})
            ORDER BY ni.score_total DESC
            LIMIT ?
        """, (cfg("crawl.video_min_score", 60), *like_params, cfg("crawl.video_batch_size", 6))).fetchall()
        conn.close()

        if not vids:
            log("  VIDEO_FETCH: 无待抓视频 (backlog 清空)")
        else:
            video_strategy = ",".join(cfg("crawl.video_strategy", ["browser", "archive", "jina", "tavily"]))
            vworkers = cfg("crawl.video_workers", 2)
            vtimeout = int(cfg("crawl.video_timeout", 420))  # 视频子批超时 (默认 7 分钟, browser 挂起+兜底单条可达 ~110s)
            vok, vfail = _run_recovery_batch(
                vids, video_strategy, vtimeout, "VIDEO_FETCH", video=True, workers=vworkers)
            if vok + vfail > 0:
                step_result("VIDEO_FETCH", vok, vfail, f"{len(vids)} videos [{video_strategy}]")
    except Exception as e:
        log(f"  VIDEO_FETCH FAILED: {e}")
        step_result("VIDEO_FETCH", 0, 1, str(e)[:80])


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

# ── 5+6. Cloud Sync + Content Push (并行) ─────────────────
log("Step 5+6/6: Cloud Sync + Content Push (并行)")
def _do_step5():
    """Cloud Sync - 只读 event_registry + HTTP POST"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM event_registry
            WHERE last_updated > datetime('now', '-48 hours', 'localtime')
               OR first_seen > datetime('now', '-48 hours', 'localtime')
        """).fetchall()
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
            return
        # 网络延迟 ~5s, 每次POST是主要耗时
        # 事件单个体积~800B, 50个仅~40KB, 远低于nginx 50MB限制
        CHUNK = cfg("pipeline.cloud_chunk", 50)
        push_ok = push_fail = 0
        for i in range(0, len(push_events), CHUNK):
            chunk = push_events[i:i+CHUNK]
            try:
                r = httpx.post(f"{CLOUD_API}/internal/events/batch", json=chunk,
                               headers={'X-Internal-Token': TOKEN}, timeout=60)
                if r.status_code >= 400:
                    log(f"  CLOUD_SYNC chunk {i//CHUNK+1}: HTTP {r.status_code}")
                    push_fail += len(chunk)
                else:
                    result = r.json()
                    push_ok += result.get("ok", 0)
                    push_fail += result.get("fail", 0)
            except Exception as e:
                log(f"  CLOUD_SYNC chunk {i//CHUNK+1}: {e}")
                push_fail += len(chunk)
        step_result("CLOUD_SYNC", push_ok, push_fail, f"{len(push_events)} events in {(len(push_events)+CHUNK-1)//CHUNK} chunks")
    except Exception as e:
        log(f"  CLOUD_SYNC FAILED: {e}")
        step_result("CLOUD_SYNC", 0, 1, str(e)[:80])

def _do_step6():
    """Content Push - 只读 news_content + HTTP POST"""
    try:
        conn = sqlite3.connect(db_path)
        show_start = datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute("""
            SELECT rr.article_url, rr.title, nc.content_md, nc.content_len,
                   ni.score_total, ni.tier, rr.source_name, rr.source_domain
            FROM news_content nc
            JOIN news_intelligence ni ON nc.intel_id = ni.id
            JOIN rss_raw rr ON ni.raw_id = rr.id
            WHERE nc.content_len > 0
              AND (nc.fetch_at > ? OR nc.created_at > ?)
        """, (show_start, show_start)).fetchall()
        conn.close()
        if rows:
            if not TOKEN:
                log("  CONTENT_PUSH skipped: NEWS_API_TOKEN not set")
                step_result("CONTENT_PUSH", 0, 0, "no token configured")
                return
            body = [{'url':r[0],'title':r[1],'content_md':r[2],'score_total':r[4],'tier':r[5],
                     'source_name':r[6],'source_domain':r[7]} for r in rows]
            # 网络延迟~5s, 增大chunk减少往返
            CHUNK = cfg("pipeline.content_chunk", 200)
            push_ok = push_fail = 0
            for i in range(0, len(body), CHUNK):
                chunk = body[i:i+CHUNK]
                try:
                    r = httpx.post(f"{CLOUD_API}/internal/news/batch", json=chunk,
                                    headers={'X-Internal-Token': TOKEN}, timeout=60)
                    if r.status_code >= 400:
                        log(f"  CONTENT_PUSH chunk {i//CHUNK+1}: HTTP {r.status_code}")
                        push_fail += len(chunk)
                    else:
                        result = r.json()
                        push_ok += result.get("ok", 0)
                        push_fail += result.get("fail", 0)
                except Exception as e:
                    log(f"  CONTENT_PUSH chunk {i//CHUNK+1}: {e}")
                    push_fail += len(chunk)
            step_result("CONTENT_PUSH", push_ok, push_fail, f"{len(rows)} articles in {(len(body)+CHUNK-1)//CHUNK} chunks")
    except Exception as e:
        log(f"  CONTENT_PUSH FAILED: {e}")
        step_result("CONTENT_PUSH", 0, 1, str(e)[:80])

# 并行执行 Step 5 + Step 6 (都是 DB只读 + HTTP, 无写冲突)
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {executor.submit(_do_step5): "CLOUD_SYNC",
               executor.submit(_do_step6): "CONTENT_PUSH"}
    for future in as_completed(futures):
        try:
            future.result()
        except Exception as e:
            log(f"  {futures[future]} thread failed: {e}")

# ── Summary ─────────────────────────────────────────────────
elapsed = time.time() - t0
release_lock()
log(f"DONE in {elapsed:.0f}s")
log("=" * 60)

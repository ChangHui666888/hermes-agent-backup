#!/usr/bin/env python3
"""
news_intel/pipeline.py — 主编排入口

完整流程：
  RSS采集 → 评分 → Intelligence Router → 三级增强 → 存储

用法：
  # 评分 + 增强（不抓全文）
  python -m news_intel.pipeline --hours 2

  # 评分 → 抓全文 → 增强 → 存储
  python -m news_intel.pipeline --hours 2 --fetch

  # 全量跑
  python -m news_intel.pipeline --all --fetch
"""

import sys
import os
import json
import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from news_intel.db import init_db, get_db, upsert_content
from news_intel.scorer import score_article, compute_velocity
from news_intel.router import route
from news_intel.sync import sync_recent

TAVILY_KEY = os.environ.get("TAVILY_API_KEY") or ""
SEARXNG_URL = "http://100.107.117.23:8080"


def run_pipeline(hours: int = 2, limit: int = 50, do_fetch: bool = False):
    """
    运行完整流水线。

    Args:
        hours: 处理最近N小时的RSS数据
        limit: 最大处理篇数
        do_fetch: 是否调用 batch.py 抓取全文
    """
    start = time.monotonic()
    push_ok = 0
    push_fail = 0
    push_duration = 0

    # 1. 初始化数据库
    init_db()
    db = get_db()

    # 2. 同步 + 评分
    stats = sync_recent(hours=hours, limit=limit)
    if not stats:
        db.close()
        return
    run_duplicate = stats.get("duplicate", 0)

    # 3. 为 Tier A/B 文章做增强（跳过已增强的） WHERE ni.tier IN ('A', 'B')
    rows = db.execute("""
        SELECT ni.id as intel_id, ni.tier, ni.score_total,
               rr.title, rr.description, rr.article_url, rr.source_name
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A', 'B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
        ORDER BY ni.score_total DESC
        LIMIT ?
    """, (limit,)).fetchall()

    print(f"\n[pipeline] 增强 {len(rows)} 篇 Tier A/B 文章...")

    # 提取待抓取 URL — 先检查 RSS description 是否已够用
    urls_to_fetch = []
    rss_skip = 0
    for row in rows:
        url = row["article_url"]
        desc = (row["description"] or "").strip()
        if url and len(desc) >= 200:
            # Check quality: not HTML-heavy, not boilerplate
            html_ratio = (desc.count("<") + desc.count(">")) / max(len(desc), 1)
            if html_ratio < 0.3:
                # RSS description is good enough, write directly to DB
                db.execute("""
                    INSERT INTO news_content (intel_id, article_url, content_md, content_len,
                        fetch_strategy, fetch_cost, fetch_at)
                    VALUES (?, ?, ?, ?, 'rss_fulltext', 0, datetime('now','localtime'))
                    ON CONFLICT(article_url) DO UPDATE SET
                        content_md=excluded.content_md, content_len=excluded.content_len,
                        fetch_strategy='rss_fulltext', fetch_cost=0,
                        fetch_at=datetime('now','localtime')
                """, (row["intel_id"], url, desc, len(desc)))
                rss_skip += 1
                continue
        if url:
            urls_to_fetch.append((url, row["intel_id"], row["tier"]))

    if rss_skip:
        db.commit()
        print(f"  [rss] {rss_skip} articles use RSS description, skip HTTP fetch")

    # 如果有正文抓取需求且 do_fetch，调用 batch.py
    fetched_content = {}
    if do_fetch and urls_to_fetch:
        import tempfile
        import subprocess
        batch_script = os.path.join(SCRIPT_DIR, "batch.py")
        if os.path.exists(batch_script):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
                tf.write("\n".join(url for url, _, _ in urls_to_fetch))
                url_file = tf.name
            out_file = os.path.join(os.path.dirname(__file__), "_fetch_tmp.jsonl")
            print(f"  [fetch] 抓取 {len(urls_to_fetch)} 篇全文...")
            batch_timeout = 300
            try:
                subprocess.run([
                    sys.executable, batch_script,
                    "--urls", url_file, "--out", out_file,
                    "--rate-delay", "0.1", "--max-workers", "8", "--no-progress",
                ], cwd=SCRIPT_DIR, timeout=batch_timeout)
            except subprocess.TimeoutExpired:
                print(f"  [fetch] batch.py timed out after {batch_timeout}s — using partial results")
            # 读取抓取结果（超时时也有部分结果可读）
            if os.path.exists(out_file):
                with open(out_file, encoding="utf-8") as f:
                    for line in f:
                        data = json.loads(line)
                        if data.get("ok"):
                            fetched_content[data["url"]] = data.get("content", "")
                os.remove(out_file)
            if os.path.exists(url_file):
                os.unlink(url_file)
    # SearXNG recovery: find alternative URLs for failed articles (free)
    searxng_recovered = 0
    if do_fetch:
        failed_mid = [(url, intel_id) for url, intel_id, score
                      in [(u[0], u[1], (row["score_total"] or 0))
                          for u, row in zip(urls_to_fetch, rows)
                          if u[0] not in fetched_content]
                      if score >= 80 and score < 90][:10]
        if failed_mid:
            print(f"  [searxng] Searching alternative URLs for {len(failed_mid)} articles...")
            import httpx
            for url, intel_id in failed_mid:
                try:
                    title = next((r["title"] for r in rows if r["article_url"] == url), "")
                    q = title[:80] if title else url
                    resp = httpx.get(f"{SEARXNG_URL}/search", params={"q": q, "format": "json"},
                                     headers={"User-Agent": "NewsIntelBot/1.0"}, timeout=10)
                    data = resp.json()
                    alt_urls = [r.get("url","") for r in data.get("results",[]) if r.get("url")][:2]
                    for alt_url in alt_urls:
                        if alt_url == url: continue
                        r2 = httpx.get(alt_url, headers={"User-Agent": "Mozilla/5.0 Chrome/131"}, timeout=10)
                        if r2.status_code == 200 and len(r2.text) > 500:
                            from core.fetchers import _extract_main_text
                            content = _extract_main_text(r2.text, url=alt_url)
                            if content and len(content) > 200:
                                db.execute("""
                                    UPDATE news_content SET content_md=?, content_len=?,
                                    fetch_strategy='searxng_alt', fetch_cost=2, fetch_at=datetime('now','localtime')
                                    WHERE intel_id=? AND (content_md IS NULL OR content_md='')
                                """, (content, len(content), intel_id))
                                searxng_recovered += 1
                                break
                except Exception:
                    pass
            if searxng_recovered:
                db.commit()
                print(f"  [searxng] Recovered {searxng_recovered} articles")

    # Tavily recovery: high-score articles that failed all strategies
    tavily_recovered = 0
    if do_fetch and TAVILY_KEY:
        failed_high = [(url, intel_id, score) for url, intel_id, score, tier
                       in [(u[0], u[1], (row["score_total"] or 0))
                           for u, row in zip(urls_to_fetch, rows)
                           if u[0] not in fetched_content]
                       if score >= 85]
        if failed_high:
            print(f"  [tavily] Recovering {len(failed_high)} high-score articles...")
            import httpx
            for url, intel_id, score in failed_high[:5]:  # max 5 per run
                try:
                    resp = httpx.post("https://api.tavily.com/search", json={
                        "api_key": TAVILY_KEY, "query": url, "search_depth": "basic",
                        "max_results": 2, "include_answer": True,
                    }, timeout=15)
                    data = resp.json()
                    answer = data.get("answer", "")
                    results = data.get("results", [])
                    if answer and len(answer) > 100:
                        content = f"[Tavily]\n\n{answer}"
                    elif results:
                        content = f"[Tavily]\n\n{results[0].get('content', results[0].get('snippet', ''))}"
                    else:
                        continue
                    db.execute("""
                        UPDATE news_content SET content_md=?, content_len=?,
                        fetch_strategy='tavily', fetch_cost=5, fetch_at=datetime('now','localtime')
                        WHERE intel_id=? AND (content_md IS NULL OR content_md='')
                    """, (content, len(content), intel_id))
                    tavily_recovered += 1
                except Exception as e:
                    print(f"    tavily error: {e}")
            if tavily_recovered:
                db.commit()
                print(f"  [tavily] Recovered {tavily_recovered} articles")

    enhanced = 0
    for row in rows:
        intel = db.execute(
            "SELECT entities, tags FROM news_intelligence WHERE id=?",
            (row["intel_id"],)
        ).fetchone()
        entities = json.loads(intel["entities"]) if intel and intel["entities"] else {}
        tags = json.loads(intel["tags"]) if intel and intel["tags"] else []

        # 获取正文
        content_md = fetched_content.get(row["article_url"], "")

        result = route(
            title=row["title"] or "",
            description=row["description"] or "",
            scores={"tier": row["tier"], "entities": entities, "categories": tags},
            content_md=content_md,
        )

        # 写入 content 层
        upsert_content(db, row["intel_id"], {
            "article_url": row["article_url"],
            "content_md": content_md,
            "content_len": len(content_md),
            "summary_cn": result.get("summary_cn", ""),
            "summary_en": result.get("summary_en", ""),
            "extraction_method": result.get("method", "unknown"),
            "llm_model": result.get("llm_model"),
            "llm_cost": result.get("llm_cost", 0.0),
            "source_headline": row["title"],
        })
        enhanced += 1

    elapsed = time.monotonic() - start

    # 统计
    tier_counts = {"A": 0, "B": 0, "C": 0}
    tc = db.execute("SELECT tier, COUNT(*) as cnt FROM news_intelligence WHERE scored_at > datetime('now', ? || ' hours', 'localtime') GROUP BY tier", (f"-{hours}",)).fetchall()
    for t in tc:
        tier_counts[t["tier"]] = t["cnt"]

    # 累计统计（全库）— 必须在 db.close() 之前
    cum = db.execute("""
        SELECT tier, COUNT(*) as cnt FROM news_intelligence GROUP BY tier
    """).fetchall()
    cumulative = {r["tier"]: r["cnt"] for r in cum}
    total_articles = db.execute("SELECT COUNT(*) FROM news_content").fetchone()[0]

    db.close()

    # ── 推送到云端 FastAPI ──────────────────────────
    api_base = os.environ.get("NEWS_API_BASE", "")
    if api_base:
        print(f"\n[pipeline] 推送结果到 {api_base} ...")
        push_start = time.monotonic()
        try:
            from news_intel.pusher import push_batch
            db2 = get_db()
            push_rows = db2.execute("""
                SELECT rr.title, rr.description, rr.article_url, rr.source_name, rr.source_domain,
                       ni.score_total, ni.tier, ni.tags, ni.entities,
                       nc.content_md, nc.summary_cn, nc.summary_en, nc.key_points,
                       nc.extraction_method, nc.fetch_strategy, nc.fetch_cost
                FROM news_content nc
                JOIN news_intelligence ni ON nc.intel_id = ni.id
                JOIN rss_raw rr ON ni.raw_id = rr.id
                WHERE nc.created_at > datetime('now', '-1 hours', 'localtime')
            """).fetchall()
            articles = []
            for r in push_rows:
                articles.append({
                    "url": r["article_url"], "title": r["title"],
                    "content": r["content_md"], "domain": r["source_domain"],
                    "source_name": r["source_name"],
                    "structured": {"headline": r["title"], "summary_cn": r["summary_cn"],
                                   "summary": r["summary_en"],
                                   "key_points": json.loads(r["key_points"]) if r["key_points"] else [],
                                   "_extraction_method": r["extraction_method"],
                                   "tags": json.loads(r["tags"]) if r["tags"] else []},
                    "scores": {"total": r["score_total"], "tier": r["tier"],
                               "entities": json.loads(r["entities"]) if r["entities"] else {}},
                    "strategy_used": r["fetch_strategy"], "total_cost": r["fetch_cost"] or 0,
                })
            result = push_batch(articles, api_base=api_base)
            db2.close()
            push_ok = result["ok"]
            push_fail = result["fail"]
            push_duration = round(time.monotonic() - push_start, 1)
            print(f"  推送完成: ✅{push_ok} ❌{push_fail} ({push_duration}s)")
        except Exception as e:
            push_duration = round(time.monotonic() - push_start, 1)
            print(f"  推送失败: {e}")

    print(f"\n{'='*60}")
    print(f"Pipeline 完成 | 耗时: {elapsed:.1f}s")
    print(f"  Tier A (>90):    {tier_counts['A']:>4}篇 → DeepSeek V4 Flash")
    print(f"  Tier B (60-90):  {tier_counts['B']:>4}篇 → Qwen3-1.7B 本地")
    print(f"  Tier C (<60):    {tier_counts['C']:>4}篇 → Python 规则（零成本）")
    print(f"  增强处理:         {enhanced:>4}篇")
    print(f"  总成本:           ${sum(r.get('llm_cost', 0) for r in []) * enhanced:.4f}")
    print(f"{'='*60}")

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        # 本轮批次
        "batch_input": stats["total"] if stats else 0,
        "batch_new": (stats["total"] or 0) - (run_duplicate or 0),
        "batch_duplicate": run_duplicate or 0,
        "batch_tier_a": tier_counts.get("A", 0),
        "batch_tier_b": tier_counts.get("B", 0),
        "batch_tier_c": tier_counts.get("C", 0),
        "batch_enhanced": enhanced,
        "batch_pushed": push_ok or 0,
        "batch_push_failed": push_fail or 0,
        # 累计
        "total_a": cumulative.get("A", 0),
        "total_b": cumulative.get("B", 0),
        "total_c": cumulative.get("C", 0),
        "total_articles": total_articles,
        # 性能
        "duration_sec": round(elapsed, 1),
        "duration_push_sec": push_duration,
        "duration_pipeline_sec": round(elapsed - push_duration, 1),
    }
    report_path = os.path.join(os.path.expanduser("~"), ".hermes", "news-pipeline-report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="News Intelligence Pipeline")
    parser.add_argument("--hours", type=int, default=2, help="处理最近N小时 (default: 2)")
    parser.add_argument("--limit", type=int, default=200, help="最大篇数 (default: 200)")
    parser.add_argument("--fetch", action="store_true", help="抓取全文（调用 batch.py）")
    parser.add_argument("--all", action="store_true", help="全量处理")
    args = parser.parse_args()

    h = 720 if args.all else args.hours
    run_pipeline(hours=h, limit=args.limit, do_fetch=args.fetch)

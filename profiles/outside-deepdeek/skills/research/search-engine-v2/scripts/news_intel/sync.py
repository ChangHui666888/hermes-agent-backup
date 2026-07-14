#!/usr/bin/env python3
"""
news_intel/sync.py — 从 rss-archive.db 同步到 news_intel.db

读取老 RSS 数据 → 评分 → 写入三层表。

=== 修复说明 (watermark cursor) ===
旧版本每次都只看"当前时间往前推 N 小时"的滑动窗口 + 硬 LIMIT，
一旦 cron 漏跑或单小时新增超过 LIMIT，落在窗口外/被截断的文章
会被永久跳过，不会被后续任何一次运行重新捕获。

新版本引入持久化游标 sync_state.rss_last_synced_at：
  - 每次从"上次同步到的 created_at"往后拉，而不是从"现在"往前推
  - 按 created_at ASC 处理，处理完后把游标推进到本批次最大的 created_at
  - 即使一次 LIMIT 内处理不完积压，下一次运行也会从游标处继续，不会丢
  - 仅在从未同步过（游标为空，首次运行）时，才退回到 "最近N小时" 兜底
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from news_intel.db import (
    get_db, insert_raw_article, upsert_intelligence,
    get_sync_watermark, set_sync_watermark,
)
from news_intel.scorer import score_article, compute_velocity

RSS_DB = os.path.expanduser("~/.hermes/rss-archive.db")


def _fetch_batch(src: sqlite3.Connection, watermark: str | None, hours: int, limit: int):
    """按游标（或首次运行时按小时窗口兜底）取一批 RSS 文章，按 created_at 升序。"""
    if watermark:
        rows = src.execute("""
            SELECT source, title, summary, link, category, date, created_at
            FROM rss_articles
            WHERE created_at > ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (watermark, limit)).fetchall()
        print(f"[sync] 游标续拉: created_at > {watermark} (最多{limit}篇)")
    else:
        rows = src.execute("""
            SELECT source, title, summary, link, category, date, created_at
            FROM rss_articles
            WHERE created_at > datetime('now', '-' || ? || ' hours', 'localtime')
            ORDER BY created_at ASC
            LIMIT ?
        """, (str(hours), limit)).fetchall()
        print(f"[sync] 首次运行(无游标)，回退到最近{hours}小时窗口 (最多{limit}篇)")
    return rows


def _process_rows(dst: sqlite3.Connection, rows: list) -> dict:
    """对一批已取出的 RSS 行做去重、评分、写入。返回统计信息。"""
    raw_count = len(rows)
    existing_urls = set(r[0] for r in dst.execute("SELECT article_url FROM rss_raw").fetchall())
    rows = [r for r in rows if r["link"] not in existing_urls]
    duplicate = raw_count - len(rows)

    stats = {"A": 0, "B": 0, "C": 0, "total": 0, "duplicate": duplicate, "raw_count": raw_count}

    if not rows:
        return stats

    print(f"[sync] 读取 {len(rows)} 篇新文章，开始评分...")

    articles_for_vel = [
        {"title": r["title"] or "", "published_at": r["date"] or ""}
        for r in rows
    ]
    articles_for_vel = compute_velocity(articles_for_vel)

    for i, (r, vel_data) in enumerate(zip(rows, articles_for_vel)):
        title = r["title"] or ""
        description = r["summary"] or ""
        source = r["source"] or ""
        url = r["link"] or ""

        scores = score_article(
            source_name=source,
            title=title,
            description=description,
            velocity_count=vel_data.get("velocity_count", 0),
        )

        from urllib.parse import urlparse
        domain = urlparse(url).netloc if url else ""
        raw_id = insert_raw_article(dst, {
            "guid": url,
            "source_name": source,
            "source_domain": domain,
            "article_url": url,
            "title": title,
            "description": description,
            "published_at": r["date"],
            "category_raw": r["category"],
        })

        if raw_id is None:
            cur = dst.execute("SELECT id FROM rss_raw WHERE guid=?", (url,))
            row = cur.fetchone()
            if row:
                raw_id = row[0]
            else:
                continue

        upsert_intelligence(
            dst, raw_id, scores,
            tier=scores["tier"],
            category=scores["categories"][0] if scores["categories"] else r["category"] or "general",
            tags=scores["categories"][:5],
            entities=scores["entities"],
            velocity_count=scores["velocity_count"],
        )

        stats["total"] += 1
        stats[scores["tier"]] += 1

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(rows)}] scored")

    return stats


def sync_recent(hours: int = 2, limit: int = 200):
    """同步 RSS 数据到 news_intel.db（游标优先，首次运行按小时窗口兜底）"""
    if not os.path.exists(RSS_DB):
        print(f"[sync] RSS DB not found: {RSS_DB}")
        return

    src = sqlite3.connect(RSS_DB)
    src.row_factory = sqlite3.Row
    dst = get_db()

    watermark = get_sync_watermark(dst)
    rows = _fetch_batch(src, watermark, hours, limit)

    if not rows:
        print(f"[sync] 无新文章")
        src.close()
        dst.close()
        return

    stats = _process_rows(dst, rows)

    # 游标推进到本批次里最大的 created_at（哪怕文章是重复/跳过的，也要推进，
    # 否则重复文章会导致游标卡住、每次都重新扫描同一批）
    max_created_at = max(r["created_at"] for r in rows)
    set_sync_watermark(dst, max_created_at)

    src.close()
    dst.close()

    print(f"\n[sync] 完成: {stats['total']}篇 (重复跳过 {stats['duplicate']}篇)")
    print(f"  Tier A ( >90): {stats['A']}篇 → DeepSeek V4 Flash")
    print(f"  Tier B (60-90): {stats['B']}篇 → Qwen3-1.7B 本地")
    print(f"  Tier C ( <60): {stats['C']}篇 → Python 规则（零成本）")
    print(f"  游标更新至: {max_created_at}")

    if len(rows) == limit:
        print(f"  ⚠️ 本次命中 LIMIT={limit} 上限，可能仍有积压未同步；"
              f"下次运行会自动从游标继续，或立即用 --catchup 一次性追平")

    return stats


def sync_catchup(limit_per_batch: int = 500, max_batches: int = 200, hours: int = 720):
    """
    持续按批次追平积压（用于首次回填历史数据，或补上长时间未同步的缺口）。
    每批最多 limit_per_batch 篇，直到没有新数据或达到 max_batches。
    """
    total = {"A": 0, "B": 0, "C": 0, "total": 0, "duplicate": 0, "batches": 0}
    for i in range(max_batches):
        stats = sync_recent(hours=hours, limit=limit_per_batch)
        if not stats or stats.get("total", 0) == 0 and stats.get("duplicate", 0) == 0:
            break
        total["A"] += stats.get("A", 0)
        total["B"] += stats.get("B", 0)
        total["C"] += stats.get("C", 0)
        total["total"] += stats.get("total", 0)
        total["duplicate"] += stats.get("duplicate", 0)
        total["batches"] += 1
        if stats.get("raw_count", 0) < limit_per_batch:
            # 这一批取到的原始行数不足 limit，说明已经追到最新，没有更多积压了
            break
    print(f"\n[sync] catchup 完成: 共 {total['batches']} 批, "
          f"新增 {total['total']}篇 (A={total['A']} B={total['B']} C={total['C']}), "
          f"跳过重复 {total['duplicate']}篇")
    return total


def sync_all(limit: int = 500):
    """全量同步（首次使用/一次性回填）。内部走 catchup 循环，自动分批追平。"""
    return sync_catchup(limit_per_batch=limit, hours=720)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RSS → News Intel 同步")
    parser.add_argument("--hours", type=int, default=2, help="首次运行(无游标)时的兜底窗口")
    parser.add_argument("--limit", type=int, default=200, help="单批最大篇数")
    parser.add_argument("--all", action="store_true", help="全量同步(首次回填，自动分批追平)")
    parser.add_argument("--catchup", action="store_true", help="持续分批追平当前积压")
    args = parser.parse_args()

    if args.all:
        sync_all(limit=args.limit)
    elif args.catchup:
        sync_catchup(limit_per_batch=args.limit, hours=args.hours)
    else:
        sync_recent(hours=args.hours, limit=args.limit)

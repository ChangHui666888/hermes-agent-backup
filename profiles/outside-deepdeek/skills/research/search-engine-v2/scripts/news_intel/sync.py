#!/usr/bin/env python3
"""
news_intel/sync.py — 从 rss-archive.db 同步到 news_intel.db

读取老 RSS 数据 → 评分 → 写入三层表。
"""

import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from news_intel.db import get_db, insert_raw_article, upsert_intelligence
from news_intel.scorer import score_article, compute_velocity

RSS_DB = os.path.expanduser("~/.hermes/rss-archive.db")


def sync_recent(hours: int = 2, limit: int = 200):
    """同步最近 N 小时的 RSS 数据到 news_intel.db"""
    if not os.path.exists(RSS_DB):
        print(f"[sync] RSS DB not found: {RSS_DB}")
        return

    src = sqlite3.connect(RSS_DB)
    src.row_factory = sqlite3.Row
    dst = get_db()

    # 读取最近文章
    rows = src.execute("""
        SELECT source, title, summary, link, category, date
        FROM rss_articles
        WHERE created_at > datetime('now', '-' || ? || ' hours', 'localtime')
        ORDER BY created_at DESC
        LIMIT ?
    """, (str(hours), limit)).fetchall()

    if not rows:
        print(f"[sync] 无新文章（最近{hours}小时）")
        src.close()
        dst.close()
        return

    # 去重：跳过已评分文章
    raw_count = len(rows)
    existing_urls = set(r[0] for r in dst.execute("SELECT article_url FROM rss_raw").fetchall())
    rows = [r for r in rows if r["link"] not in existing_urls]
    duplicate = raw_count - len(rows)

    if not rows:
        print(f"[sync] 所有文章已评分（最近{hours}小时）")
        src.close()
        dst.close()
        return

    print(f"[sync] 读取 {len(rows)} 篇文章，开始评分...")

    # 准备 velocity 计算所需的文章列表
    articles_for_vel = []
    for r in rows:
        articles_for_vel.append({
            "title": r["title"] or "",
            "published_at": r["date"] or "",
        })

    # 计算传播速度
    articles_for_vel = compute_velocity(articles_for_vel)

    # 评分 + 写入
    stats = {"A": 0, "B": 0, "C": 0, "total": 0, "duplicate": duplicate}
    for i, (r, vel_data) in enumerate(zip(rows, articles_for_vel)):
        title = r["title"] or ""
        description = r["summary"] or ""
        source = r["source"] or ""
        url = r["link"] or ""

        # 评分
        scores = score_article(
            source_name=source,
            title=title,
            description=description,
            velocity_count=vel_data.get("velocity_count", 0),
        )

        # 写入 raw 层
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
            # URL 已存在，查已有 ID
            cur = dst.execute("SELECT id FROM rss_raw WHERE guid=?", (url,))
            row = cur.fetchone()
            if row:
                raw_id = row[0]
            else:
                continue

        # 写入 intelligence 层
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

    src.close()
    dst.close()

    print(f"\n[sync] 完成: {stats['total']}篇")
    print(f"  Tier A ( >90): {stats['A']}篇 → DeepSeek V4 Flash")
    print(f"  Tier B (60-90): {stats['B']}篇 → Qwen3-1.7B 本地")
    print(f"  Tier C ( <60): {stats['C']}篇 → Python 规则（零成本）")

    return stats


def sync_all(limit: int = 500):
    """全量同步（首次使用）"""
    return sync_recent(hours=720, limit=limit)  # 30天


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RSS → News Intel 同步")
    parser.add_argument("--hours", type=int, default=2, help="同步最近N小时")
    parser.add_argument("--limit", type=int, default=200, help="最大篇数")
    parser.add_argument("--all", action="store_true", help="全量同步")
    args = parser.parse_args()

    if args.all:
        sync_all(limit=args.limit)
    else:
        sync_recent(hours=args.hours, limit=args.limit)

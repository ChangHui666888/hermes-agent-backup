#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_fix.py — 只读校验脚本，不修改任何数据。

用途：
  1. 部署修复文件之前：看一眼当前 tier 过滤 bug 影响了多少篇文章
  2. 部署修复文件、跑过几轮 pipeline 之后：确认抓取候选池、content_ok、
     以及 sync_state 游标是否符合预期

用法（在你的 news_intel 目录下执行，或用 --db 指定路径）：
  python verify_fix.py --db C:\\Users\\ChangHui\\AppData\\Local\\hermes\\profiles\\outside-deepdeek\\skills\\research\\search-engine-v2\\scripts\\news_intel\\news_intel.db
"""

import argparse
import sqlite3
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="news_intel.db 路径")
    args = parser.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    print("=" * 60)
    print("1. Tier 分布 & Fetcher 候选池对比（修复前 vs 修复后逻辑）")
    print("=" * 60)
    for row in db.execute("""
        SELECT ni.tier,
               COUNT(ni.id) as intel_total,
               COUNT(nc.id) as has_content_row,
               SUM(CASE WHEN nc.content_md IS NOT NULL AND nc.content_md != ''
                        THEN 1 ELSE 0 END) as content_ok
        FROM news_intelligence ni
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        GROUP BY ni.tier
        ORDER BY ni.tier
    """):
        print(f"  Tier {row['tier']}: intel={row['intel_total']:>5}  "
              f"has_content_row={row['has_content_row']:>5}  "
              f"content_ok={row['content_ok']:>5}")

    old_pool = db.execute("""
        SELECT COUNT(*) FROM news_intelligence ni
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
    """).fetchone()[0]

    new_pool = db.execute("""
        SELECT COUNT(*) FROM news_intelligence ni
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A', 'B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
    """).fetchone()[0]

    print(f"\n  修复前候选池 (仅Tier A): {old_pool}")
    print(f"  修复后候选池 (Tier A+B): {new_pool}")
    if new_pool > old_pool:
        print(f"  → tier 过滤 bug 确认存在，修复后多覆盖 {new_pool - old_pool} 篇文章")

    print()
    print("=" * 60)
    print("2. sync_state 游标（部署 db.py 修复 + 至少跑过一次 sync 后才会出现）")
    print("=" * 60)
    has_table = db.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='sync_state'
    """).fetchone()
    if not has_table:
        print("  尚未部署修复（sync_state 表不存在）。"
              "部署 db.py 后跑一次 pipeline，init_db() 会自动建表。")
    else:
        rows = db.execute("SELECT key, value, updated_at FROM sync_state").fetchall()
        if not rows:
            print("  sync_state 表已存在，但还没有游标记录 —— 说明还没跑过一次新版 sync_recent()")
        for r in rows:
            print(f"  {r['key']} = {r['value']}  (updated_at={r['updated_at']})")

    print()
    print("=" * 60)
    print("3. RSS 同步覆盖率参考（本地 rss_raw 副本 vs 你手动提供的 latest24h）")
    print("=" * 60)
    total, min_ts, max_ts = db.execute(
        "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM rss_raw"
    ).fetchone()
    print(f"  rss_raw 总数={total}  时间范围={min_ts} ~ {max_ts}")
    print("  可以和 rss-archive.db 里同一时间段的 latest24h 数字对比，"
          "部署游标修复、稳定运行几天后，两者应该趋近一致。")

    db.close()


if __name__ == "__main__":
    sys.exit(main())

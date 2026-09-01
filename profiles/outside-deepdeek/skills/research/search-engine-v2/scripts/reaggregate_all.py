#!/usr/bin/env python3
"""
reaggregate_all.py — 完全重跑事件聚合

用优化后的聚合器对全部文章重新生成事件：
1. 备份当前 event_registry
2. 清空 event_registry
3. 加载全部 Tier A/B 有内容的文章
4. aggregate_events 重新生成并持久化
5. 推送全部事件到云端

用法:
  python reaggregate_all.py              # 重跑 + 推云端
  python reaggregate_all.py --no-push    # 只重跑本地，不推云端
"""

import sys, os, json, sqlite3, shutil, argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "news_intel"))

DB_PATH = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")


def backup_events():
    """备份 event_registry 到 .bak 表"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DROP TABLE IF EXISTS event_registry_bak")
        conn.execute("CREATE TABLE event_registry_bak AS SELECT * FROM event_registry")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM event_registry_bak").fetchone()[0]
        print(f"[backup] event_registry_bak: {n} 行")
    finally:
        conn.close()


def clear_events():
    """清空 event_registry"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM event_registry")
        conn.commit()
        print("[clear] event_registry 已清空")
    finally:
        conn.close()


def load_articles():
    """加载全部 Tier A/B 有内容的文章"""
    from news_intel.db import get_db
    db = get_db()
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = db.execute("""
        SELECT nc.id, rr.title, nc.summary_cn, rr.description,
               ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name,
               rr.article_url as url
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE ni.tier IN ('A', 'B')
          AND nc.content_md IS NOT NULL AND nc.content_md != ''
        ORDER BY rr.published_at ASC
    """).fetchall()
    db.close()
    print(f"[load] {len(rows)} 篇 Tier A/B 有内容文章")
    return rows


def main():
    parser = argparse.ArgumentParser(description="完全重跑事件聚合")
    parser.add_argument("--no-push", action="store_true", help="不推送到云端")
    parser.add_argument("--limit", type=int, default=0, help="只处理前N篇文章(测试用, 0=全部)")
    args = parser.parse_args()

    from news_intel.aggregator import aggregate_events

    print("=" * 50)
    print("完全重跑事件聚合 (优化版聚合器)")
    print("=" * 50)

    # 1. 备份
    backup_events()
    # 2. 清空
    clear_events()
    # 3. 加载文章
    articles = load_articles()
    if args.limit > 0:
        articles = articles[:args.limit]
        print(f"[load] 仅处理前 {args.limit} 篇(测试)")
    # 4. 聚合
    events = aggregate_events(articles, window_hours=48)
    print(f"[aggregate] 生成 {len(events)} 个事件")

    # 统计
    types = {}
    for e in events:
        t = e.get("event_type", "?")
        types[t] = types.get(t, 0) + 1
    print("[类型分布]")
    for t, c in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    # 5. 推云端
    if not args.no_push:
        # 复用 config.env (CLOUD_API / INTERNAL_TOKEN); 失败回退 Tailscale 地址
        try:
            from config.env import CLOUD_API, INTERNAL_TOKEN
        except Exception:
            CLOUD_API = "http://100.107.117.23"
            INTERNAL_TOKEN = "v8-pipeline-token-2026-xK9mP2sR7wQ"
        # pusher 在 import 时读 NEWS_API_BASE / NEWS_API_TOKEN, 必须先设 env。
        # 否则回退 localhost:8000 + 错误 token, 且走 HTTP_PROXY 时被代理返回 502。
        os.environ["NEWS_API_BASE"] = CLOUD_API
        os.environ["NEWS_API_TOKEN"] = INTERNAL_TOKEN
        from news_intel.pusher import push_events
        # 分批推送
        CHUNK = 100
        for i in range(0, len(events), CHUNK):
            chunk = events[i:i+CHUNK]
            result = push_events(chunk, api_base=CLOUD_API)
            print(f"[push] 批次 {i//CHUNK+1}: {result}")
        print("[push] 推送完成")
    else:
        print("[push] 已跳过 (--no-push)")

    print("=" * 50)
    print("完成")


if __name__ == "__main__":
    main()

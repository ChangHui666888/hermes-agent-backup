#!/usr/bin/env python3
"""
test_aggregator.py — 手动验证 L8 事件聚合质量

用法:
  python test_aggregator.py --hours 6 --window 6
"""
import sys, os, json, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_intel.aggregator import aggregate_events
from news_intel.generator import generate_insight
from news_intel.db import get_db, init_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24, help="取最近N小时文章")
    parser.add_argument("--window", type=int, default=6, help="事件聚合时间窗口(小时)")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--insight", action="store_true", help="生成 Insight")
    args = parser.parse_args()

    init_db()
    db = get_db()
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    rows = db.execute(f"""
        SELECT nc.id, rr.title, ni.score_total, ni.tier,
               ni.entities, rr.published_at
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE nc.created_at > datetime('now', '-{args.hours} hours')
        ORDER BY nc.created_at DESC
        LIMIT {args.limit}
    """).fetchall()

    articles = []
    for r in rows:
        ents = {}
        try: ents = json.loads(r["entities"])
        except: pass
        articles.append({
            "id": r["id"], "title": r["title"],
            "score_total": r["score_total"], "tier": r["tier"],
            "entities": ents,
            "published_at": r["published_at"],
        })

    if not articles:
        print("无文章数据")
        return

    print(f"输入: {len(articles)} 篇文章, 窗口={args.window}h")
    t0 = time.time()
    events = aggregate_events(articles, window_hours=args.window)
    elapsed = time.time() - t0

    print(f"聚合: {len(events)} 个事件 ({elapsed:.1f}s)")
    print()

    for i, ev in enumerate(events, 1):
        articles_with_event = sum(1 for a in articles if a["id"] in ev["article_ids"])
        print(f"事件 #{i}: {ev['title'][:80]}")
        print(f"  级别: {ev['impact_level']} | 文章: {articles_with_event}篇 | 实体: {', '.join(ev['entities'][:5])}")
        if args.insight and ev["impact_level"] == "HIGH":
            t0 = time.time()
            insight = generate_insight(ev, force_deepseek=True)
            t1 = time.time() - t0
            if insight:
                print(f"  🤖 Insight ({t1:.1f}s): {insight.get('summary','')[:100]}")
        print()

    # 统计
    covered = set()
    for ev in events:
        covered.update(ev["article_ids"])
    print(f"覆盖率: {len(covered)}/{len(articles)} = {len(covered)/len(articles)*100:.1f}%")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
test_aggregator.py — 聚合验证 + 详细审计日志

用法:
  python test_aggregator.py --hours 24 --window 6 --limit 20
  python test_aggregator.py --hours 24 --window 6 --limit 20 --verbose  # 完整指纹+评分
  python test_aggregator.py --hours 24 --window 6 --limit 20 --insight  # +洞察
"""
import sys, os, json, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_intel.aggregator import (
    aggregate_events, build_fingerprint, fingerprint_score, _parse_date,
    _get_text, _detect_action, _classify_topics, _canonicalize, _entity_weight,
    _compute_entity_idf, EVENT_THRESHOLD, MERGE_THRESHOLD,
)
from news_intel.generator import generate_for_event
from news_intel.db import get_db, init_db
from datetime import datetime, timedelta


def load_articles(hours: int, limit: int) -> list[dict]:
    init_db()
    db = get_db()
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = db.execute(f"""
        SELECT nc.id, rr.title, nc.summary_cn, rr.description,
               ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE nc.created_at > datetime('now', '-{hours} hours')
        ORDER BY nc.created_at DESC
        LIMIT {limit}
    """).fetchall()
    articles = []
    for r in rows:
        ents = {}
        try: ents = json.loads(r["entities"])
        except: pass
        articles.append({
            "id": r["id"], "title": r["title"],
            "description": r["description"] or r["summary_cn"] or "",
            "score_total": r["score_total"], "tier": r["tier"],
            "entities": ents,
            "published_at": r["published_at"],
            "source_name": r["source_name"] or "",
        })
    return articles


def print_fingerprint(a: dict, label: str = ""):
    """打印单篇文章的事件指纹"""
    fp = build_fingerprint(a)
    prefix = f"[{a['source_name'][:12]}]" if a.get("source_name") else ""
    print(f"  {prefix} {label}")
    print(f"    标题: {a['title'][:70]}")
    print(f"    实体: {a.get('entities',{})}")
    print(f"    指纹: subj={fp['subject']} | action={fp['action']} | obj={fp['object']}")
    print(f"          type={fp['event_type']} | topic={fp['primary_topic']}/{fp['secondary_topic']} | country={fp['country']}")
    print(f"          anchor={fp.get('anchor','')}")
    return fp


def print_score_matrix(articles: list[dict], verbose: bool = False):
    """打印文章对评分矩阵"""
    n = len(articles)
    if n > 20 and not verbose:
        return  # 太大时跳过

    fps = [build_fingerprint(a) for a in articles]

    merged_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            score = fingerprint_score(fps[i], fps[j])
            if score >= EVENT_THRESHOLD:
                merged_pairs.append((i, j, score, fps[i], fps[j]))

    if merged_pairs:
        print(f"\n  Phase 1 匹配对 (≥{EVENT_THRESHOLD}分):")
        for i, j, score, fpi, fpj in merged_pairs:
            a_i, a_j = articles[i], articles[j]
            print(f"    [{i}][{j}] score={score}")
            print(f"      {a_i['source_name'][:10]} {a_i['title'][:50]}")
            print(f"      {a_j['source_name'][:10]} {a_j['title'][:50]}")
            if verbose:
                print(f"      fp1: subj={fpi['subject']} act={fpi['action']} obj={fpi['object']} top={fpi['primary_topic']}")
                print(f"      fp2: subj={fpj['subject']} act={fpj['action']} obj={fpj['object']} top={fpj['primary_topic']}")


def main():
    parser = argparse.ArgumentParser(description="Event Aggregator Audit Tool")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--window", type=int, default=6)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--insight", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true", help="输出完整指纹+评分明细")
    parser.add_argument("--single", type=int, default=0, help="只分析第N个事件的文章指纹")
    args = parser.parse_args()

    articles = load_articles(args.hours, args.limit)
    print(f"输入: {len(articles)} 篇文章, 窗口={args.window}h")
    print()

    # ── 单事件深度分析模式 ──
    if args.single:
        events = aggregate_events(articles, window_hours=args.window)
        if args.single > len(events):
            print(f"事件数={len(events)}, #{args.single} 不存在")
            return
        ev = events[args.single - 1]
        print(f"=== 事件 #{args.single}: {ev['title'][:80]} ===")
        print(f"级别: {ev['impact_level']} | 文章: {ev['article_count']}篇 | 实体: {', '.join(ev['entities'][:10])}")
        print(f"动作: {ev.get('actions',[])} | 主题: {ev.get('topics',[])}")
        print()
        members = [a for a in articles if a["id"] in ev["article_ids"]]
        for i, a in enumerate(members, 1):
            print(f"--- 文章 #{i} ---")
            print_fingerprint(a)
        print(f"\n评分矩阵 ({len(members)}篇):")
        print_score_matrix(members, verbose=True)
        return

    # ── 正常聚合模式 ──
    t0 = time.time()

    # 如果 verbose, 打印所有文章指纹
    if args.verbose:
        print("=" * 60)
        print("所有文章指纹")
        print("=" * 60)
        for i, a in enumerate(articles):
            print(f"\n文章 #{i+1}/{len(articles)}")
            print_fingerprint(a)
        print()

        # 评分矩阵
        print("=" * 60)
        print("Phase 1 评分矩阵")
        print("=" * 60)
        print_score_matrix(articles, verbose=True)
        print()

    events = aggregate_events(articles, window_hours=args.window)
    elapsed = time.time() - t0

    print(f"聚合: {len(events)} 个事件 ({elapsed:.1f}s)")
    print()

    for i, ev in enumerate(events, 1):
        members = [a for a in articles if a["id"] in ev["article_ids"]]
        sources = sorted(set(a["source_name"][:12] for a in members))

        print(f"事件 #{i}: {ev['title'][:80]}")
        print(f"  级别: {ev['impact_level']} | 文章: {len(members)}篇 | 实体: {', '.join(ev['entities'][:10])}")
        print(f"  动作: {ev.get('actions',[])} | 主题: {ev.get('topics',[])}")

        if args.verbose:
            print(f"  成员详情:")
            for a in members:
                fp = build_fingerprint(a)
                print(f"    [{a['source_name'][:12]}] {a['title'][:60]}")
                print(f"      subj={fp['subject']} act={fp['action']} obj={fp['object']} top={fp['primary_topic']} country={fp['country']}")
        else:
            print(f"  来源: {', '.join(sources[:8])}")

        if args.insight:
            t1 = time.time()
            insight = generate_for_event(ev)
            t2 = time.time() - t1
            if insight:
                print(f"  🤖 Insight ({t2:.1f}s): {insight.get('summary','')[:100]}")
            else:
                print(f"  🤖 Insight: 生成失败")
        print()

    # 统计
    covered = set()
    for ev in events:
        covered.update(ev["article_ids"])
    coverage = len(covered) / len(articles) * 100

    print(f"覆盖率: {len(covered)}/{len(articles)} = {coverage:.1f}%")


if __name__ == "__main__":
    main()

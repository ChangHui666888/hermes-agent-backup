#!/usr/bin/env python3
"""
reaggregate_recent.py — 非破坏性一键重聚合最近 N 小时/天的未分配文章

背景 (ISS-20260809-010): 增量 pipeline (auto-pipeline.py Step 4.5) 每轮只取最新
500 篇未分配文章; 当轮凑不够 ≥2 文章的事件簇时不出事件, 这些文章就一直挂着。
本脚本把聚合窗口放宽到"最近 N 小时/天", 手动触发一轮, 把新事件补出来。

特性:
  - 非破坏性: 不清任何表, 不碰存量事件 / 手工校对 / 关系 / stories
  - 幂等: 只聚合 未分配(event_id 为空) 的文章; 落库 upsert, 文章标记只写未分配,
    推送 VPS 走 ON CONFLICT upsert —— 重复执行不产生重复事件
  - 复用生产 fused 聚合 (facts + ner), 产出与 EVT-20260728-218 同形状
    (evidence/source_chain/doc_refs 带 url, 依赖 ISS-20260809-010 修复)

用法 (需在 生产 profile 的 scripts 目录运行, 见 all-commands.md):
  python reaggregate_recent.py --hours 24             # 最近 24 小时
  python reaggregate_recent.py --days 3               # 最近 3 天
  python reaggregate_recent.py --hours 12 --no-push   # 只本地聚合落库, 不推送
  python reaggregate_recent.py --hours 24 --window 48 # 指定聚合窗口(默认48h)
  python reaggregate_recent.py --hours 24 --limit 50  # 仅前50篇(测试)
"""

import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "news_intel"))


def _is_cjk(text: str) -> bool:
    """是否含 CJK 汉字 (与 auto-pipeline 一致: C 级只放行 CJK)。"""
    return any("一" <= ch <= "鿿" for ch in (text or ""))


def _load_facts_payload() -> dict:
    """{article_id: [fact_payload, ...]} — fact_pipeline Step 4 产物, fused 接线。"""
    path = os.path.join(SCRIPT_DIR, "news_intel", "fact_pipeline_payload.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            payloads = json.load(f)
        facts = {}
        for p in payloads:
            aid = p.get("article_id")
            if aid and p.get("action_type"):
                facts.setdefault(aid, []).append(p)
        return facts
    except Exception as e:
        print(f"[reagg] facts-payload 解析失败, 回退 legacy: {e}")
        return {}


def _load_ner_payload() -> dict:
    """{article_id: [GLiNER 实体]} — 中文 C 级 GLiNER 产物。"""
    path = os.path.join(SCRIPT_DIR, "news_intel", "ner_by_article.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[reagg] ner-payload 解析失败, 忽略: {e}")
        return {}


def _cloud_config():
    """复用 config.env (CLOUD_API / INTERNAL_TOKEN); 失败回退 Tailscale 地址。"""
    try:
        from config.env import CLOUD_API, INTERNAL_TOKEN
        return CLOUD_API, INTERNAL_TOKEN
    except Exception:
        return "http://100.107.117.23", "v8-pipeline-token-2026-xK9mP2sR7wQ"


def main():
    p = argparse.ArgumentParser(
        description="非破坏性一键重聚合最近 N 小时/天的未分配文章 (fused, 推 VPS)")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--hours", type=int, default=24, help="回看最近 N 小时 (默认 24)")
    grp.add_argument("--days", type=int, default=0, help="回看最近 N 天 (优先于 --hours)")
    p.add_argument("--window", type=int, default=48, help="聚合窗口小时数 (默认 48)")
    p.add_argument("--no-push", action="store_true", help="只本地聚合落库, 不推送 VPS")
    p.add_argument("--limit", type=int, default=0, help="仅处理前 N 篇文章 (测试用, 0=全部)")
    args = p.parse_args()

    hours = args.days * 24 if args.days else args.hours
    if hours <= 0:
        print("[reagg] 无效回看窗口, 退出")
        return

    print("=" * 60)
    print(f"[reagg] 重聚合最近 {hours} 小时未分配文章 "
          f"(window={args.window}h, push={'否' if args.no_push else '是'})")
    print("=" * 60)

    from news_intel.db import init_db, get_db, assign_articles_to_event
    from news_intel.aggregator import aggregate_events

    init_db()
    db = get_db()
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    # 1) 最近 N 小时 + 未分配 的 A/B(+中文C) 文章, 带 url (ISS-20260809-010 修复)
    rows = db.execute("""
        SELECT nc.id, rr.title, nc.summary_cn, rr.description,
               ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name,
               rr.article_url as url
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE (ni.tier IN ('A','B') OR ni.tier = 'C')
          AND (nc.event_id IS NULL OR nc.event_id = '')
          AND nc.created_at >= datetime('now', :lookback)
        ORDER BY nc.id DESC
    """, {"lookback": f"-{hours} hours"}).fetchall()
    if args.limit:
        rows = rows[:args.limit]
    # C 级仅放行 CJK (与 auto-pipeline 一致)
    rows = [r for r in rows if r["tier"] in ("A", "B")
            or _is_cjk((r["title"] or "") + (r["description"] or ""))]
    print(f"[reagg] 候选文章: {len(rows)} (近 {hours}h 未分配 A/B + 中文C, "
          f"含 url: {sum(1 for r in rows if r.get('url'))})")
    if not rows:
        print("[reagg] 无可聚合文章, 退出")
        db.close()
        return

    # 2) 生产 fused 聚合 (facts + ner); aggregate_events 内部自动 upsert 落库
    facts = _load_facts_payload()
    ner = _load_ner_payload()
    print(f"[reagg] facts_by_article={len(facts)} ner_by_article={len(ner)}")
    events = aggregate_events(rows, window_hours=args.window,
                              facts_by_article=facts, ner_by_article=ner)
    print(f"[reagg] 生成事件: {len(events)}")
    for e in events:
        print(f"   {e['event_id']} | {len(e.get('article_ids') or [])}篇 | "
              f"{(e.get('title') or '')[:60]}")

    # 3) 标记文章归属 (幂等: 只标记未分配的文章)
    marked = 0
    for ev in events:
        marked += assign_articles_to_event(db, ev.get("event_id"), ev.get("article_ids") or [])
    db.commit()
    db.close()
    print(f"[reagg] 标记文章归属: {marked}")

    # 4) 推送新事件到 VPS (幂等 upsert)
    if args.no_push:
        print("[reagg] 已跳过推送 (--no-push)")
        return
    if not events:
        return
    # pusher 在 import 时读 NEWS_API_TOKEN / NEWS_API_BASE, 必须先设 env
    cloud_api, internal_token = _cloud_config()
    os.environ.setdefault("NEWS_API_TOKEN", internal_token)
    from news_intel import pusher
    res = pusher.push_events(events, api_base=cloud_api)
    eids = ", ".join(e["event_id"] for e in events[:5]) + ("..." if len(events) > 5 else "")
    print(f"[reagg] 推送 VPS: ok={res.get('ok')} fail={res.get('fail')} | {eids}")


if __name__ == "__main__":
    main()

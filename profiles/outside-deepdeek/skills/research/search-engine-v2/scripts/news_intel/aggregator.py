"""
news_intel/aggregator.py — L8 事件聚合器

规则引擎：实体交集 + 标题相似度 + 时间窗口 → events
"""
import json, re, os, logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


def _make_fingerprint_set(title: str) -> set:
    words = re.findall(r"[A-Za-z\u4e00-\u9fff]+", title.lower())
    stops = {"the","a","an","is","are","was","were","in","on","at","to","for","of",
             "and","or","it","this","that","with","has","s","re","ve","的","了","在",
             "是","和","也","就","都","把","被"}
    meaningful = [w for w in words if w not in stops and len(w) > 1]
    return set(meaningful[:8])


def jaccard(a: set, b: set) -> float:
    if not a or not b: return 0
    return len(a & b) / len(a | b)


def aggregate_events(articles: list[dict], window_hours: int = 6) -> list[dict]:
    """
    输入: 待聚合文章列表 [{id, title, published_at, entities: {companies:[], persons:[], countries:[]}, score_total}]
    输出: 事件列表 [{title, articles:[id,...], entities:[...], impact_level}]

    规则优先级:
    1. 实体交集 ≥ 2 且 Jaccard ≥ 0.3 → 同一事件
    2. Jaccard ≥ 0.5 (即使无实体交集) → 同一事件
    """
    if not articles:
        return []

    # 解析时间
    parsed = []
    for a in articles:
        ts = a.get("published_at")
        if isinstance(ts, str):
            try: ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except: ts = datetime.utcnow()
        elif ts is None:
            ts = datetime.utcnow()
        parsed.append((a, ts))

    window = timedelta(hours=window_hours)

    # Union-Find 聚类
    n = len(parsed)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        ai, ti = parsed[i]
        ei = ai.get("entities", {}) or {}
        ent_i = set(ei.get("companies", []) + ei.get("persons", []) + ei.get("countries", []))
        fp_i = _make_fingerprint_set(ai.get("title", ""))
        for j in range(i + 1, n):
            aj, tj = parsed[j]
            if abs(ti - tj) > window:
                continue
            ej = aj.get("entities", {}) or {}
            ent_j = set(ej.get("companies", []) + ej.get("persons", []) + ej.get("countries", []))
            fp_j = _make_fingerprint_set(aj.get("title", ""))
            jac = jaccard(fp_i, fp_j)
            shared_ent = len(ent_i & ent_j)

            if shared_ent >= 2:
                union(i, j)
            elif jac >= 0.45:
                union(i, j)

    # 分组
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    # 生成事件
    events = []
    for root, indices in groups.items():
        if len(indices) < 2:
            continue  # 单篇文章不构成事件
        members = [parsed[i][0] for i in indices]
        titles = [a.get("title", "") for a in members]
        best_title = max(titles, key=len)[:200]
        all_ents = set()
        for a in members:
            e = a.get("entities", {}) or {}
            all_ents.update(e.get("companies", []))
            all_ents.update(e.get("persons", []))
            all_ents.update(e.get("countries", []))
        max_score = max(a.get("score_total", 0) for a in members)
        impact = "HIGH" if max_score >= 85 else ("MEDIUM" if max_score >= 60 else "LOW")

        events.append({
            "title": best_title,
            "article_ids": [a["id"] for a in members],
            "article_count": len(members),
            "entities": list(all_ents),
            "impact_level": impact,
            "max_score": max_score,
        })

    events.sort(key=lambda e: e["article_count"], reverse=True)
    return events

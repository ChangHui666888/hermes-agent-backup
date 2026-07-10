"""
news_intel/scorer.py — News Value Score Engine

五维评分（满分100）：
  1. Source Authority  (20) — 来源权威度
  2. Event Impact      (30) — 事件影响力
  3. Entity Importance (20) — 实体重要性
  4. Market Relevance  (20) — 市场关联度
  5. Velocity          (10) — 传播速度

返回: {total, source, impact, entity, market, velocity, tier, entities, categories, market_assets}
"""

import json
import os
import re
from datetime import datetime
from typing import Optional

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")


def _load_json(filename: str) -> dict:
    path = os.path.join(CONFIG_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# 懒加载配置
_source_scores: Optional[dict] = None
_event_keywords: Optional[dict] = None
_entity_weights: Optional[dict] = None
_asset_graph: Optional[dict] = None


def _get_source_scores() -> dict:
    global _source_scores
    if _source_scores is None:
        _source_scores = _load_json("source_scores.json")
    return _source_scores


def _get_event_keywords() -> dict:
    global _event_keywords
    if _event_keywords is None:
        _event_keywords = _load_json("event_keywords.json")
    return _event_keywords


def _get_entity_weights() -> dict:
    global _entity_weights
    if _entity_weights is None:
        _entity_weights = _load_json("entity_weights.json")
    return _entity_weights


def _get_asset_graph() -> dict:
    global _asset_graph
    if _asset_graph is None:
        _asset_graph = _load_json("asset_graph.json")
    return _asset_graph


# ═══════════════════════════════════════════════════════════════════
# 1. Source Authority (0-20)
# ═══════════════════════════════════════════════════════════════════

def score_source(source_name: str) -> int:
    """来源权威度评分"""
    scores = _get_source_scores().get("scores", {})
    return scores.get(source_name, scores.get("_default", 5))


# ═══════════════════════════════════════════════════════════════════
# 2. Event Impact (0-30)
# ═══════════════════════════════════════════════════════════════════

def score_impact(title: str, description: str = "") -> tuple[int, list[str]]:
    """
    事件影响力评分。对 title+description 做关键词匹配。
    返回 (分数, 命中的分类列表)
    """
    text = f"{title} {description}".lower()
    keywords = _get_event_keywords()
    max_score = 0
    hit_categories = []

    for category, kw_dict in keywords.items():
        if category == "_description":
            continue
        cat_best = 0
        for keyword, score in kw_dict.items():
            if keyword.lower() in text:
                if score > cat_best:
                    cat_best = score
        if cat_best > 0:
            hit_categories.append(category)
            # 多类别取最高（不是累加，防止标题党刷分）
            if cat_best > max_score:
                max_score = cat_best

    return min(max_score, 30), hit_categories


# ═══════════════════════════════════════════════════════════════════
# 3. Entity Importance (0-20)
# ═══════════════════════════════════════════════════════════════════

def score_entities(title: str, description: str = "") -> tuple[int, dict]:
    """
    实体重要性评分。从标题+摘要中匹配已知重要实体。
    返回 (分数, {companies: [...], persons: [...], countries: [...]})
    """
    text = f"{title} {description}"
    weights = _get_entity_weights()
    found = {"companies": [], "persons": [], "countries": []}
    max_score = 0

    for etype, entities in weights.items():
        if etype == "_description":
            continue
        for name, weight in entities.items():
            if name in text:
                found[etype].append(name)
                if weight > max_score:
                    max_score = weight

    return min(max_score, 20), found


# ═══════════════════════════════════════════════════════════════════
# 4. Market Relevance (0-20)
# ═══════════════════════════════════════════════════════════════════

def score_market(title: str, description: str = "", entities: dict = None) -> tuple[int, list[str]]:
    """
    市场关联度评分。检查新闻是否涉及可交易资产。
    返回 (分数, 受影响的股票/资产列表)
    """
    text = f"{title} {description}".lower()
    graph = _get_asset_graph()
    max_score = 0
    affected = []

    # 实体 → 资产映射
    if entities:
        all_entities = (entities.get("companies", []) +
                        entities.get("persons", []) +
                        entities.get("countries", []))
        for ent in all_entities:
            for asset_key, asset_info in graph.items():
                if asset_key == "_description":
                    continue
                stocks = asset_info.get("stocks", [])
                if ent in stocks or any(s.lower() in ent.lower() for s in stocks):
                    if asset_info.get("weight", 0) > max_score:
                        max_score = asset_info["weight"]
                    for s in stocks:
                        if s not in affected:
                            affected.append(s)

    # 关键词 → 资产映射
    for asset_key, asset_info in graph.items():
        if asset_key == "_description":
            continue
        if asset_key.lower() in text:
            weight = asset_info.get("weight", 0)
            if weight > max_score:
                max_score = weight
            for s in asset_info.get("stocks", []):
                if s not in affected:
                    affected.append(s)

    return min(max_score, 20), affected


# ═══════════════════════════════════════════════════════════════════
# 5. Velocity (0-10) — 需要外部传入 velocity_count
# ═══════════════════════════════════════════════════════════════════

def score_velocity(velocity_count: int = 0, velocity_window_minutes: int = 30) -> int:
    """
    传播速度评分。velocity_count = 30分钟内同事件被多少RSS源报道。
    0源 → 0分, 5源 → 5分, 10+源 → 10分
    """
    if velocity_count >= 10:
        return 10
    if velocity_count >= 5:
        return 5
    if velocity_count >= 2:
        return 2
    return 0


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

def score_article(
    source_name: str = "",
    title: str = "",
    description: str = "",
    velocity_count: int = 0,
) -> dict:
    """
    对单篇文章五维评分。

    Args:
        source_name: RSS来源名称
        title: 文章标题
        description: 文章摘要
        velocity_count: 30分钟内同事件被多少源报道

    Returns:
        {
            total: int (0-100),
            source: int, impact: int, entity: int, market: int, velocity: int,
            tier: "A"(>90) | "B"(60-90) | "C"(<60),
            categories: [str],
            entities: {companies, persons, countries},
            market_assets: [str],
            velocity_count: int
        }
    """
    # 1. Source
    src = score_source(source_name)

    # 2. Impact
    imp, categories = score_impact(title, description)

    # 3. Entity
    ent_score, entities = score_entities(title, description)

    # 4. Market
    mkt, market_assets = score_market(title, description, entities)

    # 5. Velocity
    vel = score_velocity(velocity_count)

    total = src + imp + ent_score + mkt + vel
    total = min(total, 100)

    # Tier 划分
    if total >= 90:
        tier = "A"
    elif total >= 60:
        tier = "B"
    else:
        tier = "C"

    return {
        "total": total,
        "source": src,
        "impact": imp,
        "entity": ent_score,
        "market": mkt,
        "velocity": vel,
        "tier": tier,
        "categories": categories,
        "entities": entities,
        "market_assets": market_assets,
        "velocity_count": velocity_count,
    }


# ═══════════════════════════════════════════════════════════════════
# Velocity 计算器（需要跨文章比对）
# ═══════════════════════════════════════════════════════════════════

def _make_fingerprint_set(title: str) -> set:
    """生成标题词集（去停用词、取前8个实词）。"""
    words = re.findall(r"[A-Za-z\u4e00-\u9fff]+", title.lower())
    stops = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
             "to", "for", "of", "and", "or", "it", "this", "that", "with", "has",
             "的", "了", "在", "是", "和", "也", "就", "都", "把", "被", "s", "re", "ve"}
    meaningful = [w for w in words if w not in stops and len(w) > 1]
    return set(meaningful[:8])


def _parse_rss_date(date_str: str) -> datetime:
    """兼容多种 RSS 日期格式。"""
    from email.utils import parsedate_to_datetime
    if not date_str:
        return datetime.utcnow()
    try:
        return parsedate_to_datetime(date_str.strip())
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.utcnow()


def compute_velocity(articles: list[dict], window_minutes: int = 30) -> list[dict]:
    """
    批量计算传播速度。对每篇文章，统计 ±30分钟内同事件（同指纹）的报道数。

    Args:
        articles: [{title, published_at, ...}, ...]
        window_minutes: 时间窗口（分钟）

    Returns:
        原列表，每项增加 velocity_count 字段
    """
    from datetime import timedelta

    if not articles:
        return articles

    # 解析时间
    parsed = []
    for a in articles:
        ts_str = (a.get("published_at") or a.get("date") or "").strip()
        ts = _parse_rss_date(ts_str)
        parsed.append((a, ts))

    window = timedelta(minutes=window_minutes)

    result = []
    for a_i, ts_i in parsed:
        fp_i = _make_fingerprint_set(a_i.get("title", "") or "")
        count = 1  # 至少算自身
        if fp_i and len(fp_i) >= 2:
            for a_j, ts_j in parsed:
                if a_j is a_i:
                    continue
                fp_j = _make_fingerprint_set(a_j.get("title", "") or "")
                # Jaccard 相似度 ≥ 0.5 且 时间窗口内
                if fp_j and len(fp_j) >= 2:
                    intersection = len(fp_i & fp_j)
                    union = len(fp_i | fp_j)
                    if union > 0 and intersection / union >= 0.5 and abs(ts_i - ts_j) <= window:
                        count += 1
        a_i["velocity_count"] = count
        result.append(a_i)

    return result

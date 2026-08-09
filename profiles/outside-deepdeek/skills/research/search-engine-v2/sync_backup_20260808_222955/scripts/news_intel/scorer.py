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

# V4 Feed Registry importance (S/A/B/C/D) → 来源分兜底 (2026-08-07, 联动配置中心)
_IMPORTANCE_SCORE = {"S": 20, "A": 15, "B": 11, "C": 8, "D": 5}
_feed_importance_cache: Optional[dict] = None


def _get_feed_importance() -> dict:
    """从 pipeline 配置 rss.feeds 构建 源名→importance (V4 联动, 懒加载缓存)。

    优先 source_scores.json 精确分; 未收录源用 importance 兜底 (S=20/A=15/B=11/C=8)。
    """
    global _feed_importance_cache
    if _feed_importance_cache is None:
        m = {}
        try:
            from config.loader import load_config
            cfg = load_config()
            for f in cfg.get("rss.feeds") or []:
                if isinstance(f, dict) and f.get("name") and f.get("importance"):
                    m[f["name"]] = f["importance"]
        except Exception:
            pass
        _feed_importance_cache = m
    return _feed_importance_cache


def score_source(source_name: str) -> int:
    """来源权威度评分 (V4: source_scores 精确分优先, importance 兜底, default 最后)"""
    scores = _get_source_scores().get("scores", {})
    if source_name in scores:
        return scores[source_name]
    imp = _get_feed_importance()
    if imp:
        for fn, iv in imp.items():
            if source_name in fn or fn in source_name:
                return _IMPORTANCE_SCORE.get(iv, 8)
    return scores.get("_default", 5)


# ═══════════════════════════════════════════════════════════════════
# 2. Event Impact (0-30)
# ═══════════════════════════════════════════════════════════════════

def _match_keyword(text: str, keyword: str, mode: str) -> bool:
    """关键词匹配 (v2, 2026-08-08): substring | word_boundary。
    word_boundary 用词边界正则, 防短英文词子串误标:
      Fed→Federal / UN→function / war→award / 5G→5GHz。
    """
    if not text or not keyword:
        return False
    if mode == "word_boundary":
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])",
                         text, flags=re.IGNORECASE) is not None
    return keyword.lower() in text.lower()


# 字母数 >3 但仍需词边界的英文词 (子串误标风险高: coup→coupon / NATO→alternator / nuclear→NuclearDiffusion / election→selection)
_WORD_BOUNDARY_FORCE = {"coup", "NATO", "nuclear", "election"}


def _kw_match_mode(keyword: str) -> str:
    """自动推断关键词匹配模式 (v2, 2026-08-08):
    - 含中文 → substring (中文无词边界概念)
    - 多词短语 (含空格) → substring (保证 bank failures 命中 bank failure)
    - 短英文词/缩写 (字母≤3, 或高风险词) → word_boundary
      (防子串误标: un→function / fed→federal / war→forward·award / coup→coupon / dow→downtown / 5g→5ghz)
    - 常规英文词 (字母>3, 如 chip/crash/strike/missile) → substring (保复数/派生召回: chips/crashes/strikes)
    """
    if any('一' <= ch <= '鿿' for ch in keyword):
        return "substring"
    if " " in keyword:
        return "substring"
    if keyword in _WORD_BOUNDARY_FORCE or len(re.sub(r"[^A-Za-z]", "", keyword)) <= 3:
        return "word_boundary"
    return "substring"


def score_impact(title: str, description: str = "") -> tuple[int, list[str], list[dict]]:
    """事件影响力评分 (v2, 500 关键词 2026-08-08)。
    返回 (分数, 命中的分类列表, hits 详情)。
    兼容 int 值关键词 (自动推断 match 模式) 与 dict 值 ({score, match, event_type})。
    每分类取最高、跨分类只取所有分类最高 (不累加, 防标题党刷分)。
    """
    text = f"{title or ''} {description or ''}"
    keywords = _get_event_keywords()
    max_score = 0
    hit_categories: list[str] = []
    hits: list[dict] = []

    for category, kw_dict in keywords.items():
        if category.startswith("_"):
            continue
        cat_best = 0
        cat_hits: list[dict] = []
        for keyword, meta in kw_dict.items():
            if isinstance(meta, dict):
                score = int(meta.get("score", 0))
                mode = meta.get("match") or _kw_match_mode(keyword)
                ev_type = meta.get("event_type")
            else:
                score = int(meta)
                mode = _kw_match_mode(keyword)
                ev_type = None
            if score <= 0:
                continue
            if _match_keyword(text, keyword, mode):
                cat_hits.append({"keyword": keyword, "score": score, "event_type": ev_type})
                if score > cat_best:
                    cat_best = score
        if cat_best > 0:
            hit_categories.append(category)
            if cat_best > max_score:
                max_score = cat_best
            hits.extend(cat_hits)

    return min(max_score, 30), hit_categories, hits


# ═══════════════════════════════════════════════════════════════════
# 3. Entity Importance (0-20)
# ═══════════════════════════════════════════════════════════════════

def _entity_in_text(name: str, text: str) -> bool:
    """实体名匹配规则 (v4.4.2 修复子串误标根因)。

    旧逻辑 `name in text` 是子串匹配, 短名会误命中任何含该子串的文本:
      例: 'Xi'(习近平) 命中每篇 ML 论文摘要里的希腊字母 ξ/xi 及 fixing/proximity 里的 'xi';
          'US'/'BP'/'UK' 命中任意含 us/bp/uk 的文本。
    修复: CJK 名无词边界 → 子串匹配; 拉丁名 → 词边界 + 短名(≤3字符)大小写敏感。
    """
    if any('一' <= ch <= '鿿' for ch in name):
        return name in text
    pat = rf'\b{re.escape(name)}\b'
    if len(name) <= 3:
        return re.search(pat, text) is not None
    return re.search(pat, text, re.IGNORECASE) is not None


def score_entities(title: str, description: str = "") -> tuple[int, dict]:
    """
    实体重要性评分。从标题+摘要中匹配已知重要实体 (词边界, 非子串)。
    返回 (分数, {companies: [...], persons: [...], countries: [...], organizations: [...]})
    v1.4 (2026-08-08): 新增 organizations 类目 (央行/国际组织/政府机构, 独立于关键词表)。
    """
    text = f"{title} {description}"
    weights = _get_entity_weights()
    found = {"companies": [], "persons": [], "countries": [], "organizations": []}
    max_score = 0

    for etype, entities in weights.items():
        if etype == "_description":
            continue
        for name, weight in entities.items():
            if _entity_in_text(name, text):
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
    v2 (2026-08-08): 关键词路径复用 _kw_match_mode 词边界匹配, 修复 EV/war/oil 子串误标。
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

    # 关键词 → 资产映射 (v2: word_boundary 防 EV→every/war→forward/oil→soil 误标)
    for asset_key, asset_info in graph.items():
        if asset_key == "_description":
            continue
        if _match_keyword(text, asset_key, _kw_match_mode(asset_key)):
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
    imp, categories, impact_hits = score_impact(title, description)

    # 3. Entity
    ent_score, entities = score_entities(title, description)

    # 4. Market
    mkt, market_assets = score_market(title, description, entities)

    # 5. Velocity
    vel = score_velocity(velocity_count)

    # 6. 价值奖励 (v2.2): 对投资/全球局势/金融市场高价值文章加权
    reward = _value_reward(src, categories, market_assets, velocity_count)

    total = src + imp + ent_score + mkt + vel + reward
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
        "reward": reward,
        "tier": tier,
        "categories": categories,
        "entities": entities,
        "market_assets": market_assets,
        "velocity_count": velocity_count,
        "impact_hits": impact_hits,
    }


def _value_reward(source_score: int, categories: list, market_assets: list, velocity_count: int) -> int:
    """价值奖励分 (0-15, v2.2 2026-08-08)。

    目的: 把对【投资/全球局势/金融市场】有价值的文章升入 B/A 级, 获得 LLM 深度增强,
    避免高价值文章因五维保守(平均 27.9, B 级仅 4.6%)被淹没在 C 级。

    奖励来源:
      - 权威源报道 (来源权威 ≥16)      +4  (可信度高 → 更有价值)
      - 高价值领域关键词命中 (分类)      finance +5 / geopolitics +6 / market +5 / china +3
        (投资/地缘/市场正是用户筛选目标; ai_tech 不直接奖励, 防学术噪音)
      - 市场资产关联 (涉及可交易资产)    +3  (直接投资相关)
      - 多源并发报道 (velocity_count≥2) +3  (被多源关注 → 事件重要性)

    可经配置中心「评分」Tab 覆盖: value.reward_source/impact/market/velocity/cap。
    """
    reward = 0
    if source_score >= 16:
        reward += _value_reward_cfg("source", 4)
    for c in categories:
        if c == "finance":
            reward += _value_reward_cfg("finance", 5)
        elif c == "geopolitics":
            reward += _value_reward_cfg("geopolitics", 6)
        elif c == "market":
            reward += _value_reward_cfg("market", 5)
        elif c == "china":
            reward += _value_reward_cfg("china", 3)
    if market_assets:
        reward += _value_reward_cfg("market_assets", 3)
    if velocity_count >= 2:
        reward += _value_reward_cfg("velocity", 3)
    return min(reward, _value_reward_cfg("cap", 20))


def _value_reward_cfg(key: str, default: int) -> int:
    """价值奖励权重配置 (v2.2): 优先配置中心, 回退默认。"""
    try:
        from config.loader import get_setting
        cfg = get_setting(_get_loader_cfg(), f"value.reward_{key}", default)
        return int(cfg)
    except Exception:
        return default


def _get_loader_cfg() -> dict:
    """读取 pipeline 配置 (懒加载缓存, 供奖励权重覆盖)。"""
    global _loader_cfg_cache
    if _loader_cfg_cache is None:
        try:
            from config.loader import load_config
            _loader_cfg_cache = load_config()
        except Exception:
            _loader_cfg_cache = {}
    return _loader_cfg_cache


_loader_cfg_cache: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════
# Velocity 计算器（需要跨文章比对）
# ═══════════════════════════════════════════════════════════════════

def _make_fingerprint_set(title: str) -> set:
    """生成标题词集（去停用词、取前8个实词）。"""
    words = re.findall(r"[A-Za-z\u4e00-\u9fff]+", title.lower())
    # v2.1 (2026-08-08): 补全英文功能词停用表 (as/amid/by/from/介词/连词/代词/助动词)
    # + 常见新闻框架词 (says/said/new/latest/live/breaking), 提升 Jaccard 判同精度。
    stops = {
        # 冠词/限定词
        "the", "a", "an", "this", "that", "these", "those", "some", "any", "all",
        "each", "every", "both", "either", "neither", "no", "another", "such",
        # 介词
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "over",
        "under", "above", "below", "between", "among", "through", "during", "after",
        "before", "into", "within", "without", "against", "about", "across",
        "along", "around", "behind", "beside", "beyond", "despite", "near", "off",
        "per", "since", "toward", "towards", "upon", "via", "amid",
        # 连词
        "and", "or", "but", "so", "if", "then", "than", "because", "while",
        "although", "though", "until", "unless", "whether", "nor",
        # 代词
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
        "them", "my", "your", "his", "its", "our", "their", "who", "whom",
        "whose", "which", "what", "when", "where", "why", "how",
        # 系动词/助动词
        "is", "are", "was", "were", "be", "been", "being", "am", "has", "have",
        "had", "do", "does", "did", "will", "would", "shall", "should", "can",
        "could", "may", "might", "must", "ought",
        # 副词
        "not", "only", "just", "also", "too", "very", "quite", "rather", "still",
        "even", "again", "ever", "never", "already", "yet", "soon", "here", "there",
        # 新闻框架词 (低判别力)
        "says", "said", "say", "new", "latest", "live", "breaking", "update",
        "updates", "video", "watch", "photos", "photo",
        # 中文功能词 (单字已被 len>1 过滤; 双字功能词补充)
        "的", "了", "在", "是", "和", "也", "就", "都", "把", "被",
        "对于", "由于", "以及", "因为", "所以", "虽然", "但是",
        # 英文缩写后缀 (he's/we're/I'll...)
        "s", "re", "ve", "ll", "d", "m",
    }
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

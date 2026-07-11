"""
news_intel/aggregator.py — L8 事件聚合器 v4

Event-Centric Incremental Clustering:
  1. 每篇文章提取 EventFingerprint (SAEO + Topic + Location)
  2. 与现有事件库匹配 → 加入或创建新事件
  3. Location 硬约束: 不同国家 → 绝不合并
  4. 时间用事件生命周期, 非固定窗口

EventFingerprint = {
  subject, action, object, event_type,
  primary_topic, secondary_topic,
  country, start_time, last_time
}
"""
import re, json, logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 动作词库 (Action → EventType 映射)
# ═══════════════════════════════════════════════════════════

ACTION_MAP = {
    "SUES":       ("Legal",      [r"\b(sues?|suing|lawsuit|litigation|sue|alleges?|accuses?|files?\s+(a\s+)?lawsuit|complaint|indictment|trade\s+secret)\b"]),
    "ATTACKS":    ("Military",   [r"\b(attacks?|strikes?|bomb(?:s|ed|ing)|missile|drone\s+strike|airstrike|assault|offensive)\b"]),
    "SANCTIONS":  ("Economic",   [r"\b(sanctions?|tariffs?|embargo|blacklist|restricts?|bans?|blocks?)\b"]),
    "NEGOTIATES": ("Diplomacy",  [r"\b(talks?|negotiat(?:es?|ion)|diploma(?:cy|tic)|ceasefire|truce|peace\s+deal|agreement)\b"]),
    "ANNOUNCES":  ("Politics",   [r"\b(announces?|declares?|reveals?|unveils?|launches?|releases?|presents?)\b"]),
    "ELECTS":     ("Politics",   [r"\b(elect(?:s|ed|ion)|votes?|voting|ballot|campaign|candidate)\b"]),
    "DIES":       ("Leadership", [r"\b(dies?|dead|killed|death|funeral|burial|assassinated|mourns?)\b"]),
    "CRASHES":    ("Finance",    [r"\b(crash(?:es|ed)?|plunge(?:s|d)?|plummets?|tumbles?|slides?|sell.?off)\b"]),
    "SURGES":     ("Finance",    [r"\b(surges?|soars?|jumps?|rall(?:y|ies|ied)|climbs?|rises?)\b"]),
    "CUTS":       ("Economic",   [r"\b(cuts?|reduces?|slashes?|lowers?|drops?)\b"]),
    "REPORTS":    ("Finance",    [r"\b(reports?|earnings|revenue|profit|quarterly|fiscal)\b"]),
    "DEVELOPS":   ("Technology", [r"\b(develops?|builds?|creates?|produces?|manufactures?)\b"]),
    "BANS":       ("Legal",      [r"\b(bans?|prohibits?|outlaws?|restricts?|blocks?)\b"]),
    "FUNDS":      ("Economic",   [r"\b(funds?|funding|invests?|investment|financ(?:es?|ing)|grant)\b"]),
    "WARNS":      ("Politics",   [r"\b(warns?|cautions?|alerts?|advises?)\b"]),
}


def _detect_action(text: str) -> tuple[str, str]:
    """返回 (action, event_type)"""
    text_lower = text.lower()
    for action, (etype, patterns) in ACTION_MAP.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                return (action, etype)
    return ("OTHER", "General")


# ═══════════════════════════════════════════════════════════
# Topic 分类 (Primary + Secondary)
# ═══════════════════════════════════════════════════════════

TOPIC_SIGNALS = {
    "Legal":       ["lawsuit","sue","court","judge","attorney","trial","ruling","verdict","legal","trade secret","indictment","plead","guilty","prosecutor"],
    "Military":    ["war","strike","missile","troops","military","attack","drone","combat","aircraft","navy","army","bomb","weapon","invasion","raid","defense"],
    "Diplomacy":   ["ceasefire","negotiation","talks","diplomat","treaty","summit","agreement","peace deal","truce","dialogue","UN","NATO"],
    "Economic":    ["tariff","sanction","trade","economy","import","export","inflation","GDP","recession","commodity","sanction","embargo"],
    "Finance":     ["stock","earnings","revenue","profit","IPO","merger","acquisition","shares","investor","Wall Street","NASDAQ","S&P","dollar","bond","market","oil price","surge","crash","record high"],
    "Politics":    ["election","vote","candidate","president","senate","congress","parliament","bill","legislation","administration","governor","mayor","govern"],
    "Technology":  ["AI","artificial intelligence","OpenAI","GPU","chip","software","startup","tech","algorithm","robot","autonomous","cyber","EV","electric vehicle"],
    "Energy":      ["oil","gas","energy","pipeline","OPEC","refinery","solar","wind","nuclear","fuel","barrel","crude","power","electricity"],
    "Health":      ["covid","vaccine","hospital","disease","outbreak","pandemic","virus","drug","FDA","pharma","patient","clinical","cancer","screening"],
    "Sports":      ["World Cup","quarterfinal","semifinal","tournament","match","goal","stadium","player","team","league","championship","fans"],
    "Leadership":  ["funeral","succession","appointed","resign","chairman","CEO","executive","board","leadership","departure","nominated"],
    "Disaster":    ["earthquake","flood","hurricane","typhoon","tsunami","wildfire","collapse","explosion","accident","blackout"],
}


def _classify_topics(text: str) -> tuple[str, str]:
    """返回 (primary_topic, secondary_topic)"""
    text_lower = text.lower()
    scores = defaultdict(int)
    for topic, keywords in TOPIC_SIGNALS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                scores[topic] += 1
    ranked = sorted(scores, key=scores.get, reverse=True)
    primary = ranked[0] if ranked else "General"
    secondary = ranked[1] if len(ranked) > 1 else ""
    return (primary, secondary)


# ═══════════════════════════════════════════════════════════
# Country 提取
# ═══════════════════════════════════════════════════════════

COUNTRIES = [
    "US","USA","United States","Iran","Ukraine","Russia","China","UK","Britain",
    "France","Germany","Japan","India","Israel","Albania","Vietnam","Cuba",
    "North Korea","South Korea","Taiwan","Canada","Australia","Brazil","Mexico",
    "Italy","Spain","Poland","Turkey","Saudi Arabia","UAE","Switzerland",
    "Sweden","Norway","Netherlands","Belgium","Austria","Greece","Portugal",
    "Argentina","Chile","Colombia","Peru","Egypt","Nigeria","South Africa",
    "Kenya","Indonesia","Malaysia","Philippines","Thailand","Singapore",
    "Pakistan","Bangladesh","Iraq","Syria","Afghanistan","Lebanon",
]


def _extract_country(entities: dict, text: str) -> str | None:
    """提取首要国家"""
    e = entities or {}
    countries = list(e.get("countries", []))
    if countries:
        return countries[0]
    for c in COUNTRIES:
        if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
            return c
    return None


# ═══════════════════════════════════════════════════════════
# EventFingerprint 构建
# ═══════════════════════════════════════════════════════════

def _get_text(a: dict) -> str:
    desc = a.get("description") or a.get("summary_cn") or a.get("summary") or ""
    if desc and not desc.startswith("<table") and not desc.startswith("<tr"):
        if (desc.count("<") + desc.count(">")) / max(len(desc), 1) < 0.3:
            desc = desc[:500]
        else:
            desc = ""
    return desc + " " + (a.get("title") or "")


def build_fingerprint(article: dict) -> dict:
    """
    构建事件指纹
    返回: {subject, action, object, event_type, primary_topic, secondary_topic, country}
    """
    text = _get_text(article)
    action, event_type = _detect_action(text)
    primary, secondary = _classify_topics(text)

    entities = article.get("entities", {}) or {}
    # Subject = 第一个公司或人物
    subjects = (entities.get("companies", []) + entities.get("persons", []))[:2]
    subject = subjects[0] if subjects else ""
    # Object = 国家 或 第二个实体
    objects = entities.get("countries", []) + entities.get("companies", [])
    obj = objects[0] if objects else ""
    if obj == subject and len(objects) > 1:
        obj = objects[1]

    country = _extract_country(entities, text)

    return {
        "subject": subject,
        "action": action,
        "object": obj,
        "event_type": event_type,
        "primary_topic": primary,
        "secondary_topic": secondary,
        "country": country,
    }


def fingerprint_score(fp1: dict, fp2: dict) -> int:
    """
    两个指纹的匹配分 (0-100)
    Location 不同 → 直接 0
    """
    # ── Hard constraint: 不同国家 → 0 ──
    if fp1["country"] and fp2["country"] and fp1["country"] != fp2["country"]:
        return 0

    score = 0

    # Action (35)
    if fp1["action"] == fp2["action"] and fp1["action"] != "OTHER":
        score += 35

    # Subject (25)
    if fp1["subject"] and fp2["subject"]:
        if fp1["subject"] == fp2["subject"] or fp1["subject"] in fp2["subject"] or fp2["subject"] in fp1["subject"]:
            score += 25

    # Object (20)
    if fp1["object"] and fp2["object"]:
        if fp1["object"] == fp2["object"] or fp1["object"] in fp2["object"] or fp2["object"] in fp1["object"]:
            score += 20

    # Primary Topic (15)
    if fp1["primary_topic"] == fp2["primary_topic"]:
        score += 15
    elif fp1["secondary_topic"] and fp2["secondary_topic"] and fp1["secondary_topic"] == fp2["secondary_topic"]:
        score += 5

    # Event Type (5)
    if fp1["event_type"] == fp2["event_type"]:
        score += 5

    return score


# ═══════════════════════════════════════════════════════════
# Event-Centric Clustering V4 (frozen)
# ═══════════════════════════════════════════════════════════

EVENT_THRESHOLD = 50
MERGE_THRESHOLD = 70   # 事件间合并阈值（高于文章→事件）


def _parse_date(date_str) -> datetime | None:
    """兼容 ISO 和 RSS 日期格式。不可解析返回 None"""
    from email.utils import parsedate_to_datetime
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    try:
        return parsedate_to_datetime(date_str.strip())
    except (ValueError, TypeError):
        return None


def aggregate_events(articles: list[dict], window_hours: int = 24) -> list[dict]:
    """
    V4 标准流程 (frozen):

    Phase 1: Article → Event (Event-Centric Clustering)
      - 文章按时间升序排列（最早的文章先建事件）
      - 新文章与已有事件中心指纹比较
      - 得分 ≥ 50 → 加入事件, 否则 → 新建事件

    Phase 2: Event → Event (事件间合并)
      - 两两比较事件中心指纹
      - 得分 ≥ 70 且时间窗口内 → 合并事件
      - 消除因文章排序导致的事件拆分

    Phase 3: Filter
      - 过滤单篇文章事件
      - 计算 impact_level
    """
    if not articles:
        return []

    # ── 按时间升序排列（最早在前）──
    parsed = []
    for a in articles:
        ts = _parse_date(a.get("published_at"))
        parsed.append((a, ts))
    # None 放最后
    parsed.sort(key=lambda x: (x[1] is None, x[1] or datetime.min))

    # ═══════════════════════════════════════════════════
    # Phase 1: Article → Event
    # ═══════════════════════════════════════════════════

    events = []

    for a, ts in parsed:
        fp = build_fingerprint(a)
        best_score = 0
        best_event = None

        for ev in events:
            if ev["last_time"] and ts and abs(ts - ev["last_time"]) > timedelta(hours=window_hours):
                continue
            score = fingerprint_score(fp, ev["fingerprint"])
            if score > best_score and score >= EVENT_THRESHOLD:
                best_score = score
                best_event = ev

        if best_event:
            best_event["article_ids"].append(a["id"])
            best_event["last_time"] = max(best_event["last_time"] or ts, ts) if ts else best_event["last_time"]
            if ts and (ts < (best_event.get("start_time") or ts)):
                best_event["start_time"] = ts
            e = a.get("entities", {}) or {}
            best_event["all_entities"].update(e.get("companies", []))
            best_event["all_entities"].update(e.get("persons", []))
            best_event["all_entities"].update(e.get("countries", []))
            best_event["max_score"] = max(best_event.get("max_score", 0), a.get("score_total", 0))
            best_event["actions"].add(fp["action"])
            best_event["topics"].add(fp["primary_topic"])
            # 保留最长标题
            if len(a.get("title", "")) > len(best_event.get("best_title", "")):
                best_event["best_title"] = a["title"]
        else:
            e = a.get("entities", {}) or {}
            all_ents = set()
            all_ents.update(e.get("companies", []))
            all_ents.update(e.get("persons", []))
            all_ents.update(e.get("countries", []))
            events.append({
                "fingerprint": fp,
                "article_ids": [a["id"]],
                "start_time": ts,
                "last_time": ts,
                "all_entities": all_ents,
                "max_score": a.get("score_total", 0),
                "actions": {fp["action"]},
                "topics": {fp["primary_topic"]},
                "best_title": a.get("title", ""),
            })

    # ═══════════════════════════════════════════════════
    # Phase 2: Event → Event 合并
    # ═══════════════════════════════════════════════════

    n = len(events)
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
        for j in range(i + 1, n):
            ev_i = events[i]
            ev_j = events[j]
            # 时间窗口
            if ev_i["last_time"] and ev_j["start_time"]:
                if abs(ev_i["last_time"] - ev_j["start_time"]) > timedelta(hours=window_hours):
                    continue
            score = fingerprint_score(ev_i["fingerprint"], ev_j["fingerprint"])
            if score >= MERGE_THRESHOLD:
                union(i, j)

    # 合并事件
    merged = []
    done = set()
    for i in range(n):
        root = find(i)
        if root in done:
            continue
        done.add(root)
        group = [j for j in range(n) if find(j) == root]
        if len(group) == 1:
            merged.append(events[group[0]])
        else:
            # 合并多个事件
            m = events[group[0]]
            for j in group[1:]:
                ej = events[j]
                m["article_ids"].extend(ej["article_ids"])
                m["start_time"] = min(m["start_time"] or ej["start_time"], ej["start_time"] or m["start_time"])
                m["last_time"] = max(m["last_time"] or ej["last_time"], ej["last_time"] or m["last_time"])
                m["all_entities"].update(ej["all_entities"])
                m["max_score"] = max(m["max_score"], ej["max_score"])
                m["actions"].update(ej["actions"])
                m["topics"].update(ej["topics"])
                if len(ej.get("best_title", "")) > len(m.get("best_title", "")):
                    m["best_title"] = ej["best_title"]
            merged.append(m)

    # ═══════════════════════════════════════════════════
    # Phase 3: Output
    # ═══════════════════════════════════════════════════

    result = []
    for ev in merged:
        if len(ev["article_ids"]) < 2:
            continue
        impact = "HIGH" if ev["max_score"] >= 85 else ("MEDIUM" if ev["max_score"] >= 60 else "LOW")
        result.append({
            "title": ev["best_title"],
            "article_ids": ev["article_ids"],
            "article_count": len(ev["article_ids"]),
            "entities": list(ev["all_entities"]),
            "impact_level": impact,
            "max_score": ev["max_score"],
            "actions": list(ev["actions"]),
            "topics": list(ev["topics"]),
            "start_time": ev["start_time"],
            "last_time": ev["last_time"],
        })

    result.sort(key=lambda e: e["article_count"], reverse=True)
    return result

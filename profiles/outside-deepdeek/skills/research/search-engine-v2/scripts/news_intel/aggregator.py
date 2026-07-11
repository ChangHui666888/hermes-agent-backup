"""
news_intel/aggregator.py — L8 事件聚合器 v4.2

V4.2 改进:
  1. Entity Alias V2 (Government/Military/Org aliases)
  2. Entity Type Weight 调整 (Person→0.5, Gov=1.0, Military=1.0)
  3. Topic IDF (global_idf × topic_idf)
  4. Action Hierarchy (二级动作拆分)
  5. Score 重平衡 (Object↑30, Action↓25)
  6. Event Participants (替代 Location 硬约束)
"""
import re, json, logging, math
from datetime import datetime, timedelta
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# V4.2: Entity Alias Dictionary V2
# ═══════════════════════════════════════════════════════════

ENTITY_CANONICAL = {
    # Countries
    "US": "United States", "USA": "United States", "U.S.": "United States",
    "America": "United States",
    "UK": "United Kingdom", "Britain": "United Kingdom", "Great Britain": "United Kingdom",
    "Russia": "Russian Federation", "Russian": "Russian Federation",
    "China": "China", "PRC": "China", "Mainland China": "China",
    "Iran": "Iran", "Islamic Republic of Iran": "Iran", "Tehran": "Iran",
    "North Korea": "North Korea", "DPRK": "North Korea",
    "South Korea": "South Korea", "Korea": "South Korea",
    "Germany": "Germany", "France": "France", "Japan": "Japan", "India": "India",
    "Israel": "Israel", "Ukraine": "Ukraine",
    "European Union": "European Union", "EU": "European Union",
    "United Nations": "United Nations", "UN": "United Nations",
    "NATO": "NATO",
    # Government aliases
    "White House": "United States Government", "Washington": "United States Government",
    "Kremlin": "Russian Federation Government", "Moscow": "Russian Federation Government",
    "Beijing": "Chinese Government",
    "Tehran": "Iranian Government",
    "Pyongyang": "North Korean Government",
    "Pentagon": "United States Department of Defense",
    "Centcom": "United States Central Command",
    "IRGC": "Islamic Revolutionary Guard Corps",
    "IDF": "Israel Defense Forces",
    # Finance
    "Federal Reserve": "Federal Reserve", "Fed Chair": "Federal Reserve",
    "ECB": "European Central Bank", "BOE": "Bank of England", "BoE": "Bank of England",
    "IMF": "International Monetary Fund", "World Bank": "World Bank",
    # Organizations
    "OPEC": "OPEC", "WHO": "World Health Organization", "WTO": "World Trade Organization",
}

ENTITY_TYPE_WEIGHT = {
    "Country": 1.0,
    "Government": 1.0,
    "Military": 1.0,
    "Organization": 0.8,
    "Company": 0.8,
    "Person": 0.5,
    "Location": 0.4,
    "Other": 0.2,
}

_known_entity_types = {}


def _canonicalize(name: str) -> str:
    return ENTITY_CANONICAL.get(name, name)


def _infer_entity_type(name: str, raw_entities: dict) -> str:
    """推断实体类型（含 Government/Military 扩展）"""
    # 先检查原始分类
    for cat, etype in [("countries", "Country"), ("companies", "Company"), ("persons", "Person")]:
        if name in (raw_entities or {}).get(cat, []):
            return etype
    # 关键字推断
    canonical = _canonicalize(name)
    if any(kw in canonical for kw in ["Government", "Department", "Ministry", "Administration"]):
        return "Government"
    if any(kw in canonical for kw in ["Defense", "Military", "Army", "Navy", "Guard", "Forces"]):
        return "Military"
    return "Other"


# ═══════════════════════════════════════════════════════════
# V4.2: Action Hierarchy (一级16种 + 二级子类)
# ═══════════════════════════════════════════════════════════

ACTION_MAP = {
    "SUES":        ("Legal",     [r"\b(sues?|suing|lawsuit|litigation|files?\s+(a\s+)?lawsuit|complaint|indictment|trade\s+secret)\b"]),
    "ACCUSES":     ("Legal",     [r"\b(alleges?|accuses?|charges?)\b"]),
    "ATTACKS":     ("Military",  [r"\b(attacks?|strikes?|bomb(?:s|ed|ing)|missile|drone\s+strike|airstrike|assault|offensive)\b"]),
    "CEASEFIRE":   ("Diplomacy", [r"\b(ceasefire|truce)\b"]),
    "PEACE_DEAL":  ("Diplomacy", [r"\b(peace\s+deal|peace\s+agreement|peace\s+treaty)\b"]),
    "NEGOTIATES":  ("Diplomacy", [r"\b(talks?|negotiat(?:es?|ion)|diploma(?:cy|tic))\b"]),
    "SANCTIONS":   ("Economic",  [r"\b(sanctions?|embargo|blacklist)\b"]),
    "TARIFFS":     ("Economic",  [r"\b(tariffs?|trade\s+war|import\s+duty)\b"]),
    "RATE_CUT":    ("Finance",   [r"\b(cuts?\s+(interest\s+)?rates?|lowers?\s+(interest\s+)?rates?|rate\s+cut)\b"]),
    "RATE_HIKE":   ("Finance",   [r"\b(raises?\s+(interest\s+)?rates?|hikes?\s+(interest\s+)?rates?|rate\s+hike)\b"]),
    "ANNOUNCES":   ("Politics",  [r"\b(announces?|declares?|reveals?|unveils?|launches?|releases?|presents?)\b"]),
    "ELECTS":      ("Politics",  [r"\b(elect(?:s|ed|ion)|votes?|voting|ballot|campaign|candidate)\b"]),
    "DIES":        ("Leadership",[r"\b(dies?|dead|killed|death|funeral|burial|assassinated|mourns?)\b"]),
    "CRASHES":     ("Finance",   [r"\b(crash(?:es|ed)?|plunge(?:s|d)?|plummets?|tumbles?|slides?|sell.?off)\b"]),
    "SURGES":      ("Finance",   [r"\b(surges?|soars?|jumps?|rall(?:y|ies|ied)|climbs?|rises?|record\s+high)\b"]),
    "CUTS":        ("Economic",  [r"\b(cuts?|reduces?|slashes?|lowers?|drops?)\b"]),
    "REPORTS":     ("Finance",   [r"\b(reports?|earnings|revenue|profit|quarterly|fiscal)\b"]),
    "DEVELOPS":    ("Technology",[r"\b(develops?|builds?|creates?|manufactures?)\b"]),
    "BANS":        ("Legal",     [r"\b(bans?|prohibits?|outlaws?|restricts?|blocks?)\b"]),
    "FUNDS":       ("Economic",  [r"\b(funds?|funding|invests?|investment|financ(?:es?|ing)|grant)\b"]),
    "WARNS":       ("Politics",  [r"\b(warns?|cautions?|alerts?|advises?|threatens?\s+to)\b"]),
}


def _detect_action(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    for action, (etype, patterns) in ACTION_MAP.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                return (action, etype)
    return ("OTHER", "General")


# ═══════════════════════════════════════════════════════════
# Topic classification
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
# Country / Participants
# ═══════════════════════════════════════════════════════════

COUNTRIES = [
    "United States","US","USA","Iran","Ukraine","Russia","China","United Kingdom","UK","Britain",
    "France","Germany","Japan","India","Israel","Albania","Vietnam","Cuba",
    "North Korea","South Korea","Taiwan","Canada","Australia","Brazil","Mexico",
    "Italy","Spain","Poland","Turkey","Saudi Arabia","UAE","Switzerland",
    "Sweden","Norway","Netherlands","Belgium","Austria","Greece","Portugal",
    "Argentina","Chile","Colombia","Peru","Egypt","Nigeria","South Africa",
    "Kenya","Indonesia","Malaysia","Philippines","Thailand","Singapore",
    "Pakistan","Bangladesh","Iraq","Syria","Afghanistan","Lebanon",
]


def _extract_participants(entities: dict, text: str) -> set:
    """V4.2: 提取事件参与国 (actor + target + affected)"""
    participants = set()
    e = entities or {}
    for c in e.get("countries", []):
        participants.add(_canonicalize(c))
    for c in COUNTRIES:
        if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
            participants.add(_canonicalize(c))
    return participants


# ═══════════════════════════════════════════════════════════
# V4.2: Entity IDF with Topic IDF
# ═══════════════════════════════════════════════════════════

def _compute_entity_idf(articles: list[dict]) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """返回 (global_idf, topic_idf_map)"""
    N = len(articles)
    if N == 0:
        return {}, {}
    global_counter = Counter()
    topic_counters = defaultdict(Counter)
    topic_total = defaultdict(int)

    for a in articles:
        text = _get_text(a)
        primary, _ = _classify_topics(text)
        topic_total[primary] += 1

        e = a.get("entities", {}) or {}
        names = set()
        for cat in ("companies", "persons", "countries"):
            for name in e.get(cat, []):
                names.add(_canonicalize(name))
        global_counter.update(names)
        for name in names:
            topic_counters[primary][name] += 1

    global_idf = {name: math.log(N / max(freq, 1)) for name, freq in global_counter.items()}
    topic_idf = {}
    for topic, counter in topic_counters.items():
        total = topic_total[topic]
        topic_idf[topic] = {name: math.log(total / max(freq, 1)) for name, freq in counter.items()}

    return global_idf, topic_idf


def _entity_weight(name: str, global_idf: dict, topic_idf_map: dict, primary_topic: str) -> float:
    """V4.2: type_weight × global_idf × topic_idf"""
    canonical = _canonicalize(name)
    etype = _known_entity_types.get(canonical, "Other")
    type_w = ENTITY_TYPE_WEIGHT.get(etype, 0.2)
    g_idf = min(global_idf.get(canonical, 1.0), 2.0) / 2.0
    t_idf_map = topic_idf_map.get(primary_topic, {})
    t_idf = min(t_idf_map.get(canonical, 1.0), 2.0) / 2.0
    return type_w * (0.2 + 0.4 * g_idf + 0.4 * t_idf)


# ═══════════════════════════════════════════════════════════
# V4.2: EventFingerprint
# ═══════════════════════════════════════════════════════════

def _get_text(a: dict) -> str:
    desc = a.get("description") or a.get("summary_cn") or a.get("summary") or ""
    if desc and not desc.startswith("<table") and not desc.startswith("<tr"):
        if (desc.count("<") + desc.count(">")) / max(len(desc), 1) < 0.3:
            desc = desc[:500]
        else:
            desc = ""
    return desc + " " + (a.get("title") or "")


def build_fingerprint(article: dict, global_idf: dict = None, topic_idf_map: dict = None) -> dict:
    global_idf = global_idf or {}
    topic_idf_map = topic_idf_map or {}
    text = _get_text(article)
    action, event_type = _detect_action(text)
    primary, secondary = _classify_topics(text)

    entities = article.get("entities", {}) or {}

    # 加权选择 Subject
    candidates = []
    for name in entities.get("companies", []) + entities.get("persons", []):
        canonical = _canonicalize(name)
        w = _entity_weight(name, global_idf, topic_idf_map, primary)
        candidates.append((canonical, w))
    candidates.sort(key=lambda x: x[1], reverse=True)
    subject = candidates[0][0] if candidates else ""

    # 加权选择 Object
    obj_candidates = []
    for name in entities.get("countries", []) + entities.get("companies", []):
        canonical = _canonicalize(name)
        if canonical == subject:
            continue
        w = _entity_weight(name, global_idf, topic_idf_map, primary)
        obj_candidates.append((canonical, w))
    obj_candidates.sort(key=lambda x: x[1], reverse=True)
    obj = obj_candidates[0][0] if obj_candidates else ""

    # Primary country for hard constraint
    countries = entities.get("countries", [])
    country = _canonicalize(countries[0]) if countries else None

    # Participants (全部相关国家)
    participants = _extract_participants(entities, text)

    # SAO Anchor
    anchor = f"{subject}|{action}|{obj}|{primary}" if subject and action != "OTHER" else ""

    return {
        "subject": subject,
        "action": action,
        "object": obj,
        "event_type": event_type,
        "primary_topic": primary,
        "secondary_topic": secondary,
        "country": country,
        "participants": frozenset(participants),
        "anchor": anchor,
    }


def fingerprint_score(fp1: dict, fp2: dict) -> int:
    """
    V4.2.1: Location 硬约束 + Participants 加分
    """
    # ── Hard constraint: 主要国家不同 → 0 ──
    if fp1.get("country") and fp2.get("country") and fp1["country"] != fp2["country"]:
        return 0

    # Anchor 完全匹配 → 强行满分
    if fp1.get("anchor") and fp2.get("anchor") and fp1["anchor"] == fp2["anchor"]:
        return 100

    score = 0

    # Action (25)
    if fp1["action"] == fp2["action"] and fp1["action"] != "OTHER":
        score += 25

    # Subject (25)
    if fp1["subject"] and fp2["subject"]:
        if fp1["subject"] == fp2["subject"] or fp1["subject"] in fp2["subject"] or fp2["subject"] in fp1["subject"]:
            score += 25

    # Object (30)
    if fp1["object"] and fp2["object"]:
        if fp1["object"] == fp2["object"] or fp1["object"] in fp2["object"] or fp2["object"] in fp1["object"]:
            score += 30

    # Topic (10)
    if fp1["primary_topic"] == fp2["primary_topic"]:
        score += 10
    elif fp1["secondary_topic"] and fp2["secondary_topic"] and fp1["secondary_topic"] == fp2["secondary_topic"]:
        score += 5

    # Event Type (10)
    if fp1["event_type"] == fp2["event_type"]:
        score += 10

    # Participants 重叠加分 (bonus only)
    p1 = fp1.get("participants", frozenset())
    p2 = fp2.get("participants", frozenset())
    if p1 and p2:
        overlap = len(p1 & p2)
        if overlap >= 2:
            score += 10
        elif overlap == 1:
            score += 5

    return score


# ═══════════════════════════════════════════════════════════
# Event-Centric Clustering V4.2.1
# ═══════════════════════════════════════════════════════════

EVENT_THRESHOLD = 50
MERGE_THRESHOLD = 75


def _parse_date(date_str) -> datetime | None:
    from email.utils import parsedate_to_datetime
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return parsedate_to_datetime(date_str.strip())
    except Exception:
        return None


def aggregate_events(articles: list[dict], window_hours: int = 24) -> list[dict]:
    if not articles:
        return []

    # 初始化实体类型
    global _known_entity_types
    _known_entity_types = {}
    for a in articles:
        e = a.get("entities", {}) or {}
        for cat in ("companies", "persons", "countries"):
            for name in e.get(cat, []):
                _known_entity_types[_canonicalize(name)] = _infer_entity_type(name, e)

    global_idf, topic_idf_map = _compute_entity_idf(articles)

    # 按时间升序
    parsed = []
    for a in articles:
        ts = _parse_date(a.get("published_at"))
        fp = build_fingerprint(a, global_idf=global_idf, topic_idf_map=topic_idf_map)
        parsed.append((a, ts, fp))
    parsed.sort(key=lambda x: (x[1] is None, x[1] or datetime.min))

    # Phase 1: Article → Event
    events = []
    for a, ts, fp in parsed:
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
            best_event["all_entities"].update(_canonicalize(n) for n in e.get("companies", []))
            best_event["all_entities"].update(_canonicalize(n) for n in e.get("persons", []))
            best_event["all_entities"].update(_canonicalize(n) for n in e.get("countries", []))
            best_event["max_score"] = max(best_event.get("max_score", 0), a.get("score_total", 0))
            best_event["actions"].add(fp["action"])
            best_event["topics"].add(fp["primary_topic"])
            if len(a.get("title", "")) > len(best_event.get("best_title", "")):
                best_event["best_title"] = a["title"]
        else:
            e = a.get("entities", {}) or {}
            all_ents = set()
            all_ents.update(_canonicalize(n) for n in e.get("companies", []))
            all_ents.update(_canonicalize(n) for n in e.get("persons", []))
            all_ents.update(_canonicalize(n) for n in e.get("countries", []))
            events.append({
                "fingerprint": fp,
                "article_ids": [a["id"]],
                "start_time": ts, "last_time": ts,
                "all_entities": all_ents,
                "max_score": a.get("score_total", 0),
                "actions": {fp["action"]},
                "topics": {fp["primary_topic"]},
                "best_title": a.get("title", ""),
            })

    # Phase 2: Event → Event 合并
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
            ev_i, ev_j = events[i], events[j]
            if ev_i["last_time"] and ev_j["start_time"]:
                if abs(ev_i["last_time"] - ev_j["start_time"]) > timedelta(hours=window_hours):
                    continue
            if fingerprint_score(ev_i["fingerprint"], ev_j["fingerprint"]) >= MERGE_THRESHOLD:
                union(i, j)

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

    # Phase 3: Output
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

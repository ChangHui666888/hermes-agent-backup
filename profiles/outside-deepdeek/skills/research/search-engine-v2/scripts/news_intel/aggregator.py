"""
news_intel/aggregator.py — L8 事件聚合器 v4.3

P0/P1 fixes:
  - _detect_action 计数排序 (非首次命中)
  - ENTITY_CANONICAL 去重 Tehran
  - DIES 正则补全词形
  - Subject hub dampening + MIN_SUBJECT_WEIGHT
P2 fixes:
  - fingerprint_score 按稀有度加权
  - impact_level 一致性校验
"""
import re, json, logging, math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from itertools import combinations

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Entity Alias Dictionary (P0: Tehran 只保留国家级映射)
# ═══════════════════════════════════════════════════════════

ENTITY_CANONICAL = {
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
    "White House": "United States Government", "Washington": "United States Government",
    "Kremlin": "Russian Federation Government", "Moscow": "Russian Federation Government",
    "Beijing": "Chinese Government",
    "Pyongyang": "North Korean Government",
    "Pentagon": "United States Department of Defense",
    "Centcom": "United States Central Command",
    "IRGC": "Islamic Revolutionary Guard Corps",
    "IDF": "Israel Defense Forces",
    "Federal Reserve": "Federal Reserve", "Fed Chair": "Federal Reserve",
    "ECB": "European Central Bank", "BOE": "Bank of England", "BoE": "Bank of England",
    "IMF": "International Monetary Fund", "World Bank": "World Bank",
    "OPEC": "OPEC", "WHO": "World Health Organization", "WTO": "World Trade Organization",
}

ENTITY_TYPE_WEIGHT = {
    "Country": 1.0, "Government": 1.0, "Military": 1.0,
    "Organization": 0.8, "Company": 0.8,
    "Person": 0.5, "Location": 0.4, "Other": 0.2,
}

MIN_SUBJECT_WEIGHT = 0.15
HUB_RATIO = 0.15

_known_entity_types = {}


def _canonicalize(name: str) -> str:
    return ENTITY_CANONICAL.get(name, name)


def _infer_entity_type(name: str, raw_entities: dict) -> str:
    for cat, etype in [("countries", "Country"), ("companies", "Company"), ("persons", "Person")]:
        if name in (raw_entities or {}).get(cat, []):
            return etype
    canonical = _canonicalize(name)
    if any(kw in canonical for kw in ["Government", "Department", "Ministry", "Administration"]):
        return "Government"
    if any(kw in canonical for kw in ["Defense", "Military", "Army", "Navy", "Guard", "Forces"]):
        return "Military"
    return "Other"


# ═══════════════════════════════════════════════════════════
# Action Map (P1: DIES 正则补全词形)
# ═══════════════════════════════════════════════════════════

ACTION_MAP = {
    "SUES":        ("Legal",      [r"\b(sues?|suing|lawsuit|litigation|files?\s+(a\s+)?lawsuit|complaint|indictment|trade\s+secret)\b"]),
    "ACCUSES":     ("Legal",      [r"\b(alleges?|accuses?|charges?)\b"]),
    "ATTACKS":     ("Military",   [r"\b(attacks?|strikes?|bomb(?:s|ed|ing)|missile|drone\s+strike|airstrike|assault|offensive)\b"]),
    "CEASEFIRE":   ("Diplomacy",  [r"\b(ceasefire|truce)\b"]),
    "PEACE_DEAL":  ("Diplomacy",  [r"\b(peace\s+deal|peace\s+agreement|peace\s+treaty)\b"]),
    "NEGOTIATES":  ("Diplomacy",  [r"\b(talks?|negotiat(?:es?|ion)|diploma(?:cy|tic))\b"]),
    "SANCTIONS":   ("Economic",   [r"\b(sanctions?|embargo|blacklist)\b"]),
    "TARIFFS":     ("Economic",   [r"\b(tariffs?|trade\s+war|import\s+duty)\b"]),
    "RATE_CUT":    ("Finance",    [r"\b(cuts?\s+(interest\s+)?rates?|lowers?\s+(interest\s+)?rates?|rate\s+cut)\b"]),
    "RATE_HIKE":   ("Finance",    [r"\b(raises?\s+(interest\s+)?rates?|hikes?\s+(interest\s+)?rates?|rate\s+hike)\b"]),
    "ANNOUNCES":   ("Politics",   [r"\b(announces?|declares?|reveals?|unveils?|launches?|releases?|presents?)\b"]),
    "ELECTS":      ("Politics",   [r"\b(elect(?:s|ed|ion)|votes?|voting|ballot|campaign|candidate)\b"]),
    "DIES":        ("Leadership", [r"\b(dies?|dead|killed?|kills?|killing|deaths?|assassinat(?:ed?|es?|ion)|funerals?|burial|mourns?|mourning)\b"]),
    "CRASHES":     ("Finance",    [r"\b(crash(?:es|ed)?|plunge(?:s|d)?|plummets?|tumbles?|slides?|sell.?off)\b"]),
    "SURGES":      ("Finance",    [r"\b(surges?|soars?|jumps?|rall(?:y|ies|ied)|climbs?|rises?|record\s+high)\b"]),
    "CUTS":        ("Economic",   [r"\b(cuts?|reduces?|slashes?|lowers?|drops?)\b"]),
    "REPORTS":     ("Finance",    [r"\b(reports?|earnings|revenue|profit|quarterly|fiscal)\b"]),
    "DEVELOPS":    ("Technology", [r"\b(develops?|builds?|creates?|manufactures?)\b"]),
    "BANS":        ("Legal",      [r"\b(bans?|prohibits?|outlaws?|restricts?|blocks?)\b"]),
    "FUNDS":       ("Economic",   [r"\b(funds?|funding|invests?|investment|financ(?:es?|ing)|grant)\b"]),
    "WARNS":       ("Politics",   [r"\b(warns?|cautions?|alerts?|advises?|threatens?\s+to)\b"]),
}


def _detect_action(text: str) -> tuple[str, str]:
    """
    P0: 计数排序，非首次命中
    所有匹配到的 action 按命中次数排序，选最多命中的
    """
    text_lower = text.lower()
    scores = {}
    for action, (etype, patterns) in ACTION_MAP.items():
        hits = 0
        for pat in patterns:
            hits += len(re.findall(pat, text_lower))
        if hits > 0:
            scores[action] = hits
    if not scores:
        return ("OTHER", "General")
    best = max(scores, key=scores.get)
    return (best, ACTION_MAP[best][0])


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
    "Turkey","Saudi Arabia","UAE","Switzerland","Sweden","Norway","Netherlands",
    "Poland","Argentina","Egypt","Nigeria","South Africa","Kenya","Indonesia",
    "Philippines","Thailand","Singapore","Pakistan","Iraq","Syria","Lebanon",
]


def _extract_participants(entities: dict, text: str) -> set:
    participants = set()
    e = entities or {}
    for c in e.get("countries", []):
        participants.add(_canonicalize(c))
    for c in COUNTRIES:
        if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
            participants.add(_canonicalize(c))
    return participants


# ═══════════════════════════════════════════════════════════
# Entity IDF
# ═══════════════════════════════════════════════════════════

def _compute_entity_idf(articles: list[dict]) -> tuple[dict, dict, set]:
    N = len(articles)
    if N == 0:
        return {}, {}, set()
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

    hub_entities = {name for name, freq in global_counter.items()
                    if freq / N > HUB_RATIO and freq >= 5}

    return global_idf, topic_idf, hub_entities


def _entity_weight(name: str, global_idf: dict, topic_idf_map: dict, primary_topic: str) -> float:
    canonical = _canonicalize(name)
    etype = _known_entity_types.get(canonical, "Other")
    type_w = ENTITY_TYPE_WEIGHT.get(etype, 0.2)
    g_idf = min(global_idf.get(canonical, 1.0), 2.0) / 2.0
    t_idf_map = topic_idf_map.get(primary_topic, {})
    t_idf = min(t_idf_map.get(canonical, 1.0), 2.0) / 2.0
    return type_w * (0.2 + 0.4 * g_idf + 0.4 * t_idf)


# ═══════════════════════════════════════════════════════════
# EventFingerprint
# ═══════════════════════════════════════════════════════════

def _get_text(a: dict) -> str:
    desc = a.get("description") or a.get("summary_cn") or a.get("summary") or ""
    if desc and not desc.startswith("<table") and not desc.startswith("<tr"):
        if (desc.count("<") + desc.count(">")) / max(len(desc), 1) < 0.3:
            desc = desc[:500]
        else:
            desc = ""
    return desc + " " + (a.get("title") or "")


def build_fingerprint(article: dict, global_idf: dict = None, topic_idf_map: dict = None,
                      hub_entities: set = None) -> dict:
    global_idf = global_idf or {}
    topic_idf_map = topic_idf_map or {}
    hub_entities = hub_entities or set()
    text = _get_text(article)
    action, event_type = _detect_action(text)
    primary, secondary = _classify_topics(text)

    entities = article.get("entities", {}) or {}

    # P1: Subject — hub entities 降权但不禁用
    candidates = []
    for name in entities.get("companies", []) + entities.get("persons", []):
        canonical = _canonicalize(name)
        w = _entity_weight(name, global_idf, topic_idf_map, primary)
        if canonical in hub_entities:
            w *= 0.3  # hub实体降权70%，但不排除
        candidates.append((canonical, w))
    candidates.sort(key=lambda x: x[1], reverse=True)
    if candidates and candidates[0][1] >= MIN_SUBJECT_WEIGHT:
        subject = candidates[0][0]
        subject_weight = candidates[0][1]
    else:
        subject = ""
        subject_weight = 0.0

    # Object
    obj_candidates = []
    for name in entities.get("countries", []) + entities.get("companies", []):
        canonical = _canonicalize(name)
        if canonical == subject:
            continue
        w = _entity_weight(name, global_idf, topic_idf_map, primary)
        if canonical in hub_entities:
            w *= 0.3
        obj_candidates.append((canonical, w))
    obj_candidates.sort(key=lambda x: x[1], reverse=True)
    if obj_candidates:
        obj = obj_candidates[0][0]
        object_weight = obj_candidates[0][1]
    else:
        obj = ""
        object_weight = 0.0

    countries = entities.get("countries", [])
    country = _canonicalize(countries[0]) if countries else None

    participants = _extract_participants(entities, text)

    anchor = f"{subject}|{action}|{obj}|{primary}" if subject and action != "OTHER" else ""

    return {
        "subject": subject, "subject_weight": subject_weight,
        "action": action, "object": obj, "object_weight": object_weight,
        "event_type": event_type, "primary_topic": primary, "secondary_topic": secondary,
        "country": country, "participants": frozenset(participants), "anchor": anchor,
    }


def fingerprint_score(fp1: dict, fp2: dict) -> int:
    """
    V4.3: Location 硬约束 + 按稀有度加权
    """
    if fp1.get("country") and fp2.get("country") and fp1["country"] != fp2["country"]:
        return 0

    if fp1.get("anchor") and fp2.get("anchor") and fp1["anchor"] == fp2["anchor"]:
        return 100

    score = 0

    # Action (25)
    if fp1["action"] == fp2["action"] and fp1["action"] != "OTHER":
        score += 25

    # Subject (P2: 加权 10~25)
    if fp1["subject"] and fp2["subject"]:
        if fp1["subject"] == fp2["subject"] or fp1["subject"] in fp2["subject"] or fp2["subject"] in fp1["subject"]:
            rarity = min(fp1.get("subject_weight", 0), fp2.get("subject_weight", 0))
            score += 10 + int(15 * min(rarity / 0.4, 1.0))

    # Object (P2: 加权 10~30)
    if fp1["object"] and fp2["object"]:
        if fp1["object"] == fp2["object"] or fp1["object"] in fp2["object"] or fp2["object"] in fp1["object"]:
            rarity = min(fp1.get("object_weight", 0), fp2.get("object_weight", 0))
            score += 10 + int(20 * min(rarity / 0.4, 1.0))

    # Topic (10)
    if fp1["primary_topic"] == fp2["primary_topic"]:
        score += 10
    elif fp1["secondary_topic"] and fp2["secondary_topic"] and fp1["secondary_topic"] == fp2["secondary_topic"]:
        score += 5

    # Event Type (10)
    if fp1["event_type"] == fp2["event_type"]:
        score += 10

    # Participants bonus
    p1 = fp1.get("participants", frozenset())
    p2 = fp2.get("participants", frozenset())
    if p1 and p2:
        overlap = len(p1 & p2)
        if overlap >= 2: score += 10
        elif overlap == 1: score += 5

    return score


# ═══════════════════════════════════════════════════════════
# Event-Centric Clustering V4.3
# ═══════════════════════════════════════════════════════════

EVENT_THRESHOLD = 50
MERGE_THRESHOLD = 75


def _extract_action_detail(text: str, action: str) -> str | None:
    """从文本中提取动作细节（动作词后紧跟的描述）"""
    if action == "OTHER" or not text:
        return None
    patterns = ACTION_MAP.get(action, ("", []))[1]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            # 取匹配词后紧跟的 80 字符作为 detail
            end = m.end()
            detail = text[end:end+80].strip(" ,.;:\"'").strip()
            return detail[:50] if detail else None
    return None


def _infer_actor_roles(entity_refs: list, action: str, obj: str) -> list:
    """根据动作类型推断实体角色"""
    roles = []
    for i, ent in enumerate(entity_refs[:5]):
        role = "Initiator" if i == 0 else ("Target" if ent["name"] == obj else "Participant")
        roles.append({"entity": ent["name"], "type": ent["type"], "role": role})
    return roles


def _parse_date(date_str) -> datetime | None:
    from email.utils import parsedate_to_datetime
    if not date_str: return None
    try: return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except: pass
    try: return parsedate_to_datetime(date_str.strip())
    except: return None


def aggregate_events(articles: list[dict], window_hours: int = 24) -> list[dict]:
    if not articles:
        return []

    global _known_entity_types
    _known_entity_types = {}
    for a in articles:
        e = a.get("entities", {}) or {}
        for cat in ("companies", "persons", "countries"):
            for name in e.get(cat, []):
                _known_entity_types[_canonicalize(name)] = _infer_entity_type(name, e)

    global_idf, topic_idf_map, hub_entities = _compute_entity_idf(articles)

    # 按时间升序 + 预计算指纹
    parsed = []
    for a in articles:
        ts = _parse_date(a.get("published_at"))
        fp = build_fingerprint(a, global_idf=global_idf, topic_idf_map=topic_idf_map, hub_entities=hub_entities)
        parsed.append((a, ts, fp))
    parsed.sort(key=lambda x: (x[1] is None, x[1] or datetime.min))

    # Phase 1: Article → Event
    events = []
    for a, ts, fp in parsed:
        best_score, best_event = 0, None
        for ev in events:
            if ev["last_time"] and ts and abs(ts - ev["last_time"]) > timedelta(hours=window_hours):
                continue
            score = fingerprint_score(fp, ev["fingerprint"])
            if score > best_score and score >= EVENT_THRESHOLD:
                best_score, best_event = score, ev

        if best_event:
            best_event["article_ids"].append(a["id"])
            best_event["fingerprints"].append(fp)
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
                "fingerprint": fp, "fingerprints": [fp],
                "article_ids": [a["id"]], "start_time": ts, "last_time": ts,
                "all_entities": all_ents, "max_score": a.get("score_total", 0),
                "actions": {fp["action"]}, "topics": {fp["primary_topic"]},
                "best_title": a.get("title", ""),
            })

    # Phase 2: Event → Event 合并
    n = len(events)
    parent = list(range(n))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        px, py = find(x), find(y)
        if px != py: parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            ev_i, ev_j = events[i], events[j]
            if ev_i["last_time"] and ev_j["start_time"]:
                if abs(ev_i["last_time"] - ev_j["start_time"]) > timedelta(hours=window_hours):
                    continue
            if fingerprint_score(ev_i["fingerprint"], ev_j["fingerprint"]) >= MERGE_THRESHOLD:
                union(i, j)

    merged, done = [], set()
    for i in range(n):
        root = find(i)
        if root in done: continue
        done.add(root)
        group = [j for j in range(n) if find(j) == root]
        if len(group) == 1:
            merged.append(events[group[0]])
        else:
            m = events[group[0]]
            for j in group[1:]:
                ej = events[j]
                m["article_ids"].extend(ej["article_ids"])
                m["fingerprints"].extend(ej["fingerprints"])
                m["start_time"] = min(m["start_time"] or ej["start_time"], ej["start_time"] or m["start_time"])
                m["last_time"] = max(m["last_time"] or ej["last_time"], ej["last_time"] or m["last_time"])
                m["all_entities"].update(ej["all_entities"])
                m["max_score"] = max(m["max_score"], ej["max_score"])
                m["actions"].update(ej["actions"]); m["topics"].update(ej["topics"])
                if len(ej.get("best_title", "")) > len(m.get("best_title", "")):
                    m["best_title"] = ej["best_title"]
            merged.append(m)

    # Phase 3: Output
    result = []
    for idx, ev in enumerate(merged):
        if len(ev["article_ids"]) < 2: continue

        # 成员数据
        members = [a for a, _, _ in parsed if a["id"] in ev["article_ids"]]
        fps = ev.get("fingerprints", [ev["fingerprint"]])

        # ── Coherence ──
        coherence = 0
        if len(fps) >= 2:
            scores = [fingerprint_score(fps[i], fps[j]) for i, j in combinations(range(len(fps)), 2)]
            coherence = sum(scores) / len(scores) if scores else 0

        # ── Impact ──
        impact = "HIGH" if ev["max_score"] >= 85 else ("MEDIUM" if ev["max_score"] >= 60 else "LOW")
        if coherence < MERGE_THRESHOLD and impact == "HIGH":
            impact = "MEDIUM"

        # ── Entity ID 映射 ──
        entity_refs = []
        for name in ev["all_entities"]:
            etype = _known_entity_types.get(name, "Other")
            entity_refs.append({"name": name, "type": etype})

        # ── Source ──
        source_names = list(set(a.get("source_name", "") for a in members if a.get("source_name")))
        try:
            from news_intel.scorer import score_source
            source_scores_list = [score_source(s) for s in source_names]
        except ImportError:
            source_scores_list = [5] * len(source_names)
        max_auth = max(source_scores_list) if source_scores_list else 5
        primary_src = source_names[0] if source_names else ""

        # ── Confidence ──
        src_auth_norm = min(max_auth / 20.0, 1.0)
        coh_norm = min(coherence / 100.0, 1.0)
        diversity = min(len(source_names) / 5.0, 1.0)
        count_factor = min(len(members) / 10.0, 1.0)
        confidence = round(0.4 * src_auth_norm + 0.3 * coh_norm + 0.2 * diversity + 0.1 * count_factor, 2)

        # ── Stage ──
        now = datetime.utcnow()
        if ev["start_time"]:
            age_hours = (now - ev["start_time"]).total_seconds() / 3600
            if age_hours <= 2: stage = "breaking"
            elif age_hours <= 24: stage = "developing"
            elif age_hours <= 168: stage = "active"
            elif age_hours <= 720: stage = "stable"
            else: stage = "closed"
        else:
            stage = "developing"

        # ── Event ID ──
        ts = ev["start_time"] or datetime.utcnow()
        event_id = f"EVT-{ts.strftime('%Y%m%d')}-{idx+1:03d}"

        # ── Summary ──
        raw_summaries = []
        for a in members[:3]:
            s = a.get("summary_cn") or a.get("description", "") or ""
            if not s.startswith("<table") and not s.startswith("<tr"):
                if (s.count("<") + s.count(">")) / max(len(s), 1) < 0.3:
                    raw_summaries.append(s[:100])
        summary = " | ".join(s for s in raw_summaries if s)

        # ── First Source ──
        timed_members = [(a, _parse_date(a.get("published_at"))) for a in members]
        timed_members = [(a, t) for a, t in timed_members if t is not None]
        first_article = min(timed_members, key=lambda x: x[1])[0] if timed_members else (members[0] if members else None)
        first_source = first_article.get("source_name", "") if first_article else ""

        # ── Action detail ──
        fp_centroid = ev["fingerprint"]
        action_detail = _extract_action_detail(
            " ".join(a.get("title", "") + " " + (a.get("description") or "")[:200] for a in members[:2]),
            fp_centroid["action"]
        )

        result.append({
            "event_id": event_id,
            "subject": {"name": fp_centroid["subject"], "type": _known_entity_types.get(fp_centroid["subject"], "Other")},
            "action": {"type": fp_centroid["action"], "detail": action_detail},
            "object": {"name": fp_centroid["object"], "type": _known_entity_types.get(fp_centroid["object"], "Other")},
            "event_type": fp_centroid["event_type"],
            "event_time": ev["start_time"].isoformat() if ev["start_time"] else None,
            "location": {"country": fp_centroid.get("country"), "region": None},
            "source": {"primary_source": first_source or primary_src, "authority": max_auth,
                       "source_count": len(source_names), "sources": source_names[:10]},
            "doc_refs": [{"url": a.get("url", ""), "title": a.get("title", "")} for a in members[:5]],
            "actors": _infer_actor_roles(entity_refs, fp_centroid["action"], fp_centroid.get("object", "")),
            "title": ev["best_title"], "summary": summary or ev["best_title"],
            "keywords": list(ev.get("topics", set())),
            "confidence": confidence, "coherence": round(coherence, 1),
            "extraction_method": "v4.3-saeo",
            "related_entities": [{"name": e["name"], "type": e["type"]} for e in entity_refs[:20]],
            "article_count": len(ev["article_ids"]), "article_ids": ev["article_ids"], "stage": stage,
            "first_seen": ev["start_time"].isoformat() if ev["start_time"] else None,
            "last_updated": ev["last_time"].isoformat() if ev["last_time"] else None,
        })

    result.sort(key=lambda e: e["article_count"], reverse=True)
    return result

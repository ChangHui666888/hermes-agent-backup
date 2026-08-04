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
import re, json, logging, math, os
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
    "Saudi Arabia": "Saudi Arabia", "UAE": "United Arab Emirates",
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

    # ── 人物别名（中英映射，统一为英文规范名） ──
    "Donald Trump": "Trump", "特朗普": "Trump", "川普": "Trump", "President Trump": "Trump",
    "Vladimir Putin": "Putin", "普京": "Putin", "President Putin": "Putin",
    "Elon Musk": "Musk", "马斯克": "Musk",
    "J.D. Vance": "J.D. Vance", "万斯": "J.D. Vance",
    "Kevin Warsh": "Kevin Warsh", "凯文·沃什": "Kevin Warsh", "凯文沃什": "Kevin Warsh", "凯文沃舎": "Kevin Warsh", "沃什": "Kevin Warsh", "沃舎": "Kevin Warsh",
    "Fed Chair": "Federal Reserve", "Powell": "Federal Reserve", "鲍威尔": "Federal Reserve",
    "Volodymyr Zelensky": "Zelensky", "泽连斯基": "Zelensky", "Zelenskyy": "Zelensky",
    "Benjamin Netanyahu": "Netanyahu", "内塔尼亚胡": "Netanyahu",
    "Narendra Modi": "Modi", "莫迪": "Modi",
    "Jensen Huang": "Jensen Huang", "黄仁勋": "Jensen Huang",
    "Sam Altman": "Sam Altman", "奥特曼": "Sam Altman",
    "Tim Cook": "Tim Cook", "库克": "Tim Cook",
    "Mark Zuckerberg": "Mark Zuckerberg", "扎克伯格": "Mark Zuckerberg",
    "Jeff Bezos": "Jeff Bezos", "贝索斯": "Jeff Bezos",
    "Emmanuel Macron": "Macron", "马克龙": "Macron",
    "Olaf Scholz": "Scholz", "朔尔茨": "Scholz",
    "Keir Starmer": "Starmer", "斯塔默": "Starmer",
    "Xi Jinping": "Xi", "习近平": "Xi", "李强": "Li Qiang",
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
    """统一实体规范化 (Phase A): 优先 canonicalizer.resolve_entity (单一来源, entity_weights.json),
    回退 ENTITY_CANONICAL 兼容旧别名。"""
    try:
        from news_intel.canonicalizer import resolve_entity
        ent = resolve_entity(name)
        if ent.get("name"):
            return ent["name"]
    except Exception:
        pass
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
        if isinstance(e, str):
            try: e = json.loads(e)
            except: e = {}
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
    """统一文本输入 (Phase A 输入一致性): title + description(英文摘要) + content(正文)。

    旧指纹与 Fact 指纹必须消费同一文本, 否则 subject/action 比对失真。
    - description 优先 (可靠英文 RSS 摘要); summary_cn 在本地库退化(~18字符), 仅兜底
    - content/content_md = 正文 (深度信号)
    - 统一 HTML 过滤 + 截断
    """
    parts = []
    for key in ("description", "summary", "summary_cn"):
        s = (a.get(key) or "").strip()
        if not s or s.startswith("<table") or s.startswith("<tr"):
            continue
        if (s.count("<") + s.count(">")) / max(len(s), 1) < 0.3:
            parts.append(s[:500])
    content = (a.get("content") or a.get("content_md") or "").strip()
    if content and not content.startswith("<table"):
        if (content.count("<") + content.count(">")) / max(len(content), 1) < 0.3:
            parts.append(content[:800])
    parts.append(a.get("title") or "")
    return " ".join(p for p in parts if p).strip()


# GLiNER label → 聚合器 entities dict 分组 (Phase A: 与 Fact 指纹共享 NER 源)
_GLINER_PERSON = ("person",)
_GLINER_COMPANY = ("organization", "company",)
_GLINER_COUNTRY = ("country", "city",)


def _gliner_to_entities(ner_list: list) -> dict:
    """GLiNER 实体列表 → {persons, companies, countries}, 供 build_fingerprint 使用。"""
    from news_intel.canonicalizer import is_media_source
    out = {"persons": [], "companies": [], "countries": []}
    for ent in ner_list or []:
        label = (ent.get("label") or "").lower()
        text = (ent.get("text") or "").strip()
        if not text or is_media_source(text):
            continue  # 排除新闻来源名 (媒体自我指涉, 非事件主体)
        if label in _GLINER_PERSON:
            out["persons"].append(text)
        elif label in _GLINER_COMPANY:
            out["companies"].append(text)
        elif label in _GLINER_COUNTRY:
            out["countries"].append(text)
    return out


def build_fingerprint(article: dict, global_idf: dict = None, topic_idf_map: dict = None,
                      hub_entities: set = None, ner_entities: list = None) -> dict:
    """legacy 指纹。ner_entities (GLiNER) 提供时优先 → 与 Fact 指纹共享 NER 源 (输入一致性)。"""
    global_idf = global_idf or {}
    topic_idf_map = topic_idf_map or {}
    hub_entities = hub_entities or set()
    text = _get_text(article)
    action, event_type = _detect_action(text)
    primary, secondary = _classify_topics(text)

    entities = article.get("entities", {}) or {}
    if isinstance(entities, str):
        try: entities = json.loads(entities)
        except: entities = {}
    if ner_entities:
        entities = _gliner_to_entities(ner_entities)

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
    V4.3: Location 硬约束 + 主题硬约束 + 按稀有度加权
    优化: 主题不同直接拒绝合并（防 Fed+Iran 跨主题错配）
    """
    if fp1.get("country") and fp2.get("country") and fp1["country"] != fp2["country"]:
        return 0

    # 主题硬约束: 主主题必须一致（Finance 不会并入 Military）
    if fp1.get("primary_topic") and fp2.get("primary_topic"):
        if fp1["primary_topic"] != fp2["primary_topic"]:
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

# 从配置中心读取阈值（兼容配置中心，缺失回退默认值）
try:
    from config.loader import load_config, get_setting as _agg_get
    _AGG_CFG = load_config()
except Exception:
    _AGG_CFG = {}

def _agg_cfg(key, default):
    return _agg_get(_AGG_CFG, key, default) if _AGG_CFG else default

EVENT_THRESHOLD = _agg_cfg("aggregate.event_threshold", 60)
MERGE_THRESHOLD = _agg_cfg("aggregate.merge_threshold", 75)
AGG_WINDOW_HOURS = _agg_cfg("aggregate.window_hours", 24)


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


def _article_ts(a: dict) -> datetime:
    """文章时间回退链: published_at → fetched_at → 聚合时刻 (naive UTC)。

    防止文章缺日期导致事件 first_seen/last_updated 与 timeline/source_chain 缺失。
    """
    return (
        _parse_date(a.get("published_at"))
        or _parse_date(a.get("fetched_at"))
        or datetime.utcnow()
    )


# ── 规则版 llm_analysis (零成本) ─────────────────────────────
# 事件级 AI 面板基线。DeepSeek 深度分析留待未来对 Top 事件调用。
_RISK_BY_TYPE = {
    "Military": "HIGH", "Crisis": "HIGH", "Disaster": "HIGH",
    "Political": "MEDIUM", "Diplomacy": "MEDIUM", "Economic": "MEDIUM",
    "Finance": "MEDIUM", "Legal": "MEDIUM", "Technology": "LOW",
    "Leadership": "MEDIUM",
}
_MARKET_BY_TYPE = {
    "Military": "Energy, shipping and defence-linked assets; safe-haven flows",
    "Diplomacy": "Cross-border trade and FX sensitivity",
    "Economic": "Equities, rates and currency markets",
    "Finance": "Credit spreads, bank and fintech equities",
    "Legal": "Affected issuers' equities and regulatory news flow",
    "Technology": "Tech and semiconductor sector sentiment",
    "Crisis": "Broad risk-off; safe havens",
}


def _rule_llm_analysis(ev: dict, max_score: int) -> dict:
    """生成事件级 llm_analysis（规则版，零 LLM 成本，保证 AI 面板非空）。"""
    etype = str(ev.get("event_type") or "").capitalize()
    stage = ev.get("stage", "developing")
    confidence = ev.get("confidence", 0.0)
    risk = _RISK_BY_TYPE.get(etype, "MEDIUM")
    if max_score >= 85 or stage == "breaking":
        risk = "HIGH"
    elif max_score >= 70 and risk == "LOW":
        risk = "MEDIUM"
    significance = (
        "Critical" if max_score >= 85 else
        "Major" if max_score >= 70 else
        "Moderate" if max_score >= 60 else "Minor"
    )
    market = _MARKET_BY_TYPE.get(etype, "Broader cross-asset sentiment")
    summary = ev.get("summary") or ev.get("title", "")
    return {
        "event_summary": (summary[:500] if summary else ev.get("title", "")),
        "risk_level": risk,
        "market_effect": market,
        "confidence": round(float(confidence), 2),
        "significance": significance,
        "forecast": None,
    }


def build_fact_fingerprint(fact: dict) -> dict:
    """从规范化 fact 构建指纹 (Adapter: 有 fact 用 fact, 无则 legacy build_fingerprint)。

    输入 fact_pipeline 产出的 fact payload:
      {action_type, action_event_type, location, entities:[{entity_name, role}]}
    提取 subject/object(按 role=SUBJECT/OBJECT) + action + event_type + country。
    """
    ents = fact.get("entities") or []
    subj = next((e.get("entity_name", "") for e in ents if e.get("role") == "SUBJECT"), "")
    obj = next((e.get("entity_name", "") for e in ents if e.get("role") == "OBJECT"), "")
    action = fact.get("action_type") or ""
    etype = fact.get("action_event_type") or ""
    country = fact.get("location") or ""
    return {
        "subject": subj, "action": action, "object": obj,
        "event_type": etype, "primary_topic": etype, "secondary_topic": "",
        "country": country,
        "participants": frozenset(n for n in (subj, obj) if n),
        "anchor": subj,
        "subject_weight": 1.0, "object_weight": 1.0,
    }


def build_fused_fingerprint(article: dict, fact: dict = None, global_idf: dict = None,
                            topic_idf_map: dict = None, hub_entities: set = None,
                            ner_entities: list = None) -> dict:
    """指纹级融合 (Phase A 定案, 方案 A): 每字段取最优源。

    fact 提供落地 subject/object 与规范 action; legacy 兜底 country/topic(12类词表)。
    原则:
      - subject/object ← fact (落地优先; 实测基线 subject 空)
      - action ← fact(非 OTHER) 否则 legacy (修复 fact 快路径 OTHER→过度切分, 主因)
      - event_type ← fact(action_event_type) 否则 legacy
      - country ← legacy 优先, fact location 兜底 (恢复国家硬约束)
      - primary_topic ← legacy 固定 (保持 12 类主题词表, 防主题硬约束失效)
      - participants ← 并集
    输入一致性: ner_entities (GLiNER) 传给 legacy 部分 → 与 Fact 同一 NER 源/同一文本。
    """
    fp = build_fingerprint(article, global_idf=global_idf, topic_idf_map=topic_idf_map,
                           hub_entities=hub_entities, ner_entities=ner_entities)
    if not fact:
        return fp

    ents = fact.get("entities") or []
    f_subj = next((e.get("entity_name", "") for e in ents if e.get("role") == "SUBJECT"), "")
    f_obj = next((e.get("entity_name", "") for e in ents if e.get("role") == "OBJECT"), "")
    f_action = fact.get("action_type") or ""
    f_etype = fact.get("action_event_type") or ""
    f_loc = fact.get("location") or ""

    # subject/object ← fact (落地优先)
    if f_subj:
        fp["subject"], fp["subject_weight"] = f_subj, 1.0
    if f_obj:
        fp["object"], fp["object_weight"] = f_obj, 1.0

    # action ← fact(非 OTHER) 否则 legacy
    if f_action and f_action != "OTHER":
        fp["action"] = f_action
    if f_etype:
        fp["event_type"] = f_etype

    # country ← legacy 优先 (恢复硬约束), fact location 兜底
    if not fp.get("country") and f_loc:
        fp["country"] = f_loc

    # participants ← 并集
    f_parts = frozenset(n for n in (f_subj, f_obj) if n)
    if f_parts:
        fp["participants"] = (fp.get("participants") or frozenset()) | f_parts

    # anchor 重算 (OTHER 动作不锚定, 与 legacy 语义一致)
    subj, action, obj, primary = fp["subject"], fp["action"], fp["object"], fp["primary_topic"]
    fp["anchor"] = f"{subj}|{action}|{obj}|{primary}" if subj and action != "OTHER" else ""

    return fp


def aggregate_events(articles: list[dict], window_hours: int = 24, facts_by_article: dict = None,
                     fp_mode: str = "fused", ner_by_article: dict = None) -> list[dict]:
    """事件聚合。

    facts_by_article: {article_id: [fact_payload, ...]} — 有 fact 的文章用 fact 参与指纹。
    ner_by_article: {article_id: [GLiNER 实体, ...]} — 输入一致性: 传给 legacy 指纹,
      使 legacy 与 Fact 共享同一 NER 源/同一文本 (测试/生产均可注入)。
    fp_mode:
      - "fused" (默认/生产): 指纹级融合 — fact 落地 subject/object, legacy 兜底 action/country/topic
      - "fact": 纯 fact 指纹 (对比测试用)
      - "legacy": 完全忽略 fact, 旧指纹 (对比测试用)
    """
    if not articles:
        return []
    facts_by_article = facts_by_article or {}
    ner_by_article = ner_by_article or {}

    global _known_entity_types
    _known_entity_types = {}
    for a in articles:
        e = a.get("entities", {}) or {}
        if isinstance(e, str):
            try: e = json.loads(e)
            except: e = {}
        for cat in ("companies", "persons", "countries"):
            for name in e.get(cat, []):
                _known_entity_types[_canonicalize(name)] = _infer_entity_type(name, e)

    global_idf, topic_idf_map, hub_entities = _compute_entity_idf(articles)

    # 按时间升序 + 预计算指纹
    parsed = []
    for a in articles:
        ts = _article_ts(a)
        facts = facts_by_article.get(a.get("id"))
        ner = ner_by_article.get(a.get("id"))
        if facts and fp_mode != "legacy":
            if fp_mode == "fact":
                fp = build_fact_fingerprint(facts[0])  # 纯 fact 指纹 (对比测试)
            else:  # fused (默认生产)
                fp = build_fused_fingerprint(a, facts[0], global_idf=global_idf,
                                             topic_idf_map=topic_idf_map, hub_entities=hub_entities,
                                             ner_entities=ner)
        else:
            fp = build_fingerprint(a, global_idf=global_idf, topic_idf_map=topic_idf_map,
                                   hub_entities=hub_entities, ner_entities=ner)
        parsed.append((a, ts, fp))
    parsed.sort(key=lambda x: (x[1] is None, x[1] or datetime.min))

    # Phase 1: Article → Event
    events = []
    for a, ts, fp in parsed:
        # 解析实体（统一在循环开头处理）
        e = a.get("entities", {}) or {}
        if isinstance(e, str):
            try: e = json.loads(e)
            except: e = {}
        all_ents = set()
        all_ents.update(_canonicalize(n) for n in e.get("companies", []))
        all_ents.update(_canonicalize(n) for n in e.get("persons", []))
        all_ents.update(_canonicalize(n) for n in e.get("countries", []))

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
            # 修复: 无条件更新（原代码误放在 isinstance(e,str) 内）
            best_event["all_entities"].update(all_ents)
            best_event["max_score"] = max(best_event.get("max_score", 0), a.get("score_total", 0))
            best_event["actions"].add(fp["action"])
            best_event["topics"].add(fp["primary_topic"])
            if len(a.get("title", "")) > len(best_event.get("best_title", "")):
                best_event["best_title"] = a["title"]
        else:
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

        # ── Fingerprint centroid (优化: 用簇质心，多数决定而非种子) ──
        fps = ev.get("fingerprints", [ev["fingerprint"]])
        def _majority(field):
            vals = Counter(fp.get(field, "") for fp in fps)
            if not vals: return ""
            top_val, top_cnt = vals.most_common(1)[0]
            # 必须占多数(>50%)，否则回落种子
            if top_cnt * 2 > len(fps):
                return top_val
            return ev["fingerprint"].get(field, "")
        fp_centroid = {
            "subject": _majority("subject"),
            "object": _majority("object"),
            "action": _majority("action"),
            "event_type": _majority("event_type"),
            "primary_topic": _majority("primary_topic"),
            "secondary_topic": _majority("secondary_topic"),
            "country": _majority("country"),
            "participants": ev["fingerprint"].get("participants", frozenset()),
            "anchor": ev["fingerprint"].get("anchor"),
            "subject_weight": ev["fingerprint"].get("subject_weight", 0),
            "object_weight": ev["fingerprint"].get("object_weight", 0),
        }

        # ── Source authority ──
        source_auth_map = _load_source_scores()
        primary_src = members[0].get("source_name", "") if members else ""
        source_names = list(set(a.get("source_name", "") for a in members if a.get("source_name")))
        max_auth = max((source_auth_map.get(sn, 5) for sn in source_names), default=5)

        # ── Summary + Evidence (优化: HTML 过滤 + summary_cn 回退 + URL 去重) ──
        raw_summaries = []
        evidence_quotes = []
        _ev_urls = set()
        for a in members[:6]:
            s = a.get("summary_cn") or a.get("description", "") or ""
            html_ratio = (s.count("<") + s.count(">")) / max(len(s), 1)
            if not s.startswith("<table") and not s.startswith("<tr") and html_ratio < 0.3 \
               and "submitted by" not in s.lower() and not s.startswith("["):
                raw_summaries.append(s[:100])
            # 证据: description 优先; 空/HTML 时回退 summary_cn
            desc = a.get("description", "") or ""
            desc_html_ratio = (desc.count("<") + desc.count(">")) / max(len(desc), 1) if desc else 1
            if len(desc) >= 30 and not desc.startswith("<") and desc_html_ratio < 0.2 \
               and "submitted by" not in desc.lower() and "&amp;" not in desc:
                quote = desc[:150]
            else:
                s2 = (a.get("summary_cn") or "").strip()
                s2_html = (s2.count("<") + s2.count(">")) / max(len(s2), 1) if s2 else 1
                if len(s2) < 20 or s2_html >= 0.2 or "submitted by" in s2.lower():
                    continue
                quote = s2[:150]
            url = a.get("url", "")
            if url in _ev_urls:
                continue
            _ev_urls.add(url)
            evidence_quotes.append({
                "quote": quote,
                "source": a.get("source_name", ""),
                "url": url,
            })
            if len(evidence_quotes) >= 5:
                break
        summary = " | ".join(s for s in raw_summaries if s)

        # ── Source Chain (new v4.4) ──
        # 时间回退链: 无 published_at 的文章也参与排序，避免 source_chain/timeline 为空
        timed_members = [(a, _article_ts(a)) for a in members]
        sorted_by_time = sorted(timed_members, key=lambda x: x[1])
        first_article = sorted_by_time[0][0] if sorted_by_time else (members[0] if members else None)
        first_source_name = first_article.get("source_name", "") if first_article else ""
        first_source_id = _source_name_to_id(first_source_name)

        source_chain = []
        seen_sources = set()
        for a, t in sorted_by_time:
            sn = a.get("source_name", "")
            if sn in seen_sources:
                continue  # 优化: 同源只保留首次（防重复）
            seen_sources.add(sn)
            source_chain.append({
                "source_id": _source_name_to_id(sn),
                "source_name": sn,
                "time": t.isoformat() if t else None,
                "role": "break" if sn == first_source_name else "follow",
                "url": a.get("url", ""),
            })
            if len(source_chain) >= 10:
                break

        # ── Timeline (new v4.4): 每篇不同文章一个演化节点 (按 URL 去重) ──
        timeline = []
        seen_tl_urls = set()
        for a, t in sorted_by_time[:12]:
            url = a.get("url", "")
            if url in seen_tl_urls:
                continue
            seen_tl_urls.add(url)
            timeline.append({
                "time": t.isoformat() if t else None,
                "update": (a.get("title", "") or "")[:80],
                "source": a.get("source_name", ""),
            })

        # ── Entity IDs (new v4.4) ──
        subject_entity_id = _entity_name_to_id(fp_centroid["subject"]) if fp_centroid["subject"] else None
        object_entity_id = _entity_name_to_id(fp_centroid["object"]) if fp_centroid["object"] else None
        related_with_ids = []
        for e in entity_refs[:20]:
            related_with_ids.append({
                "entity_id": _entity_name_to_id(e["name"]),
                "name": e["name"],
                "type": e["type"],
            })

        # ── Action detail ──
        action_detail = _extract_action_detail(
            " ".join(a.get("title", "") + " " + (a.get("description") or "")[:200] for a in members[:2]),
            fp_centroid["action"]
        )

        event_obj = {
            "event_id": event_id,
            "subject": {"entity_id": subject_entity_id, "name": fp_centroid["subject"],
                        "type": _known_entity_types.get(fp_centroid["subject"], "Other")},
            "action": {"type": fp_centroid["action"], "detail": action_detail},
            "object": {"entity_id": object_entity_id, "name": fp_centroid["object"],
                       "type": _known_entity_types.get(fp_centroid["object"], "Other")},
            "event_type": fp_centroid["event_type"],
            "event_time": ev["start_time"].isoformat() if ev["start_time"] else None,
            "location": {"country": fp_centroid.get("country"), "region": None},
            "source": {
                "primary_source": first_source_name or primary_src,
                "primary_source_id": first_source_id,
                "authority": max_auth,
                "source_count": len(source_names),
                "sources": source_names[:10],
            },
            "doc_refs": [{"url": a.get("url", ""), "title": a.get("title", "")} for a in members[:5]],
            "actors": _infer_actor_roles(entity_refs, fp_centroid["action"], fp_centroid.get("object", "")),
            "title": ev["best_title"],
            "summary": summary or ev["best_title"],
            "keywords": list(ev.get("topics", set())),
            "confidence": confidence,
            "coherence": round(coherence, 1),
            "extraction_method": "v4.4-saeo",
            "related_entities": related_with_ids,
            "article_count": len(ev["article_ids"]),
            "article_ids": ev["article_ids"],
            "stage": stage,
            "first_seen": ev["start_time"].isoformat() if ev["start_time"] else None,
            "last_updated": ev["last_time"].isoformat() if ev["last_time"] else None,
            # ── New v4.4 fields ──
            "evidence": evidence_quotes[:5],
            "source_chain": source_chain,
            "timeline": timeline,
        }

        # 规则版 AI 分析 (零成本, 保证 IntelligencePanel 非空)
        event_obj["llm_analysis"] = _rule_llm_analysis(event_obj, ev["max_score"])

        result.append(event_obj)

        # Persist to event_registry (new v4.4)
        _persist_event(event_obj)

        # Register sources in source_registry
        _register_event_sources(source_names, source_auth_map)

        # Register entities in entity_registry
        _register_event_entities(related_with_ids)

    result.sort(key=lambda e: e["article_count"], reverse=True)
    _close_persist_db()
    return result

# ── v4.4 Helpers ─────────────────────────────────────────────────

_db = None  # module-level lazy connection for aggregate_events
_source_scores_cache = None


def _get_persist_db():
    """Lazy init: open DB once per aggregation run."""
    global _db
    if _db is None:
        from news_intel.db import init_db, get_db
        init_db()
        _db = get_db()
    return _db


def _close_persist_db():
    global _db
    if _db is not None:
        _db.close()
        _db = None


def _persist_event(event_obj: dict):
    try:
        db = _get_persist_db()
        from news_intel.db import upsert_event
        upsert_event(db, event_obj)
    except Exception:
        pass


def _register_event_sources(source_names: list, source_auth_map: dict):
    try:
        db = _get_persist_db()
        from news_intel.db import upsert_source
        for sn in source_names[:10]:
            sid = _source_name_to_id(sn)
            authority = source_auth_map.get(sn, 5)
            source_type = _infer_source_type_from_name(sn)
            upsert_source(db, sid, sn, source_type=source_type, authority=authority)
    except Exception:
        pass


def _register_event_entities(related_with_ids: list):
    try:
        db = _get_persist_db()
        from news_intel.db import upsert_entity
        for e in related_with_ids[:10]:
            upsert_entity(db, e["entity_id"], e["name"], entity_type=e["type"],
                          importance=_known_entity_importance.get(e["name"], 50))
    except Exception:
        pass


def _load_source_scores() -> dict:
    global _source_scores_cache
    if _source_scores_cache is None:
        try:
            config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "news_intel", "config")
            with open(os.path.join(config_dir, "source_scores.json"), encoding="utf-8") as f:
                _source_scores_cache = json.load(f).get("scores", {})
        except Exception:
            _source_scores_cache = {}
    return _source_scores_cache


def _source_name_to_id(name: str) -> str:
    clean = name.upper().replace(" ", "_").replace("-", "_").replace("'", "")
    clean = "".join(c for c in clean if c.isalnum() or c == "_")
    return f"SRC_{clean}" if clean else "SRC_UNKNOWN"


def _entity_name_to_id(name: str) -> str:
    clean = name.upper().replace(" ", "_").replace("-", "_").replace("'", "")
    clean = "".join(c for c in clean if c.isalnum() or c == "_")
    entity_type = _known_entity_types.get(name, "OTHER")
    prefix = {"Company": "COMP", "Person": "PERS", "Country": "CTRY",
              "Organization": "ORG", "Location": "LOC"}.get(entity_type, "ENT")
    return f"{prefix}_{clean}" if clean else f"ENT_UNKNOWN"


def _infer_source_type_from_name(name: str) -> str:
    gov_patterns = ["White House", "Fed ", "Federal Reserve", "SEC", "UN ", "UK Gov",
                    "ECB", "IMF", "World Bank", "OECD", "Bank of England", "BoE",
                    "NASA", "人民网", "新华网", "央视", "CCTV", "中国新闻网", "中国日报", "环球网"]
    for p in gov_patterns:
        if p in name:
            return "GOVERNMENT"
    if name in ("OpenAI", "Google AI", "GitHub", "ArXiv", "MIT Technology Review"):
        return "RESEARCH"
    if name in ("Reddit", "Hacker News"):
        return "SOCIAL"
    return "MEDIA"


_known_entity_importance = {
    "United States": 100, "China": 95, "Russia": 90, "Iran": 85, "Ukraine": 80,
    "United Kingdom": 80, "France": 75, "Germany": 75, "Israel": 80,
    "Donald Trump": 95, "OpenAI": 90, "Apple": 85, "NVIDIA": 85, "Tesla": 80,
    "Federal Reserve": 90, "European Union": 85, "NATO": 85, "UN": 80,
}

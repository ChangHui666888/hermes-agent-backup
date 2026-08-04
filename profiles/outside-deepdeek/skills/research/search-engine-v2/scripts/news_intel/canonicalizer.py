#!/usr/bin/env python3
"""canonicalizer.py v0.2 — 两阶段 Fact 抽取的 Stage 2 (Canonicalizer)

把 LLM/IE 输出的 Raw Fact 规范化为 Fact Graph:
  {
    action:  {type, event_type, detail},
    time, location,
    entities: [{name, id, type, role}]   ← 实体 Role 模型 (支持复合主体/多客体)
  }

v0.2 三增强:
  1. 动作语义优先级匹配 (SANCTIONS 100 > ELECTS 50, 非关键词顺序)
  2. 实体 Role 模型: 复合主体拆分 (Trump, DOJ) → 多个 entity[role=SUBJECT]
  3. 动作+客体联合规则: verb+object → action (impose...sanctions → SANCTIONS)

用法:
  from canonicalizer import canonicalize
  canonicalize({"subject":"US Government","action":"announced export control","object":"China","location":"","time":""})
"""

import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WEIGHTS = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "entity_weights.json")


# ═══════════════════════════════════════════════════════════
# 动作本体 v0.2 — (优先级, event_type, patterns)
# 优先级: 高信息量动作抢占 (战争/制裁 > 金融 > 法律 > 政治流程 > 普通)
# ═══════════════════════════════════════════════════════════
CANONICAL_ACTIONS = {
    # 战争/军事 (100)
    "ATTACKS":       (100, "Military",   [r"attack", r"strike", r"bomb", r"airstrike", r"assault", r"offensive", r"raid", r"missile", r"hit"]),
    "CEASEFIRE":     (100, "Diplomacy",  [r"ceasefire", r"truce", r"cease fire"]),
    # 制裁/管制 (100)
    "SANCTIONS":     (100, "Economic",   [r"sanction", r"embargo", r"blacklist"]),
    "EXPORT_CONTROL":(100, "Technology", [r"export control", r"restrict.*export", r"ban.*(chip|export)", r"chip restriction", r"semiconductor"]),
    "TARIFFS":       (100, "Economic",   [r"tariff", r"trade war", r"import dut"]),
    # 利率 (90)
    "RATE_CUT":      (90,  "Finance",    [r"cut.*rate", r"lower.*rate", r"rate cut", r"reduce.*rate"]),
    "RATE_HIKE":     (90,  "Finance",    [r"raise.*rate", r"hike.*rate", r"rate hike"]),
    # 法律 (90)
    "SUES":          (90,  "Legal",      [r"sue", r"lawsuit", r"litigation", r"indict", r"toss.*award", r"court.*case", r"defamation", r"appeal"]),
    "ACCUSES":       (90,  "Legal",      [r"accuse", r"allege", r"charge"]),
    "BANS":          (90,  "Legal",      [r"ban", r"prohibit", r"outlaw", r"restrict", r"block"]),
    # 金融市场 (80)
    "SURGES":        (80,  "Finance",    [r"surge", r"soar", r"jump", r"rally", r"climb", r"rise", r"record high", r"resume"]),
    "CRASHES":       (80,  "Finance",    [r"crash", r"plunge", r"plummet", r"tumble", r"slide", r"sell.?off"]),
    "REPORTS":       (80,  "Finance",    [r"report", r"earnings", r"revenue", r"profit", r"quarterly"]),
    # 外交 (70)
    "MEETS":         (70,  "Diplomacy",  [r"meet", r"summit", r"talk with", r"negotiat", r"diplomat"]),
    "PEACE_DEAL":    (70,  "Diplomacy",  [r"peace deal", r"peace agreement", r"peace treaty"]),
    # 政治流程 (50)
    "ELECTS":        (50,  "Politics",   [r"elect", r"vote", r"ballot"]),
    "APPOINTS":      (50,  "Leadership", [r"appoint", r"name .* as", r"named", r"nominated"]),
    "RESIGNS":       (50,  "Leadership", [r"resign", r"step down", r"quit", r"depart"]),
    # 普通动作 (30)
    "ANNOUNCES":     (30,  "Politics",   [r"announce", r"declare", r"unveil", r"reveal", r"launch", r"propose", r"set up", r"poised to", r"plans to"]),
    "WARNS":         (30,  "Politics",   [r"warn", r"caution", r"alert", r"threaten"]),
    "FUNDS":         (30,  "Economic",   [r"fund", r"invest", r"finance", r"grant"]),
    "DIES":          (30,  "Leadership", [r"die", r"dead", r"kill", r"assassinat", r"funeral", r"mourn"]),
    "CUTS":          (30,  "Economic",   [r"cut", r"reduce", r"slash", r"lower"]),
}

# 动作 + 客体联合规则: 动作文本命中缺失时, 从客体文本触发
_OBJECT_JOINT = {
    "SANCTIONS":     [r"sanction", r"embargo", r"blacklist"],
    "TARIFFS":       [r"tariff", r"trade war"],
    "EXPORT_CONTROL": [r"export control", r"chip", r"semiconductor", r"advanced ai chip"],
    "ATTACKS":       [r"attack", r"strike", r"militant", r"missile"],
    "BANS":          [r"ban", r"restrict"],
}

ROLES = ("SUBJECT", "OBJECT", "TARGET", "VICTIM", "SOURCE", "RESPONDER")


def _match(text: str, act: str) -> bool:
    prio, etype, patterns = CANONICAL_ACTIONS[act]
    return any(re.search(p, text) for p in patterns)


def canonicalize_action(raw_action: str, object_text: str = "", context: str = "") -> dict:
    """自由动作文本 → 规范 action_type (语义优先级 + 客体联合 + 标题上下文)

    v0.4 调优: 标题上下文只在"动作文本弱(优先级<70)"时覆盖。
    修复: "Oil jumped"(SURGES 80) 不被标题 "resume strikes"(ATTACKS) 误覆盖;
         "set up votes"(ELECTS 50) 可被标题 "sanction"(SANCTIONS) 覆盖。
    """
    text = (raw_action or "").lower()
    obj = (object_text or "").lower()
    ctx = (context or "").lower()
    TITLE_OVERRIDE = 70  # 动作文本优先级 <70(弱/泛化) 才允许标题覆盖

    def best_in(src, include_title=False):
        best = None
        for act in CANONICAL_ACTIONS:
            if _match(src, act):
                prio, etype, _ = CANONICAL_ACTIONS[act]
                if best is None or prio > best[0]:
                    best = (prio, act, etype)
        return best

    # 1. 动作文本优先
    b_text = best_in(text)
    # 2. 标题上下文: 仅当动作文本弱(无 或 优先级<TITLE_OVERRIDE)
    if b_text and b_text[0] >= TITLE_OVERRIDE:
        best = b_text
    else:
        b_title = best_in(ctx)
        best = b_title if (b_title and (b_text is None or b_title[0] > b_text[0])) else b_text
    # 3. 客体联合 (仅当动作仍无强信号)
    if not best or best[0] < TITLE_OVERRIDE:
        for act, patterns in _OBJECT_JOINT.items():
            if any(re.search(p, obj) for p in patterns):
                prio, etype, _ = CANONICAL_ACTIONS[act]
                if best is None or prio > best[0]:
                    best = (prio, act, etype)
    if not best:
        return {"type": "OTHER", "event_type": "General", "detail": (raw_action or "")[:60]}
    return {"type": best[1], "event_type": best[2], "detail": (raw_action or "")[:60]}


# ═══════════════════════════════════════════════════════════
# 实体归一 + Role 模型
# ═══════════════════════════════════════════════════════════
_ALIAS_MAP = {}
_TYPES = {"persons": "Person", "companies": "Company", "countries": "Country"}


def _load_aliases():
    global _ALIAS_MAP
    if _ALIAS_MAP:
        return
    try:
        w = json.load(open(_WEIGHTS, encoding="utf-8"))
    except Exception:
        w = {}
    for cat, etype in _TYPES.items():
        names = list(w.get(cat, {}).keys())
        english = [n for n in names if all(ord(c) < 128 for c in n)]
        canonical = max(english, key=len) if english else (names[0] if names else "")
        for n in names:
            _ALIAS_MAP[n.lower()] = (canonical, etype)


_ID_PREFIX = {"Country": "CTRY", "Person": "PERS", "Company": "COMP", "Organization": "ORG",
              "Location": "LOC", "Government": "ORG", "Military": "ORG", "Other": "ENT"}

# Location 本体 (Phase A): 城市 → 国家, 聚合/事件地图更准
CITY_TO_COUNTRY = {
    "Beijing": "China", "Shanghai": "China", "Shenzhen": "China", "Hong Kong": "China",
    "Washington": "United States", "Washington DC": "United States", "New York": "United States",
    "Los Angeles": "United States", "San Francisco": "United States", "Moscow": "Russia",
    "Kyiv": "Ukraine", "Tehran": "Iran", "Jerusalem": "Israel", "Tel Aviv": "Israel",
    "London": "United Kingdom", "Paris": "France", "Berlin": "Germany", "Tokyo": "Japan",
    "Seoul": "South Korea", "New Delhi": "India", "Riyadh": "Saudi Arabia", "Taipei": "Taiwan",
    "Brussels": "Belgium", "Geneva": "Switzerland", "Vienna": "Austria", "Rome": "Italy",
    "Madrid": "Spain", "Amsterdam": "Netherlands", "Stockholm": "Sweden", "Oslo": "Norway",
    "Warsaw": "Poland", "Prague": "Czech Republic", "Ankara": "Turkey", "Dubai": "UAE",
}


# 新闻媒体来源 (2026-08-03): 排除媒体被当作事件主体 (Al Jazeera→US 误判)。
# 只含新闻媒体, 不含机构源 (Federal Reserve/ECB/UN/OpenAI 是合法事件主体)。
MEDIA_SOURCES = frozenset([
    "reuters", "bloomberg", "bloomberg markets", "financial times", "ft", "wall street journal",
    "wsj", "bbc", "bbc world", "bbc news", "cnn", "nbc news", "cbs news", "abc news",
    "new york times", "nyt", "washington post", "wapo", "the guardian", "guardian",
    "al jazeera", "associated press", "ap news", "ap", "cnbc", "marketwatch",
    "seeking alpha", "investing.com", "yahoo finance", "barron's", "barrons",
    "the economist", "economist", "france 24", "dw", "dw news", "deutsche welle",
    "le monde", "scmp", "south china morning post", "sky news", "npr", "politico",
    "the hill", "newsweek", "techcrunch", "the verge", "wired", "ars technica",
    "mit technology review", "hacker news", "reddit", "reddit worldnews", "cctv",
])

_MEDIA_PAT = re.compile(r"\b(" + "|".join(re.escape(m) for m in MEDIA_SOURCES) + r")\b", re.IGNORECASE)


def is_media_source(name: str) -> bool:
    """新闻来源名检测 (词边界, 防 'dw' 误伤 'dow')。匹配 "Al Jazeera" / "CBS News" / "BBC's" 等。"""
    if not name or not (name or "").strip():
        return False
    return bool(_MEDIA_PAT.search(name))


def _infer_type(name: str) -> str:
    low = name.lower()
    if any(kw in low for kw in ["government", "department", "ministry", "administration", "white house", "fed", "reserve", "bank", "commission", "senate", "congress", "nato", "un", "european union", "opec", "imf", "world bank", "doj", "supreme court"]):
        return "Organization"
    if any(kw in low for kw in ["army", "navy", "forces", "military", "defense", "guard"]):
        return "Military"
    if any(kw in low for kw in ["president", "minister", "chairman", "ceo", "governor", "senator", "secretary", "leader", "king", "crown prince", "trump", "zelensky", "putin"]):
        return "Person"
    if any(kw in low for kw in ["iran", "russia", "ukraine", "china", "us", "usa", "united states", "israel", "saudi", "france", "germany", "japan", "india", "korea", "taiwan"]):
        return "Country"
    return "Other"


def resolve_entity(name: str, gliner_type: str = "") -> dict:
    """别名 → 规范名 + 稳定 id + 类型"""
    raw = (name or "").strip()
    if not raw:
        return {"name": "", "id": "", "type": ""}
    _load_aliases()
    canonical, alias_type = _ALIAS_MAP.get(raw.lower(), (raw, ""))
    # Location 本体 (Phase A): 城市 → 国家 (Beijing → China/CTRY_CHINA)
    if canonical in CITY_TO_COUNTRY:
        canonical = CITY_TO_COUNTRY[canonical]
        etype = "Country"
    else:
        etype = alias_type or gliner_type or _infer_type(canonical)
    if etype.lower() in ("person",): etype = "Person"
    elif etype.lower() in ("company",): etype = "Company"
    elif etype.lower() in ("country",): etype = "Country"
    elif etype.lower() in ("organization", "government", "military"): etype = "Organization"
    elif etype.lower() in ("city", "location"): etype = "Location"
    else: etype = "Other"
    prefix = _ID_PREFIX.get(etype, "ENT")
    clean = canonical.upper().replace(" ", "_").replace("-", "_").replace("'", "")
    clean = "".join(c for c in clean if c.isalnum() or c == "_")
    return {"name": canonical, "id": f"{prefix}_{clean}" if clean else "", "type": etype}


def split_entities(text: str) -> list[str]:
    """拆分复合主体/客体: 'Trump, DOJ' → ['Trump','DOJ']; 'US and Saudi Arabia' → ['US','Saudi Arabia']"""
    if not text or not text.strip():
        return []
    parts = re.split(r",|\band\b|\bas well as\b|;|&| plus ", text)
    names = [p.strip().strip("[]()'\"") for p in parts if p.strip()]
    return names if names else [text.strip()]


# ═══════════════════════════════════════════════════════════
# 主入口 v0.2
# ═══════════════════════════════════════════════════════════
def canonicalize(raw: dict, title: str = "") -> dict:
    """Raw Fact → Fact Graph (实体 Role 模型)

    v0.3: title 作为动作匹配上下文 (LLM 截断 action 时补全)。
    返回:
      {action:{type,event_type,detail}, time, location,
       entities:[{name,id,type,role}], subject_hint, object_hint}
    """
    raw_subj = raw.get("subject", "")
    raw_obj = raw.get("object", "")
    act = canonicalize_action(raw.get("action", ""), raw_obj, title)
    entities = []
    # 复合主体 → 多个 SUBJECT
    for nm in split_entities(raw_subj):
        e = resolve_entity(nm)
        if e["id"]:
            entities.append({**e, "role": "SUBJECT"})
    # 复合客体 → 多个 OBJECT
    for nm in split_entities(raw_obj):
        e = resolve_entity(nm)
        if e["id"]:
            entities.append({**e, "role": "OBJECT"})
    return {
        "action": act,
        "time": raw.get("time", ""),
        "location": raw.get("location", ""),
        "entities": entities,
        "subject_hint": raw_subj[:60],
        "object_hint": raw_obj[:60],
    }


if __name__ == "__main__":
    import json as _j
    tests = [
        ({"subject": "Trump, DOJ", "action": "ask Supreme Court to toss", "object": "$83.3M defamation award to E. Jean Carroll"},
         "Trump, DOJ ask Supreme Court to toss $83.3M defamation award"),
        ({"subject": "Senate", "action": "set up votes", "object": "Russia"},
         "Senate sets up votes to sanction Russia for Ukraine war"),
        ({"subject": "US and Saudi forces", "action": "attack", "object": "Tehran-aligned groups"},
         "Iran war live: US, Saudi forces attack Tehran-aligned groups"),
        ({"subject": "US", "action": "impose", "object": "new Russia sanctions package"},
         "US poised to impose new Russia sanctions package"),
        ({"subject": "Federal Reserve", "action": "cut", "object": "interest rates"},
         "Federal Reserve cuts interest rates by 50 basis points"),
        ({"subject": "US Government", "action": "announced export control", "object": "China"},
         "US announced export control on advanced AI chips to China"),
    ]
    for t, title in tests:
        c = canonicalize(t, title)
        print(_j.dumps({
            "action": c["action"]["type"],
            "entities": [(e["name"], e["id"], e["role"]) for e in c["entities"]],
        }, ensure_ascii=False))

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
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WEIGHTS = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "entity_weights.json")

# Knowledge Base V1 (知识库): repo 根 knowledge_base/, 中英别名 → 稳定 Entity ID
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_KB_LOADER = None


def _kb():
    """懒加载 knowledge_base.loader; 缺失时回退 None (不阻塞现有逻辑)。"""
    global _KB_LOADER
    if _KB_LOADER is None:
        try:
            if _REPO not in sys.path:
                sys.path.insert(0, _REPO)
            from knowledge_base import loader as _kbl
            _KB_LOADER = _kbl
        except Exception:
            _KB_LOADER = False
    return _KB_LOADER or None


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
    "SUES":          (90,  "Legal",      [r"sue", r"lawsuit", r"litigation", r"toss.*award", r"court.*case", r"defamation", r"appeal"]),
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
    # G3 扩充 (2026-08-06): 高频动作 (对应 ACTION_CATALOG)
    "INVADES":       (100, "Military",   [r"invade", r"invasion", r"入侵|占领"]),
    "SEIZES":        (100, "Military",   [r"seize", r"seizure", r"confiscate", r"夺取|扣押|没收"]),
    "INDICTS":       (90,  "Legal",      [r"indict", r"indictment", r"控告"]),
    "ARRESTS":       (90,  "Legal",      [r"arrest", r"detain", r"逮捕|拘留"]),
    "BANKRUPTS":     (90,  "Finance",    [r"bankrupt", r"insolven", r"破产|倒闭"]),
    "DROPS":         (80,  "Finance",    [r"\bdrop", r"decline", r"下跌|下滑"]),
    "IPO":           (80,  "Finance",    [r"ipo", r"initial public offering", r"上市|首次公开募股"]),
    "MERGES":        (80,  "Finance",    [r"merge", r"merger", r"合并|并购"]),
    "ACQUIRES":      (80,  "Finance",    [r"acquire", r"acquisition", r"takeover", r"收购|并购"]),
    "LAUNCHES":      (80,  "Technology", [r"launch", r"推出|发布|发射"]),
    "VISITS":        (70,  "Diplomacy",  [r"visit", r"访问|出访"]),
    "ESCALATES":     (70,  "Military",   [r"escalat", r"升级|加剧"]),
    "VETOES":        (50,  "Politics",   [r"veto", r"否决"]),
    "APPROVES":      (50,  "Politics",   [r"approve", r"approval", r"批准|通过"]),
    "CONFIRMS":      (50,  "Politics",   [r"confirm", r"确认|证实"]),
    "DENIES":        (50,  "Politics",   [r"deny", r"denies", r"denied", r"denial", r"否认|辟谣"]),
    "FIRES":         (50,  "Leadership", [r"\bfire", r"sack", r"解雇|开除|免职"]),
    "SUCCEEDS":      (50,  "Leadership", [r"succeed.*as", r"take over.*role", r"接任|继任"]),
    "EXPELLS":       (50,  "Diplomacy",  [r"expel", r"deport", r"驱逐|遣返"]),
    "GROWS":         (30,  "Economic",   [r"\bgrow", r"growth", r"增长|扩大"]),
    "PROTESTS":      (30,  "Politics",   [r"protest", r"demonstrat", r"抗议|示威"]),
    "HACKS":         (30,  "Cyber",      [r"hack", r"breach", r"黑客|入侵"]),
    "INVESTIGATES":  (30,  "Legal",      [r"investigat", r"probe", r"调查|侦查"]),
    # P0 Fact Schema V2 (2026-08-10, ISS-20260810-012): 常见动词不再落 OTHER
    "REJECTS":       (60,  "Diplomacy",  [r"reject", r"refus", r"rules? out", r"turns? down"]),
    "TESTS":         (60,  "Technology", [r"\btest", r"\btesting", r"trials?"]),
    "AFFIRMS":       (60,  "Diplomacy",  [r"affirm", r"reaffirm", r"assert"]),
    "AGREES":        (60,  "Diplomacy",  [r"\bagree", r"reach(?:ed)? (?:an )?agreement", r"reach(?:ed)? a deal"]),
    "WITHDRAWS":     (70,  "Military",   [r"withdraw", r"pull (?:out|back)", r"end military use", r"end .*military", r"end use of"]),
    "PAUSES":        (60,  "Technology", [r"pause", r"pausing", r"halt", r"suspend"]),
    "TRANSFERS":     (60,  "Diplomacy",  [r"transfer", r"hand over"]),
    "INTEGRATES":    (60,  "Technology", [r"integrat"]),
    "BEATS":         (80,  "Finance",    [r"tops?", r"beats?", r"surpass", r"beat.*estimates", r"beat.*earnings", r"tops? estimates"]),
    "DEPLOYS":       (60,  "Military",   [r"deploy", r"deployment", r"mobiliz"]),
    "CLAIMS":        (40,  "Politics",   [r"claim", r"claims?"]),
    "STATES":        (30,  "Politics",   [r"\bsays?\b", r"\bsaid\b", r"stated", r"\btold\b", r"\bcalls?\b", r"called",
                                         r"vows?", r"insists?", r"urges?", r"describes?", r"argues?", r"seeks?", r"seeking"]),
}

# 动作 + 客体联合规则: 动作文本命中缺失时, 从客体文本触发
_OBJECT_JOINT = {
    "SANCTIONS":     [r"sanction", r"embargo", r"blacklist", r"制裁", r"禁运"],
    "TARIFFS":       [r"tariff", r"trade war", r"关税", r"贸易战"],
    "EXPORT_CONTROL": [r"export control", r"chip", r"semiconductor", r"advanced ai chip",
                       r"出口管制", r"芯片", r"半导体", r"限制出口"],
    "ATTACKS":       [r"attack", r"strike", r"militant", r"missile", r"攻击", r"袭击", r"导弹", r"空袭"],
    "BANS":          [r"ban", r"restrict", r"禁止", r"限制"],
    # G3 (2026-08-06): 动作弱时客体联合触发利率动作
    "RATE_CUT":      [r"interest rate", r"基准利率", r"利率"],
    "RATE_HIKE":     [r"interest rate", r"基准利率", r"利率"],
}

ROLES = ("SUBJECT", "OBJECT", "TARGET", "VICTIM", "SOURCE", "RESPONDER")


# G3 实验发现 (2026-08-06): 中文动作在 canonicalizer 归一失效 — 中文 pattern 补充表
_CN_ACTION = {
    "SANCTIONS": [r"制裁", r"禁运"], "TARIFFS": [r"关税", r"贸易战"],
    "EXPORT_CONTROL": [r"出口管制", r"限制出口", r"芯片禁令"], "RATE_CUT": [r"降息", r"下调利率"],
    "RATE_HIKE": [r"加息", r"上调利率"], "SUES": [r"起诉", r"诉讼"],
    "ANNOUNCES": [r"宣布", r"公布", r"发布", r"起草", r"制定", r"拟订"], "WARNS": [r"警告", r"警示"],
    "RESIGNS": [r"辞职", r"卸任"], "APPOINTS": [r"任命", r"提名"],
    "ATTACKS": [r"袭击", r"攻击", r"空袭", r"轰炸"], "CEASEFIRE": [r"停火", r"休战"],
    "INVADES": [r"入侵", r"占领"], "ACQUIRES": [r"收购", r"并购"],
    "MERGES": [r"合并", r"并购"], "IPO": [r"上市", r"首次公开募股"],
    "ARRESTS": [r"逮捕", r"拘留"], "VISITS": [r"访问", r"出访"],
    "DENIES": [r"否认"], "APPROVES": [r"批准", r"通过"], "VETOES": [r"否决"],
    "EXPELS": [r"驱逐", r"遣返"], "DIES": [r"去世", r"死亡", r"遇刺"],
    "ELECTS": [r"选举", r"当选", r"投票"],
    # G4 (2026-08-06): 中文聚合补充 — 仅限 CANONICAL_ACTIONS 已有动作
    "FUNDS":  [r"投资", r"注资", r"融资", r"拨款"],
    "CUTS":   [r"削减", r"下调", r"降低", r"减少"],
    "BANS":   [r"禁止", r"封禁", r"禁用", r"限制"],
    "MEETS":  [r"会面", r"会晤", r"会见", r"会谈"],
    "REPORTS": [r"财报", r"营收", r"利润", r"业绩"],
    "ACCUSES": [r"指控", r"指责", r"谴责"],
    "PEACE_DEAL": [r"和平协议", r"和平条约", r"和平协定"],
    "REJECTS": [r"拒绝"], "TESTS": [r"测试"], "AFFIRMS": [r"重申", r"确认"],
    "AGREES": [r"同意", r"达成"], "WITHDRAWS": [r"撤出", r"撤离", r"移交", r"终止.*军事"],
    "PAUSES": [r"暂停", r"中止"], "TRANSFERS": [r"移交", r"转移"], "INTEGRATES": [r"整合", r"集成"],
    "BEATS": [r"超预期", r"超出预期"], "CLAIMS": [r"声称", r"宣称"], "STATES": [r"表示", r"称", r"说"],
}


def _match(text: str, act: str) -> bool:
    prio, etype, patterns = CANONICAL_ACTIONS[act]
    if any(re.search(p, text) for p in patterns):
        return True
    return any(re.search(p, text) for p in _CN_ACTION.get(act, []))


def _is_value_phrase(name: str) -> bool:
    """值/数字/日期/短语/子句判定 — 非实体, 不应实体化 ($0.22 / 81st anniversary / AI chip fears ease)。"""
    if not name or not name.strip():
        return True
    n = name.strip()
    if re.fullmatch(r"[$£€¥]?\s*[\d,\.]+%?", n):
        return True
    if re.match(r"^[\d$£€¥]", n):
        return True
    if re.search(r"\d+(st|nd|rd|th)\s+(anniversary|century|year|decade|day)", n, re.I):
        return True
    if len(n.split()) > 4:
        return True
    if re.match(r"^(to|for|in|on|at|of|with|by|from|targeting|using|against|into|after|before|amid|as|that|the|has|have|had|being|is|are|was|were|could|would|should|may|might|will|be|becoming)\b", n, re.I):
        return True
    return False


_STATUS_ENUM = {"COMPLETED", "ONGOING", "PLANNED", "EXPECTED", "CONSIDERED", "DELAYED",
                "CANCELLED", "DENIED", "ATTEMPTED", "ANNOUNCED", "UNKNOWN"}
_POLARITY_ENUM = {"POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"}


def _action_meta(raw_action: str, status_hint: str = "", polarity_hint: str = "") -> tuple:
    """推断 action.status / action.polarity (契约 §3.2/3.3, 含 UNKNOWN; Qwen hint 优先, 否则规则推导)。"""
    t = (raw_action or "").lower()
    if (status_hint or "").strip():
        status = status_hint.strip().upper()
        if status not in _STATUS_ENUM:
            status = "UNKNOWN"
    else:
        # 结果/否定态优先 (scrapped plans = CANCELLED, 先于 PLANNED; delayed 先于 COMPLETED)
        if re.search(r"\b(cancel|canceled|cancelled|scrap|scrapped|abandon|abandoned)\b", t):
            status = "CANCELLED"
        elif re.search(r"\b(deny|denies|denied|refus|refuses?|refused|reject|rejected|rejects)\b", t):
            status = "DENIED"
        elif re.search(r"\b(delay|delayed|delays|postpon|postpone|postponed|slipped?)\b", t):
            status = "DELAYED"
        elif re.search(r"\b(may|might|plans? to|proposed?|poised|intends? to|will|to be)\b", t):
            status = "PLANNED"
        elif re.search(r"\b(expected to|could|would|forecast|projected)\b", t):
            status = "EXPECTED"
        elif re.search(r"\b(consider|considering|mulling|weighing)\b", t):
            status = "CONSIDERED"
        elif re.search(r"\b(attempt|attempted|try(?:ing)? to|seek(?:s|ing)? to)\b", t):
            status = "ATTEMPTED"
        elif re.search(r"\b(announce|announced|unveil|unveiled|declare|declared)\b", t):
            status = "ANNOUNCED"
        elif re.search(r"\b(acquired|bought|sold|reported|voted|signed|launched|approved|said|took|made|rejected)\b", t) \
                or re.search(r"\b\w+ed\b", t):
            status = "COMPLETED"
        else:
            status = "UNKNOWN" if not t else "ONGOING"
    if (polarity_hint or "").strip():
        polarity = polarity_hint.strip().upper()
        if polarity not in _POLARITY_ENUM:
            polarity = "UNKNOWN"
    else:
        if re.search(r"\b(deny|denies|denied|refus|reject|rejected|rejects|fail(?:ed)? to|won'?t|not|cannot|can'?t|no longer|oppos|cancel|scrap|delay)\b", t):
            polarity = "NEGATIVE"
        elif re.search(r"\b(approve|agrees?|agreed|confirm|support|accept|okay|endorse)\b", t):
            polarity = "POSITIVE"
        else:
            polarity = "UNKNOWN" if not t else "NEUTRAL"
    return status, polarity


def infer_object_type(name: str, entity: dict = None) -> str:
    """object_type 推断 (契约 §3.4)。真实实体→ENTITY; 金额→AMOUNT; 日期纪念→EVENT; 长句→STATEMENT; 短语→CONCEPT。"""
    n = (name or "").strip()
    if not n:
        return "UNKNOWN"
    if entity and entity.get("entity_id"):
        return "ENTITY"
    if re.search(r"\d+(st|nd|rd|th)\s+(anniversary|century|decade|year|day)", n, re.I):
        return "EVENT"
    if re.fullmatch(r"[$£€¥]?\s*[\d,\.]+%?", n) or re.match(r"^[\d$£€¥]", n):
        return "AMOUNT"
    if len(n.split()) > 4:
        return "STATEMENT"
    if _is_value_phrase(n):
        return "CONCEPT"
    return "UNKNOWN"


def canonicalize_action(raw_action: str, object_text: str = "", context: str = "",
                        status_hint: str = "", polarity_hint: str = "") -> dict:
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
    # 3. 客体联合 (P0: 仅当无具体动词命中 — 信任 TESTS/REJECTS 等具体动词, 不被客体联合覆盖成 EXPORT_CONTROL)
    if best is None or best[0] < 30:
        for act, patterns in _OBJECT_JOINT.items():
            if any(re.search(p, obj) for p in patterns):
                prio, etype, _ = CANONICAL_ACTIONS[act]
                if best is None or prio > best[0]:
                    best = (prio, act, etype)
    status, polarity = _action_meta(raw_action, status_hint, polarity_hint)
    if not best:
        return {"type": "OTHER", "event_type": "General", "detail": (raw_action or "")[:60],
                "status": status, "polarity": polarity, "verb": (raw_action or "")[:60]}
    return {"type": best[1], "event_type": best[2], "detail": (raw_action or "")[:60],
            "status": status, "polarity": polarity, "verb": (raw_action or "")[:60]}


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
# v2.4 (2026-08-09): 迁移到 knowledge_base/locations.yaml 加载, 缺失回退内置。
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

_city_country_cache = None


def _get_city_country() -> dict:
    """从 knowledge_base/locations.yaml 构建 城市→国家 (name.en/zh + aliases); 空则回退内置。"""
    global _city_country_cache
    if _city_country_cache is not None:
        return _city_country_cache
    m = {}
    try:
        import yaml as _y
        import os as _os
        _p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                           "..", "knowledge_base", "locations.yaml")
        for cand in [_p, "knowledge_base/locations.yaml"]:
            if _os.path.exists(cand):
                _d = _y.safe_load(open(cand, encoding="utf-8")) or {}
                for ent in (_d.get("locations") or {}).values():
                    country = ent.get("country")
                    if not country:
                        continue
                    nm = ent.get("name", {})
                    names = []
                    if isinstance(nm, dict):
                        names += [nm.get("en", ""), nm.get("zh", "")]
                    elif isinstance(nm, str):
                        names.append(nm)
                    names += ent.get("aliases", []) or []
                    for n in names:
                        if n:
                            m[n] = country
                break
    except Exception:
        pass
    _city_country_cache = m if m else CITY_TO_COUNTRY
    return _city_country_cache


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

# 中文媒体名 (词边界 \b 对 CJK 无效, 用子串匹配)
_CN_MEDIA = ("路透社", "法新社", "美联社", "新华社", "彭博社", "纽约时报", "联合早报",
             "央视", "环球时报", "人民日报", "中国新闻网", "中新网", "南华早报", "观察者网")


def is_media_source(name: str) -> bool:
    """新闻来源名检测 (词边界, 防 'dw' 误伤 'dow')。匹配 "Al Jazeera" / "CBS News" / "BBC's" 等。
    中文媒体名走子串匹配 (路透社/新华社/央视 等)。"""
    if not name or not (name or "").strip():
        return False
    if _MEDIA_PAT.search(name):
        return True
    return any(m in name for m in _CN_MEDIA)


def _infer_type(name: str) -> str:
    low = name.lower()
    if any(kw in low for kw in ["government", "department", "ministry", "administration", "white house", "fed", "reserve", "bank", "commission", "senate", "congress", "nato", "un", "european union", "opec", "imf", "world bank", "doj", "supreme court", "政府", "委员会", "央行", "国防部", "商务部", "工信部", "白宫", "国务院"]):
        return "Organization"
    if any(kw in low for kw in ["army", "navy", "forces", "military", "defense", "guard", "军队", "军方", "部队"]):
        return "Military"
    if any(kw in low for kw in ["president", "minister", "chairman", "ceo", "governor", "senator", "secretary", "leader", "king", "crown prince", "trump", "zelensky", "putin", "总统", "主席", "部长", "总理", "国王", "大使", "首脑"]):
        return "Person"
    if any(kw in low for kw in ["iran", "russia", "ukraine", "china", "us", "usa", "united states", "israel", "saudi", "france", "germany", "japan", "india", "korea", "taiwan", "美国", "中国", "德国", "俄罗斯", "伊朗", "日本", "韩国", "台湾", "朝鲜", "乌克兰", "英国", "法国"]):
        return "Country"
    return "Other"


def resolve_entity(name: str, gliner_type: str = "") -> dict:
    """别名 → 规范名 + 稳定 id + 类型 (Knowledge Base V1 优先, 回退本地本体)"""
    raw = (name or "").strip()
    if not raw:
        return {"name": "", "id": "", "type": ""}
    # EXCHANGE:TICKER 前缀剥离 (NASDAQ:NVDA → NVDA): 交易所代码不是实体名的一部分
    lookup = raw
    if ":" in raw:
        pre, _, rest = raw.partition(":")
        if pre and rest and re.fullmatch(r"[A-Za-z]{2,6}", pre):
            lookup = rest
    # KB V1: 中英别名 → 稳定 Entity ID (特朗普→PERS_TRUMP, 中国→CTRY_CHINA)
    kb = _kb()
    if kb:
        try:
            hit = kb.resolve(lookup)
            if hit:
                cid, canon, etype = hit
                return {"name": canon or raw, "id": cid, "type": etype}
        except Exception:
            pass
    _load_aliases()
    canonical, alias_type = _ALIAS_MAP.get(lookup.lower(), (lookup, ""))
    # Location 本体 (Phase A): 城市 → 国家 (Beijing → China/CTRY_CHINA)
    if canonical in CITY_TO_COUNTRY:
        canonical = _get_city_country()[canonical]
        etype = "Country"
    else:
        etype = alias_type or gliner_type or _infer_type(canonical)
    if etype.lower() in ("person",): etype = "Person"
    elif etype.lower() in ("company",): etype = "Company"
    elif etype.lower() in ("country",): etype = "Country"
    elif etype.lower() in ("organization", "government", "military"): etype = "Organization"
    elif etype.lower() in ("city", "location"): etype = "Location"
    else: etype = "Other"
    if len(canonical.split()) > 3 or _is_value_phrase(canonical):
        # P0/P1 (ISS-20260810-012): 值/数字/日期/短语/多词句/动词短语(has Trump cornered) → 不实体化。
        # 原始 name 由 fact.subject/object.name 保留, 聚合走 raw name; entity_id 空 = 非实体。
        return {"name": canonical, "id": "", "type": "Other"}
    if etype == "Other":
        # Entity Grounding 最小版 (2026-08-10): 未知专有名词 → Candidate id (类型猜测), 使跨事实可匹配。
        etype = _guess_candidate_type(canonical)
    prefix = _ID_PREFIX.get(etype, "ENT")
    clean = canonical.upper().replace(" ", "_").replace("-", "_").replace("'", "")
    clean = "".join(c for c in clean if c.isalnum() or c == "_")
    return {"name": canonical, "id": f"{prefix}_{clean}" if clean else "", "type": etype}


def _guess_candidate_type(name: str) -> str:
    """未知专有名词 → 候选类型 (公司后缀/组织词/人名)。最小可用, 不做复杂KG。"""
    low = name.lower()
    if re.search(r"(公司|集团|株式会社)($|股份有限公司)", name) or re.search(r"(inc|corp|ltd|llc|gmbh)\.?$", low):
        return "Company"
    if re.search(r"(部|政府|委员会|央行|银行|国防|军队|大学|研究院|协会|组织|中心|局|司令部|司令)", low):
        return "Organization"
    if any('一' <= c <= '鿿' for c in name):  # CJK
        return "Person" if len(name) <= 6 else "Organization"
    return "Organization"


def split_entities(text: str) -> list[str]:
    """拆分复合主体/客体: 'Trump, DOJ' → ['Trump','DOJ']; 'US and Saudi Arabia' → ['US','Saudi Arabia'];
    中文: '三星电子和SK海力士' → ['三星电子','SK海力士']"""
    if not text or not text.strip():
        return []
    parts = re.split(r",|\band\b|\bas well as\b|;|&| plus |、|和|与|及", text)
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
    # G7: Ontology Validator (三层归一第三层) — 实体 ID 前缀/类型一致性诊断, 不阻断
    try:
        from ontology_validator import validate_entities
        _v_ok, _v_issues, _v_valid = validate_entities(entities)
    except Exception:
        _v_ok, _v_issues, _v_valid = True, [], len(entities)
    return {
        "action": act,
        "time": raw.get("time", ""),
        "location": raw.get("location", ""),
        "entities": entities,
        "subject_hint": raw_subj[:60],
        "object_hint": raw_obj[:60],
        "validation": {"ok": _v_ok, "issues": _v_issues,
                       "valid_entities": _v_valid, "total_entities": len(entities)},
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

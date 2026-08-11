"""fact_validator.py — Fact Quality Gate (P0, ISS-20260810-012)

Raw Fact → Validator → PASS / REPAIR / REJECT
  PASS   = 结构完整、语义合理 → 可进入 Aggregator
  REPAIR = 存在规则可确定修复的问题 (unknown→null / 时间非时间清空 / 地点规范化 / Action 归一) → 修复后视为 PASS
  REJECT = 事实本身不成立 (无 Subject / Subject 非实体 / 无 Action / 公司后缀误作实体) → **禁止进入 Aggregator**

边界: 只 验证→轻量修复→拒绝, **不重新理解全文/重新生成 Fact** (否则变成第二个 LLM Fact Engine)。
契约: references/fact-schema-v2.md §4
"""
import re

_UNKNOWN_LITERALS = {"", "unknown", "none", "n/a", "na", "null", "nil", "未知", "无", "未", "undetermined"}
_JUNK_SUFFIX = re.compile(r"^(?:the\s+)?(?:inc|inc\.|corp|corp\.|corp\.?$|ltd|ltd\.|llc|llc\.|co|co\.|gmbh|inc\.$)\s*$", re.I)
# 明显非时间: 动词/从句/长短语
_NON_TIME = re.compile(r"\b(?:is|was|will|would|has|have|because|as|before|after|until|while|during|latest|friday|monday|tuesday|wednesday|thursday|saturday|sunday|the day|a day|this year|next year)\b", re.I)


def _clean(value):
    v = (value or "").strip()
    return v if v.lower() not in _UNKNOWN_LITERALS else ""


def _norm_fact(fact: dict) -> dict:
    """防御性归一: 兼容旧格式(旧 payload subject/object/action/location/time 为字符串) → Schema V2 结构。"""
    f = dict(fact)
    for k in ("subject", "object"):
        v = f.get(k)
        if isinstance(v, str):
            f[k] = {"name": v, "entity_id": None, "type": "Other"}
    act = f.get("action")
    if isinstance(act, str):
        f["action"] = {"type": f.get("action_type") or "OTHER",
                       "status": f.get("action_status") or "UNKNOWN",
                       "polarity": f.get("action_polarity") or "UNKNOWN", "verb": act}
    for k in ("location", "time"):
        v = f.get(k)
        if isinstance(v, str):
            f[k] = {"name": v, "entity_id": None, "type": None} if k == "location" else {"raw": v, "value": None}
    return f


def validate_fact(fact: dict) -> dict:
    """返回 {verdict: 'PASS'|'REPAIR'|'REJECT', repaired: dict|None, reasons: [str]}"""
    fact = _norm_fact(fact)
    repaired = dict(fact)
    reasons = []

    # ── 1. Subject ──
    from news_intel.canonicalizer import _is_value_phrase
    subj = fact.get("subject") or {}
    subj_name = _clean(subj.get("name"))
    if not subj_name:
        reasons.append("SUBJECT_EMPTY")
    elif _JUNK_SUFFIX.match(subj_name):
        reasons.append("SUBJECT_JUNK_SUFFIX")
    elif _is_value_phrase(subj_name):
        # 值/短语/句子当主体 → 事实不成立 (但大写专有名词即使无 entity_id 也接受, 聚合走 raw name)
        reasons.append("SUBJECT_NOT_ENTITY")

    # ── 2. Action ──
    act = fact.get("action") or {}
    act_type = act.get("type") or "OTHER"
    verb = _clean(act.get("verb"))
    if act_type == "OTHER" and not verb:
        reasons.append("ACTION_EMPTY")
    # OTHER 但有 verb → 允许 (REPAIR: 保留 verb; 不强映射)

    # ── 3. Object (值/句子允许, object_type 已区分; 仅清 literal Unknown) ──
    obj = fact.get("object") or {}
    obj_name = _clean(obj.get("name"))
    if not obj_name:
        reasons.append("OBJECT_EMPTY")
    if not obj_name and (obj.get("name") or "").strip():
        repaired["object"] = {"name": None, "entity_id": None, "type": "Other", "object_type": "UNKNOWN"}

    # ── 4. Time: 明显非时间 → 清空 (REPAIR) ──
    time_raw = fact.get("time") or {}
    tr = _clean(time_raw.get("raw"))
    if tr and (len(tr.split()) > 4 or _NON_TIME.search(tr)):
        repaired["time"] = {"raw": None, "value": None}
        reasons.append("TIME_NOT_TIME")

    # ── 5. Location: unknown/空 → null (REPAIR) ──
    loc = fact.get("location") or {}
    lname = _clean(loc.get("name"))
    if not lname and (loc.get("name") or "").strip():
        repaired["location"] = {"name": None, "entity_id": None, "type": None}
        reasons.append("LOCATION_UNKNOWN")

    # ── 判定 ──
    hard_fail = {"SUBJECT_EMPTY", "SUBJECT_NOT_ENTITY", "SUBJECT_JUNK_SUFFIX", "ACTION_EMPTY"}
    if any(r in hard_fail for r in reasons):
        return {"verdict": "REJECT", "repaired": None, "reasons": reasons}
    if reasons:
        return {"verdict": "REPAIR", "repaired": repaired, "reasons": reasons}
    return {"verdict": "PASS", "repaired": repaired, "reasons": []}


def validate_facts(facts: list) -> list:
    """批量: 返回 [{verdict, repaired, reasons}]。调用方只放行 PASS / REPAIR(repaired)。"""
    return [validate_fact(f) for f in facts]

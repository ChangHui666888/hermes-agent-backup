"""ontology_validator.py — Ontology Validator (三层归一第三层, G7)

对 Canonicalizer 输出做实体类型 / 关系合法性校验。
不阻断聚合, 输出 issues 供诊断与过滤。

三层归一 (中英统一解析):
  原始新闻 → GLiNER/LLM 抽取 → AliasResolver(loader) → Canonicalizer(Entity ID)
    → **OntologyValidator (本模块)** → Fact

校验规则:
  1. Entity ID 前缀 ↔ 类型一致性 (COMP_→Company, PERS_→Person ...)
  2. 关系类型白名单 (REL_ 前缀)
  3. 关系端点 ID 合法性

用法:
  from ontology_validator import validate_entities, validate_relationship
  ok, issues, valid = validate_entities(fact["entities"])
"""
import re

# Entity ID 前缀 ↔ 本体类型 (对应 knowledge_base Entity ID 规范)
ID_TYPE = {
    "CTRY": "Country", "COMP": "Company", "PERS": "Person", "ORG": "Organization",
    "LOC": "Location", "IND": "Industry", "ACT": "Action", "REL": "Relation",
    "EVT": "EventType", "MODEL": "AiModel", "TECH": "Technology", "LAW": "Legal",
    "ENT": "Other",  # 兜底 (未映射实体)
}

_PREFIX_RE = re.compile(r"^([A-Z][A-Z_]*)_")


def validate_entity(entity_id: str, entity_type: str = "", name: str = "") -> tuple:
    """校验单个实体: ID 前缀 ↔ 类型一致。返回 (valid, issues[])。"""
    issues = []
    eid = (entity_id or "").strip()
    if not eid:
        return False, ["空 entity_id"]
    m = _PREFIX_RE.match(eid)
    prefix = m.group(1) if m else ""
    expected = ID_TYPE.get(prefix)
    if expected is None:
        issues.append(f"未知 ID 前缀: {eid}")
    elif entity_type and entity_type not in ("", "Other", "Unknown") and entity_type != expected:
        issues.append(f"类型冲突: {eid} 期望 {expected} 实际 {entity_type}")
    return len(issues) == 0, issues


def validate_relationship(rel_type: str, from_id: str = "", to_id: str = "") -> tuple:
    """校验关系: 类型 REL_ 前缀 + 端点 ID 合法。返回 (valid, issues[])。"""
    issues = []
    if rel_type and not rel_type.startswith("REL_"):
        issues.append(f"关系类型非 REL_ 前缀: {rel_type}")
    for eid in (from_id, to_id):
        if eid:
            ok, iss = validate_entity(eid)
            if not ok:
                issues.extend(iss)
    return len(issues) == 0, issues


def validate_entities(entities: list) -> tuple:
    """批量校验 canonicalize 输出的 entities[]。返回 (valid, issues[], valid_count)。"""
    issues = []
    valid = 0
    for e in entities or []:
        ok, iss = validate_entity(e.get("id", ""), e.get("type", ""), e.get("name", ""))
        if ok:
            valid += 1
        else:
            issues.extend(iss)
    return (valid == len(entities or []), issues, valid)


def validate_fact_graph(fact: dict) -> dict:
    """校验 canonicalize 输出整体, 返回带 validation 的增强 dict (不修改原 dict)。"""
    ents = fact.get("entities") or []
    ok, issues, valid = validate_entities(ents)
    out = dict(fact)
    out["validation"] = {
        "ok": ok,
        "issues": issues,
        "valid_entities": valid,
        "total_entities": len(ents),
    }
    return out


if __name__ == "__main__":
    # 自测
    t = [("COMP_NVIDIA", "Company", True), ("COMP_NVIDIA", "Person", False),
         ("PERS_TRUMP", "Person", True), ("BOGUS_X", "Company", False),
         ("", "Company", False)]
    for eid, etype, expect in t:
        ok, iss = validate_entity(eid, etype)
        print(f"  {'✅' if ok == expect else '❌'} validate_entity({eid!r}, {etype!r}) → {ok} {iss}")
    ok, iss = validate_relationship("REL_INVESTOR", "COMP_NVIDIA", "PERS_TRUMP")
    print(f"  {'✅' if ok else '❌'} validate_relationship(REL_INVESTOR) → {ok} {iss}")
    ok, iss = validate_relationship("INVESTOR", "COMP_NVIDIA", "")
    print(f"  {'✅' if not ok else '❌'} validate_relationship(INVESTOR非REL) → {ok} {iss}")

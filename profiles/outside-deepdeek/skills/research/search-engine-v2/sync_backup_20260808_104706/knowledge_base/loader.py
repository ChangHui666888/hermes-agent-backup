"""knowledge_base/loader.py — 全球知识库加载器 + 别名→Entity ID 解析 (Knowledge Base V1)

读取 knowledge_base/*.yaml (9 本体 + entity_alias), 构建统一别名索引:
  名称/别名 (中英) → 稳定 Entity ID (CTRY_CHINA / COMP_NVIDIA / PERS_TRUMP ...)

API:
  get_kb() -> dict                         全量本体 (懒加载 + 线程安全)
  resolve(name) -> (entity_id, canonical, type) | None   别名/名称 → 稳定 ID
  entity_type(cid) -> str                  根据 ID 前缀推断类型 (CTRY→Country ...)
"""
import os
import re
import threading

try:
    import yaml
except ImportError:
    yaml = None

KB_DIR = os.path.dirname(os.path.abspath(__file__))

_FILES = [
    ("countries.yaml", "countries", "Country"),
    ("organizations.yaml", "organizations", "Organization"),
    ("companies.yaml", "companies", "Company"),
    ("people.yaml", "people", "Person"),
    ("locations.yaml", "locations", "Location"),
    ("industries.yaml", "industries", "Industry"),
    ("actions.yaml", "actions", "Action"),
    ("relations.yaml", "relations", "Relation"),
    ("event_types.yaml", "event_types", "EventType"),
]

# ID 前缀 → 类型 (与 canonicalizer._ID_PREFIX 一致)
_PREFIX_TYPE = {
    "CTRY": "Country", "COMP": "Company", "PERS": "Person", "ORG": "Organization",
    "LOC": "Location", "IND": "Industry", "ACT": "Action", "REL": "Relation",
    "EVT": "EventType", "MODEL": "Model", "TECH": "Technology", "LAW": "Law",
    "CUR": "Currency", "IDX": "Index", "ETF": "ETF", "CMD": "Commodity",
    "SHIP": "Ship", "AIR": "Aircraft", "SAT": "Satellite", "MISSILE": "Missile",
    "WPN": "Weapon", "PROD": "Product", "STORY": "Story", "ENT": "Entity",
}


def _load_yaml(fn: str) -> dict:
    if yaml is None:
        return {}
    p = os.path.join(KB_DIR, fn)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        return d
    except Exception:
        return {}


_kb = None
_lock = threading.RLock()  # RLock: _get_index 持锁内调 get_kb 不会死锁


def get_kb() -> dict:
    """懒加载全量本体。"""
    global _kb
    with _lock:
        if _kb is not None:
            return _kb
        kb = {"countries": {}, "organizations": {}, "companies": {}, "people": {},
              "locations": {}, "industries": {}, "actions": {}, "relations": {},
              "event_types": {}, "aliases": {}}
        for fn, key, _ in _FILES:
            d = _load_yaml(fn)
            kb[key] = d.get(key, {}) if isinstance(d, dict) else {}
        kb["aliases"] = (_load_yaml("entity_alias.yaml") or {}).get("aliases", {})
        _kb = kb
        return _kb


def _entry_type(cid: str, fallback: str) -> str:
    for pre, t in _PREFIX_TYPE.items():
        if cid.startswith(pre + "_"):
            return t
    return fallback


def _build_index(kb: dict) -> dict:
    """alias(小写) → (entity_id, canonical_name, type)

    优先级: entity_alias.yaml (curated, 含转喻/缩写) 先建 → 覆盖 section 自动条目。
    例如 'Washington' → ORG_US_GOVERNMENT (curated) 而非 LOC_WASHINGTON。
    """
    idx = {}

    def _add(cid: str, name_en: str, name_zh: str, aliases: list, etype: str):
        names = [n for n in (name_en, name_zh) if n] + (aliases or [])
        canon = name_en or name_zh or ""
        for n in names:
            key = n.strip().lower()
            if key and (key not in idx):
                idx[key] = (cid, canon, etype)

    # 1) entity_alias.yaml (curated) 优先
    cid_canon = {}
    for _key in ("countries", "companies", "people", "organizations", "locations"):
        for cid, meta in kb.get(_key, {}).items():
            nm = meta.get("name", {}) if isinstance(meta, dict) else {}
            cid_canon[cid] = (nm.get("en") or nm.get("zh") or "") or cid_canon.get(cid, "")
    for cid, meta in kb.get("aliases", {}).items():
        canon = meta.get("canonical", "") if isinstance(meta, dict) else ""
        canon = canon or cid_canon.get(cid, "")
        for al in (meta.get("aliases", []) if isinstance(meta, dict) else []) or []:
            key = al.strip().lower()
            if key and key not in idx:
                idx[key] = (cid, canon, _entry_type(cid, "Entity"))

    # 2) section 条目填 gap (curated 未覆盖的 canonical 名/别名)
    for key, etype in (("countries", "Country"), ("organizations", "Organization"),
                       ("companies", "Company"), ("people", "Person"),
                       ("locations", "Location"), ("industries", "Industry")):
        for cid, meta in kb.get(key, {}).items():
            nm = meta.get("name", {}) if isinstance(meta, dict) else {}
            _add(cid, nm.get("en", ""), nm.get("zh", ""), meta.get("aliases"), etype)

    return idx


_index = None


def _get_index() -> dict:
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = _build_index(get_kb())
    return _index


def resolve(name: str) -> tuple | None:
    """别名/名称 → (entity_id, canonical_name, type)。查不到返回 None。"""
    if not name:
        return None
    key = name.strip().lower()
    return _get_index().get(key)


def entity_id(name: str, etype: str = "Entity") -> str:
    """名称 → 稳定 Entity ID; KB 没有则按前缀规范生成 (兼容 aggregator _entity_name_to_id)。"""
    hit = resolve(name)
    if hit:
        return hit[0]
    clean = name.upper().replace(" ", "_").replace("-", "_").replace("'", "")
    clean = "".join(c for c in clean if c.isalnum() or c == "_")
    pre = {"Country": "CTRY", "Company": "COMP", "Person": "PERS",
           "Organization": "ORG", "Location": "LOC"}.get(etype, "ENT")
    return f"{pre}_{clean}" if clean else "ENT_UNKNOWN"


def entity_type(cid: str) -> str:
    return _entry_type(cid, "Entity")


def action_lookup(action_id: str) -> dict | None:
    kb = get_kb()
    return kb["actions"].get(action_id)


def relation_lookup(rel_id: str) -> dict | None:
    kb = get_kb()
    return kb["relations"].get(rel_id)


if __name__ == "__main__":
    kb = get_kb()
    total = sum(len(v) for k, v in kb.items() if isinstance(v, dict))
    print(f"知识库加载: {total} 实体/本体条目, 别名索引 {len(_get_index())} 条")
    for t in ("特朗普", "Trump", "中国", "China", "NVIDIA", "英伟达", "Beijing", "习近平", "黄仁勋"):
        print(f"  {t} → {resolve(t)}")

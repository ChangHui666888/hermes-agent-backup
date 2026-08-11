"""event_ab.py — A/B 事件两级聚合 (2026-08-10, ISS-20260810-012)

A事件(高精度): 宁拆勿错 — 同一 (subject_id, action_type, object_id) 才合并为一个 A 事件。
B事件(宽松):  实体行为脉络 — 同一 subject_id 的 A 事件归为一个 B 事件 (实体时间线)。

输入: facts[], 每条含 subject_id/subject_name/action_type/object_id/object_name/time。
输出: {"a_events": [{"id","subject_id","action_type","object_id","facts":[...]}],
       "b_events": [{"id","subject_id","a_event_ids":[...]}]}
"""


def cluster_a(facts: list) -> list:
    """A 事件: (subject_id, action_type, object_id) 精确合并 → 高精度, 宁拆勿错。"""
    groups = {}
    for f in facts:
        key = (f.get("subject_id") or "", f.get("action_type") or "OTHER", f.get("object_id") or "")
        groups.setdefault(key, []).append(f)
    a_events = []
    for i, (key, fs) in enumerate(groups.items(), 1):
        sid, act, oid = key
        a_events.append({
            "id": f"A-{i:03d}",
            "subject_id": sid, "action_type": act, "object_id": oid,
            "subject_name": fs[0].get("subject_name") or "",
            "object_name": fs[0].get("object_name") or "",
            "n_facts": len(fs), "facts": fs,
        })
    return a_events


def cluster_b(a_events: list) -> list:
    """B 事件: 同 subject_id 的 A 事件 → 实体行为脉络 (宽松聚合)。"""
    groups = {}
    for a in a_events:
        groups.setdefault(a["subject_id"], []).append(a["id"])
    b_events = []
    for i, (sid, ids) in enumerate(groups.items(), 1):
        b_events.append({"id": f"B-{i:03d}", "subject_id": sid, "a_event_ids": ids})
    return b_events


def aggregate_ab(facts: list) -> dict:
    a = cluster_a(facts)
    return {"a_events": a, "b_events": cluster_b(a)}

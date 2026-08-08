"""news_intel/event_normalizer.py — 事件归一 (v4.4.1)

定期把"同标题"的重复事件合并到最早事件, 根治聚合器非幂等造成的重复堆积:
  - 事件号保留 first_seen 最早的 (事件号稳定, 便于历史引用)
  - 被并入事件涉及的文章全部重新标记到最早事件 (news_content.event_id)
  - 合并 article_ids / evidence / source_chain / timeline / doc_refs / actors
    / related_entities / keywords (URL 或 ID 去重)
  - 删除被并入的重复事件行 (event_registry)

配合增量聚合 (只聚合未标记文章) 使用:
  - 增量聚合避免同一文章反复生成新事件 (预防)
  - 归一合并兜底跨轮/跨批的同故事分裂 (收敛)

返回 (kept_rows, deleted_event_ids) 供 Step 4.6 同步云端:
  - kept_rows  → POST /internal/events/batch   (upsert 更新云端)
  - deleted_event_ids → POST /internal/events/delete (删除云端重复)
"""
import json
from datetime import datetime

_JSON_FIELDS = ["article_ids", "doc_refs", "actors", "keywords",
                "related_entities", "evidence", "source_chain",
                "timeline", "llm_analysis"]


def _load_json(v):
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


def _dump_json(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def _norm_title(t):
    return " ".join((t or "").split()).lower()


def _dedupe_by(items, key):
    seen, out = set(), []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        k = key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _merge_events(evs: list) -> tuple:
    """同标题事件归并到最早。返回 (kept_row, merged_away_ids)。

    kept_row 为 registry 兼容行 (JSON 字段为字符串, 平铺列与表结构一致)。
    """
    evs = [e for e in evs if e]
    if len(evs) <= 1:
        return (evs[0] if evs else None), []

    def _fs(e):
        return e.get("first_seen") or "￿"  # NULL 排最后

    earliest = min(evs, key=lambda e: (str(_fs(e)), str(e.get("event_id") or "")))
    keep_id = earliest["event_id"]

    all_article_ids = list(_load_json(earliest.get("article_ids")) or [])
    all_evidence = list(_load_json(earliest.get("evidence")) or [])
    all_chain = list(_load_json(earliest.get("source_chain")) or [])
    all_timeline = list(_load_json(earliest.get("timeline")) or [])
    all_doc_refs = list(_load_json(earliest.get("doc_refs")) or [])
    all_actors = list(_load_json(earliest.get("actors")) or [])
    all_related = list(_load_json(earliest.get("related_entities")) or [])
    all_keywords = list(_load_json(earliest.get("keywords")) or [])
    max_confidence = earliest.get("confidence") or 0

    merged_away = []
    for e in evs:
        if e["event_id"] == keep_id:
            continue
        merged_away.append(e["event_id"])
        all_article_ids.extend(_load_json(e.get("article_ids")) or [])
        all_evidence.extend(_load_json(e.get("evidence")) or [])
        all_chain.extend(_load_json(e.get("source_chain")) or [])
        all_timeline.extend(_load_json(e.get("timeline")) or [])
        all_doc_refs.extend(_load_json(e.get("doc_refs")) or [])
        all_actors.extend(_load_json(e.get("actors")) or [])
        all_related.extend(_load_json(e.get("related_entities")) or [])
        all_keywords.extend(_load_json(e.get("keywords")) or [])
        max_confidence = max(max_confidence or 0, e.get("confidence") or 0)

    all_article_ids = list(dict.fromkeys(
        int(a) for a in all_article_ids if str(a).isdigit()))
    all_evidence = _dedupe_by(all_evidence, lambda x: x.get("url"))
    all_chain = _dedupe_by(all_chain, lambda x: x.get("source_id") or x.get("source_name"))
    all_timeline = _dedupe_by(all_timeline,
                              lambda x: x.get("url") or (str(x.get("time")) + str(x.get("update", ""))))
    all_doc_refs = _dedupe_by(all_doc_refs, lambda x: x.get("url"))
    all_actors = _dedupe_by(all_actors, lambda x: (x.get("entity"), x.get("role")))
    all_related = _dedupe_by(all_related, lambda x: x.get("entity_id") or x.get("name"))
    all_keywords = list(dict.fromkeys(k for k in all_keywords if k))

    def _ts(x):
        return x.get("time") or ""

    all_timeline.sort(key=_ts)
    all_chain.sort(key=_ts)

    src_names = list(dict.fromkeys(x.get("source_name") or ""
                                   for x in all_chain if x.get("source_name")))
    if not src_names and earliest.get("source_chain"):
        src_names = list(dict.fromkeys(x.get("source_name") or ""
                                       for x in all_chain)) or []
    source_count = len(src_names) if src_names else (earliest.get("source_count") or 0)

    kept = dict(earliest)
    kept["article_ids"] = _dump_json(all_article_ids)
    kept["article_count"] = len(all_article_ids)
    kept["evidence"] = _dump_json(all_evidence[:5])
    kept["source_chain"] = _dump_json(all_chain[:10])
    kept["timeline"] = _dump_json(all_timeline[:12])
    kept["doc_refs"] = _dump_json(all_doc_refs[:5])
    kept["actors"] = _dump_json(all_actors[:10])
    kept["related_entities"] = _dump_json(all_related[:20])
    kept["keywords"] = _dump_json(all_keywords)
    kept["source_count"] = source_count
    kept["confidence"] = max_confidence
    kept["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return kept, merged_away


def normalize_duplicate_events(db, groups_max: int = 200) -> tuple:
    """扫描 event_registry, 同标题归并。返回 (kept_rows, deleted_event_ids)。

    kept_rows 已是最新合并后的 registry 行 (可直接走 cloud batch upsert 推送格式)。
    """
    rows = db.execute("SELECT * FROM event_registry").fetchall()
    by_title = {}
    for r in rows:
        title = _norm_title(r["title"])
        if not title:
            continue
        by_title.setdefault(title, []).append(dict(r))

    kept_rows, deleted_ids = [], []
    for title, evs in list(by_title.items()):
        if len(evs) < 2:
            continue
        if len(kept_rows) >= groups_max:
            break
        kept, merged_away = _merge_events(evs)
        if not kept or not merged_away:
            continue

        # 1) 覆盖写最早事件行 (合并后的文章/证据)
        db.execute("""
            UPDATE event_registry SET
                summary=?, event_type=?, stage=?, confidence=?, coherence=?,
                subject_name=?, subject_type=?, action_type=?, action_detail=?,
                object_name=?, object_type=?, location_country=?, primary_source_id=?,
                source_count=?, article_count=?, article_ids=?, doc_refs=?, actors=?,
                keywords=?, related_entities=?, evidence=?, source_chain=?, timeline=?,
                llm_analysis=?, last_updated=?
            WHERE event_id=?
        """, (
            kept.get("summary"), kept.get("event_type"), kept.get("stage", "active"),
            kept.get("confidence", 0), kept.get("coherence", 0),
            kept.get("subject_name"), kept.get("subject_type"), kept.get("action_type"),
            kept.get("action_detail"), kept.get("object_name"), kept.get("object_type"),
            kept.get("location_country"), kept.get("primary_source_id"),
            kept.get("source_count", 0), kept.get("article_count", 0),
            kept.get("article_ids"), kept.get("doc_refs"), kept.get("actors"),
            kept.get("keywords"), kept.get("related_entities"), kept.get("evidence"),
            kept.get("source_chain"), kept.get("timeline"), kept.get("llm_analysis"),
            kept.get("last_updated"), kept["event_id"],
        ))

        # 2) 删除被并入的重复行
        for eid in merged_away:
            db.execute("DELETE FROM event_registry WHERE event_id=?", (eid,))

        # 3) 重新标记被并入事件的文章归属 → 最早事件
        away_ids = []
        for e in evs:
            if e["event_id"] in merged_away:
                away_ids.extend(_load_json(e.get("article_ids")) or [])
        ids = [int(a) for a in away_ids if str(a).isdigit()]
        if ids:
            ph = ",".join("?" * len(ids))
            db.execute(
                f"UPDATE news_content SET event_id=? WHERE id IN ({ph})",
                [kept["event_id"]] + ids,
            )

        kept_rows.append(kept)
        deleted_ids.extend(merged_away)

    db.commit()
    return kept_rows, deleted_ids

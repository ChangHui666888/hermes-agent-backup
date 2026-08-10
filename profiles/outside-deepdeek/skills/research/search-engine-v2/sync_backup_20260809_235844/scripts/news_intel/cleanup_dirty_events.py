"""news_intel/cleanup_dirty_events.py — Phase 3 一次性清理脚本 (脏属性根治)

背景: score_entities 旧版是子串匹配 (`name in text`), 导致
  - 'Xi' 误标所有 ML 论文 (希腊字母 ξ/xi / fixing/proximity 里的 'xi')
  - 'US'/'BP'/'UK' 等短名误标任意含该子串的文本
  从而事件 subject/action 脏, 且无关论文被合并成同一事件。

本脚本 (配合修复后的 scorer.py / aggregator.py):
  1) 用修复后的 score_entities 重算所有 news_intelligence.entities (消除子串误标)
  2) 重算 event_registry 事件的 subject/action/event_type
     (主体: 标题出现的实体优先 + 出现次数多数决; action/type: 文章多数决)
  3) 删除"虚假合并"事件 (全部成员为 arXiv 且无真实主体), 并解绑其文章 (event_id=NULL)
  4) 推送云端: upsert 保留事件 + delete 删除虚假事件

用法: python news_intel/cleanup_dirty_events.py [--no-cloud]
  --no-cloud  只改本地, 不同步云端
"""
import sys
import os
import json
import sqlite3
import argparse
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))  # scripts/
sys.path.insert(0, SCRIPT_DIR)                   # news_intel/

from news_intel.scorer import score_entities
from news_intel.aggregator import (_name_in_text, _detect_action, _classify_topics,
                                   _subject_is_prominent)
from news_intel.db import DB_PATH


def _json_load(v):
    if not v:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v)
    except Exception:
        return []


def _strict_majority(vals, fallback=""):
    """严格多数决 (>50%) 才返回该值, 否则回退。"""
    c = Counter(vals)
    if not c:
        return fallback
    top, cnt = c.most_common(1)[0]
    return top if cnt * 2 > len(vals) else fallback


def re_score_entities(db) -> int:
    """用修复后的 score_entities 重算全部 news_intelligence.entities。返回更新行数。"""
    rows = db.execute("""
        SELECT ni.id, rr.title, rr.description
        FROM news_intelligence ni JOIN rss_raw rr ON ni.raw_id = rr.id
    """).fetchall()
    n = 0
    for r in rows:
        _, ents = score_entities(r["title"] or "", r["description"] or "")
        db.execute("UPDATE news_intelligence SET entities=? WHERE id=?",
                   (json.dumps(ents, ensure_ascii=False), r["id"]))
        n += 1
    db.commit()
    return n


def load_event_articles(db, event_id: str, article_ids: list) -> list:
    """加载事件成员文章的标题/描述/实体 (news_intelligence.entities 已重算)。"""
    if not article_ids:
        return []
    ph = ",".join("?" * len(article_ids))
    rows = db.execute(f"""
        SELECT nc.id, rr.title, rr.description, ni.entities
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE nc.id IN ({ph})
    """, article_ids).fetchall()
    out = []
    for r in rows:
        ents = {}
        if r["entities"]:
            try:
                ents = json.loads(r["entities"])
            except Exception:
                ents = {}
        out.append({"id": r["id"], "title": r["title"] or "", "description": r["description"] or "",
                    "source": _src_of(db, r["id"]), "entities": ents})
    return out


def _src_of(db, nc_id: int) -> str:
    row = db.execute("""
        SELECT rr.source_name FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id WHERE nc.id=?
    """, (nc_id,)).fetchone()
    return row["source_name"] if row else ""


def recompute_attrs(articles: list, cur_subject: str = "", cur_action: str = "",
                    cur_type: str = "") -> dict:
    """事件属性校准 (保留真实主体, 清除垃圾主体, 补算回退值)。

    - subject: 保留现有值, 除非它没通过"事件级主体门"
      (主体须出现在事件代表标题 或 ≥2 成员文章标题) → 否则清空
      (Xi/BP/Apple 等子串误标或陈旧实体不会在标题出现, 被清除;
       SpaceX/Chevron 等真实主体在标题出现, 被保留)
    - action/type: 当前为回退值 (OTHER/General) 时才按文章多数决补算, 其余保留
    """
    if not articles:
        return {"subject": cur_subject, "action": cur_action or "OTHER",
                "event_type": cur_type or "General"}
    best_title = max((a.get("title") or "" for a in articles), key=len, default="")

    subj = cur_subject or ""
    if subj and not _subject_is_prominent(
            subj, best_title, [a.get("title") or "" for a in articles]):
        subj = ""

    action = cur_action or "OTHER"
    etype = cur_type or "General"
    if action == "OTHER":
        acts = [_detect_action((a.get("title") or "") + " " + (a.get("description") or ""))[0]
                for a in articles]
        action = _strict_majority(acts, "OTHER")
    if etype in ("General", ""):
        tops = [_classify_topics((a.get("title") or "") + " " + (a.get("description") or ""))[0]
                for a in articles]
        etype = _strict_majority(tops, "General")
    return {"subject": subj, "action": action, "event_type": etype}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cloud", action="store_true", help="只改本地, 不同步云端")
    args = ap.parse_args()

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    print("[1/4] 重算 news_intelligence.entities ...")
    n = re_score_entities(db)
    print(f"  updated {n} article entity rows")

    events = db.execute("SELECT * FROM event_registry").fetchall()
    print(f"[2/4] 重算 {len(events)} 个事件属性 ...")
    changed_events, bogus_events = [], []
    for ev in events:
        aids = [int(a) for a in _json_load(ev["article_ids"]) if str(a).isdigit()]
        arts = load_event_articles(db, ev["event_id"], aids)
        attrs = recompute_attrs(arts, ev["subject_name"] or "", ev["action_type"] or "",
                                ev["event_type"] or "")
        all_arxiv = bool(arts) and all((a["source"] or "").startswith("arXiv") for a in arts)

        # 虚假合并: 全部成员为 arXiv 且无真实主体 (旧 Xi 误标把无关论文并到一起)
        if all_arxiv and not attrs["subject"]:
            bogus_events.append(ev["event_id"])
            continue

        new_subj = attrs["subject"]
        new_action = attrs["action"]
        new_type = attrs["event_type"]
        if (new_subj != (ev["subject_name"] or "")
                or new_action != (ev["action_type"] or "")
                or new_type != (ev["event_type"] or "")):
            db.execute("""
                UPDATE event_registry SET subject_name=?, subject_type=?,
                    action_type=?, event_type=?, last_updated=datetime('now','localtime')
                WHERE event_id=?
            """, (new_subj, "Other", new_action, new_type, ev["event_id"]))
            changed_events.append(ev["event_id"])
            print(f"  {ev['event_id']}: subj {ev['subject_name'] or '(空)'}→{new_subj or '(空)'} | "
                  f"act {ev['action_type']}→{new_action} | type {ev['event_type']}→{new_type}")

    db.commit()

    print(f"[3/4] 删除 {len(bogus_events)} 个虚假 ML 合并事件 + 解绑文章 ...")
    for eid in bogus_events:
        ev = db.execute("SELECT * FROM event_registry WHERE event_id=?", (eid,)).fetchone()
        if ev:
            for a in _json_load(ev["article_ids"]):
                db.execute("UPDATE news_content SET event_id=NULL WHERE id=? AND event_id=?", (a, eid))
            db.execute("DELETE FROM event_registry WHERE event_id=?", (eid,))
    db.commit()
    print(f"  本地: 保留事件更新 {len(changed_events)}, 删除虚假事件 {len(bogus_events)}")
    print("  本地 event_registry:", db.execute("SELECT COUNT(*) FROM event_registry").fetchone()[0],
          "条 | news_content 标记:", db.execute(
              "SELECT COUNT(*) FROM news_content WHERE event_id IS NOT NULL AND event_id!=''").fetchone()[0], "条")

    if not args.no_cloud:
        print("[4/4] 推送云端 ...")
        try:
            from config.env import CLOUD_API, INTERNAL_TOKEN
        except Exception:
            CLOUD_API = "http://100.107.117.23"
            INTERNAL_TOKEN = "v8-pipeline-token-2026-xK9mP2sR7wQ"
        TOKEN = os.environ.get("NEWS_API_TOKEN") or INTERNAL_TOKEN
        headers = {"X-Internal-Token": TOKEN}

        def to_push(evid):
            r = db.execute("SELECT * FROM event_registry WHERE event_id=?", (evid,)).fetchone()
            if not r:
                return None
            ev = dict(r)
            for f in ["article_ids", "doc_refs", "actors", "keywords", "related_entities",
                      "evidence", "source_chain", "timeline", "llm_analysis"]:
                if isinstance(ev.get(f), str):
                    try:
                        ev[f] = json.loads(ev[f])
                    except Exception:
                        pass
            return {
                "event_id": ev.get("event_id"), "title": ev.get("title", ""), "summary": ev.get("summary"),
                "event_type": ev.get("event_type"), "stage": ev.get("stage", "active"),
                "confidence": ev.get("confidence", 0), "coherence": ev.get("coherence", 0),
                "subject": {"name": ev.get("subject_name", ""), "type": ev.get("subject_type", "Other")},
                "action": {"type": ev.get("action_type", "OTHER"), "detail": ev.get("action_detail")},
                "object": {"name": ev.get("object_name", ""), "type": ev.get("object_type", "Other")},
                "location": {"country": ev.get("location_country")},
                "source": {"primary_source_id": ev.get("primary_source_id"),
                           "source_count": ev.get("source_count", 0)},
                "article_count": ev.get("article_count", 0), "article_ids": ev.get("article_ids", []),
                "doc_refs": ev.get("doc_refs", []), "actors": ev.get("actors", []),
                "keywords": ev.get("keywords", []), "related_entities": ev.get("related_entities", []),
                "evidence": ev.get("evidence", []), "source_chain": ev.get("source_chain", []),
                "timeline": ev.get("timeline", []), "llm_analysis": ev.get("llm_analysis"),
                "first_seen": ev.get("first_seen"), "last_updated": ev.get("last_updated"),
            }

        payload = [to_push(e) for e in changed_events]
        payload = [p for p in payload if p]
        if payload:
            for i in range(0, len(payload), 50):
                chunk = payload[i:i + 50]
                r = httpx.post(f"{CLOUD_API}/internal/events/batch", json=chunk, headers=headers, timeout=60)
                res = r.json()
                print(f"  upsert chunk: ok={res.get('ok')} fail={res.get('fail')}")
        if bogus_events:
            r = httpx.post(f"{CLOUD_API}/internal/events/delete", json=bogus_events,
                           headers=headers, timeout=60)
            print(f"  delete bogus: HTTP {r.status_code} {r.text[:120]}")

    db.close()
    print("DONE")


if __name__ == "__main__":
    import httpx  # noqa
    main()

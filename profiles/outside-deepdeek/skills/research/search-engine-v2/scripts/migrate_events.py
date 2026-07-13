#!/usr/bin/env python3
"""migrate_events.py — SQLite event_registry → PostgreSQL events table.

One-shot migration. Reads from local SQLite, inserts into PG via HTTP.
Safe to re-run (ON CONFLICT DO UPDATE).
"""

import sqlite3, os, sys, json
import httpx

# Paths
SQLITE_DB = os.path.expanduser(
    "~/AppData/Local/hermes/profiles/outside-deepdeek/"
    "skills/research/search-engine-v2/scripts/news_intel/news_intel.db"
)
API = os.environ.get("NEWS_API_BASE", "http://100.107.117.23")
TOKEN = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")


def main():
    if not os.path.exists(SQLITE_DB):
        print(f"SQLite not found: {SQLITE_DB}")
        sys.exit(1)

    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM event_registry ORDER BY first_seen DESC").fetchall()
    print(f"SQLite: {len(rows)} events")

    events = []
    for r in rows:
        ev = dict(r)
        # Parse JSON fields
        for field in ["article_ids", "doc_refs", "actors", "keywords",
                       "related_entities", "evidence", "source_chain",
                       "timeline", "llm_analysis"]:
            if isinstance(ev.get(field), str):
                try: ev[field] = json.loads(ev[field])
                except: pass

        events.append({
            "event_id": ev.get("event_id"),
            "title": ev.get("title", ""),
            "summary": ev.get("summary", ""),
            "event_type": ev.get("event_type"),
            "stage": ev.get("stage", "active"),
            "confidence": ev.get("confidence", 0.0),
            "coherence": ev.get("coherence", 0.0),
            "subject": {"name": ev.get("subject_name", ""), "type": ev.get("subject_type", "Other")},
            "action": {"type": ev.get("action_type", "OTHER"), "detail": ev.get("action_detail")},
            "object": {"name": ev.get("object_name", ""), "type": ev.get("object_type", "Other")},
            "location": {"country": ev.get("location_country")},
            "source": {"primary_source_id": ev.get("primary_source_id"), "source_count": ev.get("source_count", 0)},
            "article_count": ev.get("article_count", 0),
            "article_ids": ev.get("article_ids", []),
            "doc_refs": ev.get("doc_refs", []),
            "actors": ev.get("actors", []),
            "keywords": ev.get("keywords", []),
            "related_entities": ev.get("related_entities", []),
            "evidence": ev.get("evidence", []),
            "source_chain": ev.get("source_chain", []),
            "timeline": ev.get("timeline", []),
            "llm_analysis": ev.get("llm_analysis"),
            "first_seen": ev.get("first_seen"),
            "last_updated": ev.get("last_updated"),
        })

    conn.close()

    # Push to PG via HTTP
    resp = httpx.post(
        f"{API}/internal/events/batch",
        json=events,
        headers={"X-Internal-Token": TOKEN},
        timeout=60,
    )
    print(f"PG push: {resp.status_code} {resp.json()}")

    # Verify
    resp2 = httpx.get(f"{API}/api/v1/dashboard")
    if resp2.status_code == 200:
        m = resp2.json()["metrics"]
        print(f"PG events: {m['active_events']}")
    else:
        print(f"Verify failed: {resp2.status_code}")


if __name__ == "__main__":
    main()

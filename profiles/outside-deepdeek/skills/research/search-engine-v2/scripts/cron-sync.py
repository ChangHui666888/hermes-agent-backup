#!/usr/bin/env python3
"""cron-sync.py — Pipeline aggregation + HTTP push to V8 cloud backend.

V8 version: No SFTP. No SSH. No paramiko.
Uses HTTP POST /internal/events/batch + /internal/news/batch.

Called by Hermes cron every 30 minutes.
"""

import sys, os, time, json
import httpx

# Paths
PROFILE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(PROFILE, "skills", "research", "search-engine-v2", "scripts")
sys.path.insert(0, PIPELINE)

API_BASE = os.environ.get("NEWS_API_BASE", "http://100.107.117.23")
INTERNAL_TOKEN = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")

print(f"[cron] Pipeline: {PIPELINE}")
print(f"[cron] API: {API_BASE}")

# ── 1. Aggregate events ──────────────────────────────────────
try:
    from news_intel.db import init_db
    from news_intel.aggregator import aggregate_events
    init_db()
    from news_intel.db import get_db
    db = get_db()
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = db.execute("""
        SELECT nc.id, rr.title, nc.summary_cn, rr.description,
               ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE ni.tier IN ('A','B')
        ORDER BY nc.id DESC LIMIT 100
    """).fetchall()
    events = aggregate_events(rows, window_hours=24)
    print(f"[cron] Aggregated {len(events)} events")
    db.close()
except Exception as e:
    print(f"[cron] Aggregation: {e}")
    events = []

# ── 2. Push events to cloud via HTTP ──────────────────────────
if events:
    try:
        body = []
        for ev in events:
            item = {
                "event_id": ev.get("event_id"),
                "title": ev.get("title", ""),
                "summary": ev.get("summary", ""),
                "event_type": ev.get("event_type"),
                "stage": ev.get("stage", "active"),
                "confidence": ev.get("confidence", 0.0),
                "coherence": ev.get("coherence", 0.0),
                "subject": ev.get("subject", {}),
                "action": ev.get("action", {}),
                "object": ev.get("object", {}),
                "location": ev.get("location", {}),
                "source": ev.get("source", {}),
                "actors": ev.get("actors", []),
                "keywords": ev.get("keywords", []),
                "related_entities": ev.get("related_entities", []),
                "article_count": ev.get("article_count", 0),
                "article_ids": ev.get("article_ids", []),
                "doc_refs": ev.get("doc_refs", []),
                "evidence": ev.get("evidence", []),
                "source_chain": ev.get("source_chain", []),
                "timeline": ev.get("timeline", []),
                "llm_analysis": ev.get("llm_analysis"),
                "first_seen": ev.get("first_seen"),
                "last_updated": ev.get("last_updated"),
            }
            body.append({k: v for k, v in item.items() if v is not None})

        resp = httpx.post(
            f"{API_BASE}/internal/events/batch",
            json=body,
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            timeout=30,
        )
        print(f"[cron] Events push: {resp.status_code} {resp.json()}")
    except Exception as e:
        print(f"[cron] Events push failed: {e}")

print(f"[cron] Done at {time.strftime('%H:%M:%S')}")

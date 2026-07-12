"""pusher.py v4.4 - Hermes -> Cloud PostgreSQL push (Articles + Events)

Two push modes:
  push_batch(articles)     - article-level (existing, unchanged)
  push_events(events)      - event-level (new v4.4, Event Dossier -> cloud DB)
"""

import json
import os
import logging

import httpx

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("NEWS_API_BASE", "http://localhost:8000")
INTERNAL_TOKEN = os.environ.get("NEWS_API_TOKEN", "hermes-pipeline-secret-2026")


# ---- Article Push (unchanged) ------------------------------------

def push_batch(articles: list[dict], api_base: str = None) -> dict:
    base = api_base or API_BASE
    if not articles:
        return {"ok": 0, "fail": 0}

    body = []
    for a in articles:
        s = a.get("structured", {})
        sc = a.get("scores", {})
        item = {
            "url": a.get("url", ""),
            "title": s.get("headline") or a.get("title", ""),
            "content_md": a.get("content", ""),
            "published_at": s.get("published_at"),
            "source_name": a.get("source_name") or a.get("domain", ""),
            "source_domain": a.get("domain", ""),
            "category": sc.get("categories", [None])[0] if "categories" in sc else None,
            "tags": s.get("tags") or sc.get("categories", []),
            "entities": sc.get("entities") or s.get("entities", {}),
            "score_total": sc.get("total", 0) if isinstance(sc, dict) else 0,
            "score_breakdown": sc if isinstance(sc, dict) else {},
            "tier": sc.get("tier") if isinstance(sc, dict) else None,
            "analysis": a.get("analysis", {}),
            "summary_cn": s.get("summary_cn", ""),
            "summary": s.get("summary", ""),
            "key_points": s.get("key_points", []),
            "extraction_method": s.get("method") or s.get("_extraction_method"),
            "fetch_strategy": a.get("strategy_used"),
            "fetch_cost": a.get("total_cost", 0),
        }
        body.append({k: v for k, v in item.items() if v is not None})

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base}/internal/news/batch",
                json=body,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
            if resp.status_code == 200:
                result = resp.json()
                return {"ok": result.get("ok", len(body)), "fail": result.get("fail", 0)}
            logger.warning(f"[pusher] article batch {resp.status_code}: {resp.text[:100]}")
            return {"ok": 0, "fail": len(body)}
    except Exception as e:
        logger.warning(f"[pusher] article batch error: {e}")
        return {"ok": 0, "fail": len(body)}


def push_article(article: dict, api_base: str = None, token: str = None) -> bool:
    result = push_batch([article], api_base)
    return result["ok"] > 0


# ---- Event Push (new v4.4) ---------------------------------------

def push_events(events: list[dict], api_base: str = None) -> dict:
    """Push Event Dossiers to cloud PostgreSQL via /internal/events/batch.

    Each event is a full v4.4 Event Object with:
      event_id, title, summary, SAO, source, actors, evidence,
      source_chain, timeline, confidence, stage, etc.

    Returns {"ok": N, "fail": N}.
    """
    base = api_base or API_BASE
    if not events:
        return {"ok": 0, "fail": 0}

    body = []
    for ev in events:
        item = _event_to_push_format(ev)
        body.append({k: v for k, v in item.items() if v is not None})

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base}/internal/events/batch",
                json=body,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
            if resp.status_code == 200:
                result = resp.json()
                return {"ok": result.get("ok", len(body)), "fail": result.get("fail", 0)}
            logger.warning(f"[pusher] event batch {resp.status_code}: {resp.text[:100]}")
            return {"ok": 0, "fail": len(body)}
    except Exception as e:
        logger.warning(f"[pusher] event batch error: {e}")
        return {"ok": 0, "fail": len(body)}


def push_event(event: dict, api_base: str = None) -> bool:
    """Push a single event dossier."""
    result = push_events([event], api_base)
    return result["ok"] > 0


def push_from_registry(stage: str = None, limit: int = 50,
                       api_base: str = None) -> dict:
    """Read events from local event_registry and push to cloud.

    Args:
        stage: Filter by lifecycle stage (active, developing, breaking, etc.)
        limit: Max events to push
        api_base: Cloud API URL

    Returns {'ok': N, 'fail': N}
    """
    try:
        from news_intel.db import init_db, get_db, list_events
        init_db()
        db = get_db()
        events = list_events(stage=stage, limit=limit, db=db)
        db.close()
        if not events:
            return {"ok": 0, "fail": 0}
        return push_events(events, api_base)
    except Exception as e:
        logger.warning(f"[pusher] push_from_registry error: {e}")
        return {"ok": 0, "fail": 0}


def _event_to_push_format(ev: dict) -> dict:
    """Convert v4.4 Event Object to POST body format."""
    return {
        "event_id": ev.get("event_id"),
        "title": ev.get("title", ""),
        "summary": ev.get("summary", ""),
        "event_type": ev.get("event_type"),
        "stage": ev.get("stage", "active"),
        "confidence": ev.get("confidence", 0.0),
        "coherence": ev.get("coherence", 0.0),

        # SAO
        "subject": json.dumps(ev.get("subject", {}), ensure_ascii=False),
        "action": json.dumps(ev.get("action", {}), ensure_ascii=False),
        "object": json.dumps(ev.get("object", {}), ensure_ascii=False),

        # Location
        "location_country": ev.get("location", {}).get("country") if isinstance(ev.get("location"), dict) else None,

        # Source
        "primary_source": ev.get("source", {}).get("primary_source") if isinstance(ev.get("source"), dict) else None,
        "primary_source_id": ev.get("source", {}).get("primary_source_id") if isinstance(ev.get("source"), dict) else None,
        "source_authority": ev.get("source", {}).get("authority") if isinstance(ev.get("source"), dict) else 0,
        "source_count": ev.get("source", {}).get("source_count") if isinstance(ev.get("source"), dict) else 0,
        "sources": json.dumps(ev.get("source", {}).get("sources", []), ensure_ascii=False) if isinstance(ev.get("source"), dict) else None,

        # Articles
        "article_count": ev.get("article_count", 0),
        "article_ids": json.dumps(ev.get("article_ids", []), ensure_ascii=False),
        "doc_refs": json.dumps(ev.get("doc_refs", []), ensure_ascii=False),

        # Actors & Entities
        "actors": json.dumps(ev.get("actors", []), ensure_ascii=False),
        "keywords": json.dumps(ev.get("keywords", []), ensure_ascii=False),
        "related_entities": json.dumps(ev.get("related_entities", []), ensure_ascii=False),

        # Evidence & Timeline (new v4.4)
        "evidence": json.dumps(ev.get("evidence", []), ensure_ascii=False),
        "source_chain": json.dumps(ev.get("source_chain", []), ensure_ascii=False),
        "timeline": json.dumps(ev.get("timeline", []), ensure_ascii=False),

        # Analysis
        "llm_analysis": json.dumps(ev.get("llm_analysis", {}), ensure_ascii=False) if ev.get("llm_analysis") else None,

        # Timing
        "event_time": ev.get("event_time"),
        "first_seen": ev.get("first_seen"),
        "last_updated": ev.get("last_updated"),

        # Meta
        "extraction_method": ev.get("extraction_method", "v4.4-saeo"),
    }

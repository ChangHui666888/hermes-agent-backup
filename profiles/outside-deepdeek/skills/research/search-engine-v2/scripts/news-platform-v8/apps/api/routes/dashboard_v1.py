"""routes/dashboard_v1.py — Sentinel Dashboard (PG version)."""

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import Event, Source

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard():
    db = next(get_db())
    try:
        metrics = {
            "active_events": db.query(Event).filter(Event.stage.in_(("active", "developing", "breaking"))).count(),
            "critical_events": 0,
            "today_updates": 0,
            "sources": db.query(Source).count(),
        }
        hot = db.query(Event).order_by(Event.confidence.desc()).limit(6).all()
        hot_events = [_event_to_dict(e) for e in hot]
        map_events = [
            {"event_id": e.event_id, "title": e.title, "country": e.location_country,
             "impact_level": e.event_type, "confidence": e.confidence or 0.0}
            for e in db.query(Event).filter(Event.location_country.isnot(None), Event.location_country != "").order_by(Event.confidence.desc()).limit(20).all()
        ]
        return {"metrics": metrics, "hot_events": hot_events, "map_events": map_events}
    finally:
        db.close()


def _event_to_dict(e: Event) -> dict:
    return {
        "event_id": e.event_id, "title": e.title, "summary": e.summary,
        "event_type": e.event_type, "stage": e.stage, "confidence": e.confidence or 0.0,
        "coherence": e.coherence or 0.0,
        "subject": {"entity_id": None, "name": e.subject_name or "", "type": e.subject_type or "Other"},
        "action": {"type": e.action_type or "OTHER", "detail": e.action_detail},
        "object": {"entity_id": None, "name": e.object_name or "", "type": e.object_type or "Other"},
        "location": {"country": e.location_country, "region": None},
        "source": {"primary_source": e.primary_source_id or "", "primary_source_id": e.primary_source_id,
                    "authority": 0, "source_count": e.source_count or 0, "sources": []},
        "actors": e.actors or [], "keywords": e.keywords or [],
        "related_entities": e.related_entities or [], "article_count": e.article_count or 0,
        "first_seen": str(e.first_seen) if e.first_seen else None,
        "last_updated": str(e.last_updated) if e.last_updated else None,
        "evidence": e.evidence or [], "source_chain": e.source_chain or [],
        "timeline": e.timeline or [], "llm_analysis": e.llm_analysis,
    }

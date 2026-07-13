"""routes/search_v1.py — Full-text search."""

from fastapi import APIRouter, Query
from apps.api.database import get_db
from apps.api.models import Event

router = APIRouter(tags=["search"])


@router.get("/search")
def search_events(q: str = Query(..., min_length=2)):
    db = next(get_db())
    try:
        pattern = f"%{q}%"
        rows = db.query(Event).filter(
            (Event.title.ilike(pattern)) | (Event.summary.ilike(pattern))
        ).order_by(Event.confidence.desc()).limit(20).all()
        return {"query": q, "events": [{
            "event_id": e.event_id, "title": e.title, "event_type": e.event_type,
            "stage": e.stage, "confidence": e.confidence or 0.0,
            "location_country": e.location_country, "subject_name": e.subject_name,
            "action_type": e.action_type, "object_name": e.object_name,
            "source_count": e.source_count or 0, "article_count": e.article_count or 0,
            "last_updated": str(e.last_updated) if e.last_updated else None,
        } for e in rows]}
    finally:
        db.close()

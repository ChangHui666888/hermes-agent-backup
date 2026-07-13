"""routes/events_v1.py — Event list + detail (PG version)."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import Event
from apps.api.routes.dashboard_v1 import _event_to_dict

router = APIRouter(tags=["events"])


@router.get("/events")
def list_events(
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    event_type: str = Query(None), location_country: str = Query(None), stage: str = Query(None),
):
    db = next(get_db())
    try:
        q = db.query(Event)
        if event_type: q = q.filter(Event.event_type == event_type)
        if location_country: q = q.filter(Event.location_country == location_country)
        if stage: q = q.filter(Event.stage == stage)
        total = q.count()
        items = q.order_by(Event.first_seen.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "total": total, "page": page, "limit": limit,
            "items": [{"event_id": e.event_id, "title": e.title, "event_type": e.event_type,
                        "stage": e.stage, "confidence": e.confidence or 0.0,
                        "location_country": e.location_country, "subject_name": e.subject_name,
                        "action_type": e.action_type, "object_name": e.object_name,
                        "source_count": e.source_count or 0, "article_count": e.article_count or 0,
                        "last_updated": str(e.last_updated) if e.last_updated else None}
                       for e in items],
        }
    finally:
        db.close()


@router.get("/events/{event_id}")
def get_event(event_id: str):
    db = next(get_db())
    try:
        e = db.query(Event).filter(Event.event_id == event_id).first()
        if not e: raise HTTPException(status_code=404)
        return _event_to_dict(e)
    finally:
        db.close()

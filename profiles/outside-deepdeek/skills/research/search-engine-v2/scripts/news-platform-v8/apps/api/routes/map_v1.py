"""routes/map_v1.py — Geographic event markers."""

from fastapi import APIRouter
from apps.api.database import get_db
from apps.api.models import Event

router = APIRouter(tags=["map"])


@router.get("/map/events")
def get_map_events():
    db = next(get_db())
    try:
        rows = db.query(Event).filter(
            Event.location_country.isnot(None), Event.location_country != ""
        ).order_by(Event.confidence.desc()).limit(50).all()
        return {"events": [{
            "event_id": e.event_id, "title": e.title, "country": e.location_country,
            "impact_level": e.event_type, "confidence": e.confidence or 0.0,
        } for e in rows]}
    finally:
        db.close()

"""GET /api/v1/map/events — geographic event markers."""

from fastapi import APIRouter, HTTPException

from db import get_db
from models.schemas import MapEvent, MapEventsResponse

router = APIRouter(tags=["map"])


@router.get("/map/events", response_model=MapEventsResponse)
def get_map_events():
    try:
        db = get_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    rows = db.execute(
        "SELECT DISTINCT event_id, title, location_country, event_type, confidence "
        "FROM event_registry WHERE location_country IS NOT NULL AND location_country != '' "
        "ORDER BY confidence DESC LIMIT 50"
    ).fetchall()

    events = [
        MapEvent(
            event_id=r["event_id"],
            title=r["title"] or "",
            country=r["location_country"],
            impact_level=r["event_type"],
            confidence=r["confidence"] or 0.0,
        )
        for r in rows
    ]

    db.close()
    return MapEventsResponse(events=events)

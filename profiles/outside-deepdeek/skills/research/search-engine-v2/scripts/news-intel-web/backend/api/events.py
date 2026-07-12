"""GET /api/v1/events, GET /api/v1/events/{event_id}."""

from fastapi import APIRouter, HTTPException, Query

from db import get_db, row_to_dict
from models.schemas import EventListResponse, EventListItem, EventDossier

router = APIRouter(tags=["events"])


@router.get("/events", response_model=EventListResponse)
def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    event_type: str = Query(None),
    location_country: str = Query(None),
    stage: str = Query(None),
):
    try:
        db = get_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    where = []
    params = []
    if event_type:
        where.append("event_type=?")
        params.append(event_type)
    if location_country:
        where.append("location_country=?")
        params.append(location_country)
    if stage:
        where.append("stage=?")
        params.append(stage)
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(f"SELECT COUNT(*) FROM event_registry {clause}", params).fetchone()[0]

    offset = (page - 1) * limit
    rows = db.execute(
        f"SELECT * FROM event_registry {clause} ORDER BY first_seen DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    items = [
        EventListItem(
            event_id=r["event_id"],
            title=r["title"] or "",
            event_type=r["event_type"] or "Other",
            stage=r["stage"] or "active",
            confidence=r["confidence"] or 0.0,
            location_country=r["location_country"],
            subject_name=r["subject_name"],
            action_type=r["action_type"],
            object_name=r["object_name"],
            source_count=r["source_count"] or 0,
            article_count=r["article_count"] or 0,
            last_updated=r["last_updated"],
        )
        for r in rows
    ]

    db.close()
    return EventListResponse(total=total, page=page, limit=limit, items=items)


@router.get("/events/{event_id}", response_model=EventDossier)
def get_event(event_id: str):
    try:
        db = get_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    row = db.execute("SELECT * FROM event_registry WHERE event_id=?", (event_id,)).fetchone()
    if row is None:
        db.close()
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    from api.dashboard import _build_dossier
    dossier = _build_dossier(db, row_to_dict(row))
    db.close()
    return dossier

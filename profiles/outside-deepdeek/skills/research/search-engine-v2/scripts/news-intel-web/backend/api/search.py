"""GET /api/v1/search — full-text search on event titles and summaries."""

from fastapi import APIRouter, HTTPException, Query

from db import get_db
from models.schemas import EventListItem, SearchResponse

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_events(q: str = Query(..., min_length=2)):
    try:
        db = get_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    pattern = f"%{q}%"
    rows = db.execute(
        "SELECT event_id, title, event_type, stage, confidence, "
        "location_country, subject_name, action_type, object_name, "
        "source_count, article_count, last_updated "
        "FROM event_registry "
        "WHERE title LIKE ? OR summary LIKE ? OR keywords LIKE ? "
        "ORDER BY confidence DESC LIMIT 20",
        (pattern, pattern, pattern),
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
    return SearchResponse(query=q, events=items)

"""GET /api/v1/sources — source registry with event counts."""

from fastapi import APIRouter, HTTPException

from db import get_db
from models.schemas import SourceEntity

router = APIRouter(tags=["sources"])


@router.get("/sources")
def list_sources():
    try:
        db = get_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    rows = db.execute("""
        SELECT sr.source_id, sr.name, sr.type, sr.authority,
               COUNT(er.event_id) as event_count
        FROM source_registry sr
        LEFT JOIN event_registry er ON sr.source_id = er.primary_source_id
        GROUP BY sr.source_id
        ORDER BY sr.authority DESC
        LIMIT 100
    """).fetchall()

    items = [
        SourceEntity(
            source_id=r["source_id"],
            name=r["name"],
            type=r["type"] or "MEDIA",
            authority=r["authority"] or 5,
            event_count=r["event_count"],
        )
        for r in rows
    ]

    db.close()
    return {"items": items}

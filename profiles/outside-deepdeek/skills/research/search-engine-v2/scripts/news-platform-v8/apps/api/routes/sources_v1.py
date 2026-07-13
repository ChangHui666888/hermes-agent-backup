"""routes/sources_v1.py — Source network."""

from fastapi import APIRouter
from apps.api.database import get_db
from apps.api.models import Source

router = APIRouter(tags=["sources"])


@router.get("/sources")
def list_sources():
    db = next(get_db())
    try:
        items = [{"source_id": str(s.id), "name": s.name, "type": s.type or "MEDIA",
                   "authority": 5, "event_count": 0} for s in db.query(Source).all()]
        return {"items": items}
    finally:
        db.close()

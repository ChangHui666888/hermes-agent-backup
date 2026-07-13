"""routes/ads.py — Ad serving."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from apps.api.database import get_db
from apps.api.models import Ad

router = APIRouter(prefix="/ads", tags=["ads"])


@router.get("/random")
def random_ad(position: str = "sidebar", db: Session = Depends(get_db)):
    ad = db.query(Ad).filter(Ad.is_active == True, Ad.position == position).order_by(func.random()).first()
    if not ad:
        return None
    return {"id": ad.id, "title": ad.title, "image_url": ad.image_url, "link_url": ad.link_url}

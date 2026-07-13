"""routes/categories.py"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from apps.api.database import get_db
from apps.api.models import Article

router = APIRouter(tags=["categories"])


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(Article.category, func.count(Article.id).label("cnt"))
        .filter(Article.is_published == True, Article.category.isnot(None))
        .group_by(Article.category)
        .order_by(func.count(Article.id).desc())
        .all()
    )
    return [{"name": r[0], "count": r[1]} for r in rows]

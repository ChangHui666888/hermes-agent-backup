"""routes/admin.py — Admin dashboard."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from apps.api.database import get_db
from apps.api.models import Article, User, Ad
from apps.api.routes.auth import get_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
def dashboard(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    return {
        "articles_total": db.query(func.count(Article.id)).scalar(),
        "articles_published": db.query(func.count(Article.id)).filter(Article.is_published == True).scalar(),
        "users_total": db.query(func.count(User.id)).scalar(),
        "ads_active": db.query(func.count(Ad.id)).filter(Ad.is_active == True).scalar(),
    }

"""routes/news.py — Article queries with VIP content masking."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from apps.api.database import get_db
from apps.api.models import Article
from apps.api.routes.auth import get_current_user, get_vip
from apps.api.schemas import ArticleList

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=ArticleList)
def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = Query(None),
    tier: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Article).filter(Article.is_published == True)
    if category:
        q = q.filter(Article.category == category)
    if tier:
        q = q.filter(Article.tier == tier.upper())
    total = q.count()
    items = q.order_by(desc(Article.published_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_public_fields(a) for a in items]}


@router.get("/hot")
def hot_news(limit: int = Query(10), db: Session = Depends(get_db)):
    items = db.query(Article).filter(Article.is_published == True).order_by(desc(Article.score_total)).limit(limit).all()
    return {"items": [_public_fields(a) for a in items]}


@router.get("/latest")
def latest_news(limit: int = Query(20), db: Session = Depends(get_db)):
    items = db.query(Article).filter(Article.is_published == True).order_by(desc(Article.published_at)).limit(limit).all()
    return {"items": [_public_fields(a) for a in items]}


@router.get("/search")
def search_news(q: str = Query(...), page: int = Query(1), db: Session = Depends(get_db)):
    pattern = f"%{q}%"
    items = db.query(Article).filter(
        Article.is_published == True,
        (Article.title.ilike(pattern)) | (Article.summary_cn.ilike(pattern)),
    ).order_by(desc(Article.score_total)).offset((page - 1) * 20).limit(20).all()
    return {"items": [_public_fields(a) for a in items], "total": len(items)}


@router.get("/{article_id}")
def get_article(
    article_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.query(Article).filter(Article.id == article_id).first()
    if not a:
        raise HTTPException(status_code=404)
    result = _public_fields(a)
    # VIP/Admin get full content
    if user and user.level in ("vip", "admin"):
        result["content_md"] = a.content_md
        result["analysis"] = a.analysis
        result["key_points"] = a.key_points
    return result


def _public_fields(a: Article) -> dict:
    return {
        "id": a.id, "url": a.url, "title": a.title,
        "summary_cn": a.summary_cn, "source_name": a.source_name,
        "source_domain": a.source_domain, "published_at": str(a.published_at) if a.published_at else None,
        "category": a.category, "tier": a.tier, "score_total": a.score_total,
        "tags": a.tags, "entities": a.entities, "extraction_method": a.extraction_method,
    }

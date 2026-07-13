"""apps/api/schemas.py — Pydantic models."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json


def _parse_json(v):
    if isinstance(v, str):
        try: return json.loads(v)
        except: return v
    return v


class ArticleIn(BaseModel):
    url: str
    title: str
    content_md: Optional[str] = None
    published_at: Optional[datetime] = None
    source_name: Optional[str] = None
    source_domain: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list] = None
    entities: Optional[dict] = None
    score_total: Optional[int] = 0
    score_breakdown: Optional[dict] = None
    tier: Optional[str] = None
    analysis: Optional[dict] = None
    summary_cn: Optional[str] = None
    key_points: Optional[list] = None
    extraction_method: Optional[str] = None
    fetch_strategy: Optional[str] = None
    fetch_cost: Optional[int] = 0


class ArticleOut(BaseModel):
    id: int
    url: str
    title: str
    summary_cn: Optional[str] = None
    source_name: Optional[str] = None
    source_domain: Optional[str] = None
    published_at: Optional[str] = None
    category: Optional[str] = None
    tier: Optional[str] = None
    score_total: Optional[int] = None
    tags: Optional[list] = None
    entities: Optional[dict] = None
    extraction_method: Optional[str] = None


class ArticleDetail(ArticleOut):
    content_md: Optional[str] = None
    analysis: Optional[dict] = None
    key_points: Optional[list] = None


class ArticleList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ArticleOut]


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    token: str
    level: str


class SubscribeIn(BaseModel):
    tag_id: int

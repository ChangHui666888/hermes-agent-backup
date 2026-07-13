"""apps/api/models.py — All 18 tables from pg_dump + expanded event fields."""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from apps.api.database import Base


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    url = Column(String(2048))
    type = Column(String(20), default="rss")
    status = Column(String(20), default="active")
    failure_count = Column(Integer, default=0)
    quarantine_until = Column(DateTime)
    created_at = Column(DateTime, default=func.now())


class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(2048), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text)
    summary_cn = Column(Text)
    content_md = Column(Text)
    content_len = Column(Integer)
    source_name = Column(String(200))
    source_domain = Column(String(200))
    published_at = Column(DateTime)
    category = Column(String(100))
    importance = Column(String(20))
    importance_level = Column(String(20), default="medium")
    tags = Column(JSONB)
    entities = Column(JSONB)
    score_total = Column(Integer)
    score_breakdown = Column(JSONB)
    tier = Column(String(1))
    analysis = Column(JSONB)
    key_points = Column(JSONB)
    extraction_method = Column(String(50))
    fetch_strategy = Column(String(50))
    fetch_cost = Column(Integer)
    is_published = Column(Boolean, default=True)
    is_duplicate = Column(Boolean, default=False)
    status = Column(String(20), default="raw")
    language = Column(String(5), default="en")
    source_id = Column(Integer, ForeignKey("sources.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime)
    fetched_at = Column(DateTime, default=func.now())


class Event(Base):
    """Expanded event_registry — SAO + evidence + source_chain + timeline."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(30), nullable=False, unique=True, index=True)  # EVT-YYYYMMDD-NNN
    title = Column(String(500), nullable=False)
    summary = Column(Text)
    event_type = Column(String(50))
    stage = Column(String(20), default="active")
    confidence = Column(Float, default=0.0)
    coherence = Column(Float, default=0.0)
    # SAO
    subject_name = Column(String(200))
    subject_type = Column(String(50))
    action_type = Column(String(50))
    action_detail = Column(Text)
    object_name = Column(String(200))
    object_type = Column(String(50))
    location_country = Column(String(100))
    # Source
    primary_source_id = Column(String(100))
    source_count = Column(Integer, default=0)
    article_count = Column(Integer, default=0)
    # JSONB fields (Dossier)
    article_ids = Column(JSONB)
    doc_refs = Column(JSONB)
    actors = Column(JSONB)
    keywords = Column(JSONB)
    related_entities = Column(JSONB)
    evidence = Column(JSONB)       # [{quote, source, url}]
    source_chain = Column(JSONB)   # [{source_id, source_name, time, role, url}]
    timeline = Column(JSONB)       # [{time, update, source}]
    llm_analysis = Column(JSONB)
    extraction_method = Column(String(50), default="v8")
    first_seen = Column(DateTime)
    last_updated = Column(DateTime)
    created_at = Column(DateTime, default=func.now())


class Entity(Base):
    __tablename__ = "entities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50))
    country = Column(String(100))
    importance = Column(Integer, default=50)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    level = Column(String(20), default="free")  # free / vip / admin
    expire_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())


class Ad(Base):
    __tablename__ = "ads"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200))
    image_url = Column(String(500))
    link_url = Column(String(500))
    position = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"))


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)


class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(200))
    exchange = Column(String(50))


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    tag_id = Column(Integer, ForeignKey("tags.id"))


class Insight(Base):
    __tablename__ = "insights"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id"))
    content = Column(JSONB)
    created_at = Column(DateTime, default=func.now())


class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(JSONB)
    updated_at = Column(DateTime, default=func.now())


class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20))
    message = Column(Text)
    created_at = Column(DateTime, default=func.now())


# Association tables
class ArticleCategory(Base):
    __tablename__ = "article_category"
    article_id = Column(Integer, ForeignKey("articles.id"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), primary_key=True)


class ArticleTag(Base):
    __tablename__ = "article_tag"
    article_id = Column(Integer, ForeignKey("articles.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)


class ArticleEntity(Base):
    __tablename__ = "article_entity"
    article_id = Column(Integer, ForeignKey("articles.id"), primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), primary_key=True)
    relevance_score = Column(Float, default=1.0)


class EventArticle(Base):
    __tablename__ = "event_article"
    event_id = Column(Integer, ForeignKey("events.id"), primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), primary_key=True)


class EventEntity(Base):
    __tablename__ = "event_entity"
    event_id = Column(Integer, ForeignKey("events.id"), primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), primary_key=True)

"""Pydantic models — mirrored from frozen frontend contracts/"""

from pydantic import BaseModel
from typing import Optional


class SAOEntity(BaseModel):
    entity_id: Optional[str] = None
    name: str
    type: str


class Action(BaseModel):
    type: str
    detail: Optional[str] = None


class Location(BaseModel):
    country: Optional[str] = None
    region: Optional[str] = None


class SourceInfo(BaseModel):
    primary_source: str
    primary_source_id: Optional[str] = None
    authority: int
    source_count: int
    sources: list[str] = []


class Actor(BaseModel):
    entity: str
    type: str
    role: str


class EntityRef(BaseModel):
    entity_id: Optional[str] = None
    name: str
    type: str


class Evidence(BaseModel):
    quote: str
    source: str
    url: str


class SourceChainItem(BaseModel):
    source_id: str
    source_name: str
    time: Optional[str] = None
    role: str  # 'break' | 'follow'
    url: str


class TimelineItem(BaseModel):
    time: Optional[str] = None
    update: str
    source: str


class DocRef(BaseModel):
    url: str
    title: str


# ── Event Dossier ────────────────────────────────────────────────

class EventDossier(BaseModel):
    event_id: str
    title: str
    summary: Optional[str] = None
    event_type: str
    stage: str
    confidence: float
    coherence: float
    subject: SAOEntity
    action: Action
    object: SAOEntity
    location: Location
    source: SourceInfo
    actors: list[Actor] = []
    keywords: list[str] = []
    related_entities: list[EntityRef] = []
    article_count: int
    first_seen: Optional[str] = None
    last_updated: Optional[str] = None
    evidence: list[Evidence] = []
    source_chain: list[SourceChainItem] = []
    timeline: list[TimelineItem] = []
    llm_analysis: Optional[dict] = None
    extraction_method: Optional[str] = None


# ── Dashboard ────────────────────────────────────────────────────

class DashboardMetrics(BaseModel):
    active_events: int
    critical_events: int
    today_updates: int
    sources: int


class MapEvent(BaseModel):
    event_id: str
    title: str
    country: Optional[str] = None
    impact_level: Optional[str] = None
    confidence: float


class DashboardResponse(BaseModel):
    metrics: DashboardMetrics
    hot_events: list[EventDossier] = []
    map_events: list[MapEvent] = []


# ── Event List ───────────────────────────────────────────────────

class EventListItem(BaseModel):
    event_id: str
    title: str
    event_type: str
    stage: str
    confidence: float
    location_country: Optional[str] = None
    subject_name: Optional[str] = None
    action_type: Optional[str] = None
    object_name: Optional[str] = None
    source_count: int
    article_count: int
    last_updated: Optional[str] = None


class EventListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[EventListItem]


# ── Sources ──────────────────────────────────────────────────────

class SourceEntity(BaseModel):
    source_id: str
    name: str
    type: str
    authority: int
    event_count: int


# ── Map ──────────────────────────────────────────────────────────

class MapEventsResponse(BaseModel):
    events: list[MapEvent]


# ── Search ───────────────────────────────────────────────────────

class SearchResponse(BaseModel):
    query: str
    events: list[EventListItem]

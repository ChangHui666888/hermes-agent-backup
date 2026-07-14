"""routes/internal.py — Hermes -> V8 push endpoint. NO hardcoded secrets."""

import json, os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from apps.api.database import get_db
from apps.api.models import Article
from apps.api.schemas import ArticleIn
from sqlalchemy.dialects.postgresql import insert

router = APIRouter(prefix="/internal", tags=["internal"])

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN")
if not INTERNAL_TOKEN:
    raise RuntimeError("INTERNAL_TOKEN environment variable is required")


def verify_internal(x_internal_token: str = Header(None)):
    if not x_internal_token or x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    return True


@router.post("/news/batch")
def ingest_articles(
    articles: List[ArticleIn],
    _: bool = Depends(verify_internal),
    db: Session = Depends(get_db),
):
    """Batch ingest articles from Hermes Pipeline."""
    ok, fail = 0, 0
    for a in articles:
        try:
            stmt = (
                insert(Article)
                .values(
                    url=a.url, title=a.title, content_md=a.content_md,
                    published_at=a.published_at, source_name=a.source_name,
                    source_domain=a.source_domain, category=a.category,
                    tags=json.dumps(a.tags, ensure_ascii=False) if a.tags else None,
                    entities=json.dumps(a.entities, ensure_ascii=False) if a.entities else None,
                    score_total=a.score_total,
                    score_breakdown=json.dumps(a.score_breakdown) if a.score_breakdown else None,
                    tier=a.tier, analysis=json.dumps(a.analysis) if a.analysis else None,
                    summary_cn=a.summary_cn,
                    key_points=json.dumps(a.key_points) if a.key_points else None,
                    extraction_method=a.extraction_method,
                    fetch_strategy=a.fetch_strategy, fetch_cost=a.fetch_cost,
                )
                .on_conflict_do_update(
                    index_elements=["url"],
                    set_={"title": a.title, "content_md": a.content_md,
                          "score_total": a.score_total, "tier": a.tier},
                )
            )
            db.execute(stmt)
            ok += 1
        except Exception as e:
            fail += 1
    db.commit()
    return {"ok": ok, "fail": fail}


@router.post("/events/batch")
def ingest_events(
    events: List[dict],
    _: bool = Depends(verify_internal),
    db: Session = Depends(get_db),
):
    """Batch ingest event dossiers from Pipeline aggregator."""
    ok, fail = 0, 0
    SQL = text("""
        INSERT INTO events (event_id, title, summary, event_type, stage,
            confidence, coherence, subject_name, subject_type, action_type, action_detail,
            object_name, object_type, location_country, primary_source_id,
            source_count, article_count, article_ids, doc_refs, actors,
            keywords, related_entities, evidence, source_chain, timeline,
            llm_analysis, first_seen, last_updated)
        VALUES (:event_id, :title, :summary, :event_type, :stage,
            :confidence, :coherence, :subject_name, :subject_type, :action_type, :action_detail,
            :object_name, :object_type, :location_country, :primary_source_id,
            :source_count, :article_count, :article_ids, :doc_refs, :actors,
            :keywords, :related_entities, :evidence, :source_chain, :timeline,
            :llm_analysis, :first_seen, :last_updated)
        ON CONFLICT (event_id) DO UPDATE SET
            title=EXCLUDED.title, summary=EXCLUDED.summary,
            stage=EXCLUDED.stage, confidence=EXCLUDED.confidence,
            coherence=EXCLUDED.coherence, last_updated=EXCLUDED.last_updated,
            evidence=EXCLUDED.evidence, source_chain=EXCLUDED.source_chain,
            timeline=EXCLUDED.timeline, llm_analysis=EXCLUDED.llm_analysis
    """)
    for ev in events:
        try:
            db.execute(SQL, {
                "event_id": ev.get("event_id"), "title": ev.get("title", ""),
                "summary": ev.get("summary", ""), "event_type": ev.get("event_type"),
                "stage": ev.get("stage", "active"), "confidence": ev.get("confidence", 0.0),
                "coherence": ev.get("coherence", 0.0),
                "subject_name": ev.get("subject", {}).get("name") if isinstance(ev.get("subject"), dict) else None,
                "subject_type": ev.get("subject", {}).get("type") if isinstance(ev.get("subject"), dict) else None,
                "action_type": ev.get("action", {}).get("type") if isinstance(ev.get("action"), dict) else None,
                "action_detail": ev.get("action", {}).get("detail") if isinstance(ev.get("action"), dict) else None,
                "object_name": ev.get("object", {}).get("name") if isinstance(ev.get("object"), dict) else None,
                "object_type": ev.get("object", {}).get("type") if isinstance(ev.get("object"), dict) else None,
                "location_country": ev.get("location", {}).get("country") if isinstance(ev.get("location"), dict) else None,
                "primary_source_id": ev.get("source", {}).get("primary_source_id") if isinstance(ev.get("source"), dict) else None,
                "source_count": ev.get("source", {}).get("source_count") if isinstance(ev.get("source"), dict) else 0,
                "article_count": ev.get("article_count", 0),
                "article_ids": json.dumps(ev.get("article_ids", [])),
                "doc_refs": json.dumps(ev.get("doc_refs", [])),
                "actors": json.dumps(ev.get("actors", [])),
                "keywords": json.dumps(ev.get("keywords", [])),
                "related_entities": json.dumps(ev.get("related_entities", [])),
                "evidence": json.dumps(ev.get("evidence", [])),
                "source_chain": json.dumps(ev.get("source_chain", [])),
                "timeline": json.dumps(ev.get("timeline", [])),
                "llm_analysis": json.dumps(ev.get("llm_analysis")) if ev.get("llm_analysis") else None,
                "first_seen": ev.get("first_seen"), "last_updated": ev.get("last_updated"),
            })
            ok += 1
        except Exception as e:
            fail += 1
    db.commit()
    return {"ok": ok, "fail": fail}

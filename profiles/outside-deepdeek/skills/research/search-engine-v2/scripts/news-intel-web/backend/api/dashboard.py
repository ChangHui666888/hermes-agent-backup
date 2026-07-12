"""GET /api/v1/dashboard — KPI metrics + hot events + map events."""

from fastapi import APIRouter, HTTPException

from db import get_db, row_to_dict
from models.schemas import (
    DashboardMetrics, DashboardResponse, EventDossier, MapEvent,
)

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard():
    try:
        db = get_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    # Metrics
    metrics = DashboardMetrics(
        active_events=db.execute(
            "SELECT COUNT(*) FROM event_registry WHERE stage IN ('active','developing','breaking')"
        ).fetchone()[0],
        critical_events=0,  # no explicit critical flag; derived from confidence + article_count
        today_updates=db.execute(
            "SELECT COUNT(*) FROM event_registry WHERE last_updated > datetime('now','-1 day','localtime')"
        ).fetchone()[0],
        sources=db.execute(
            "SELECT COUNT(*) FROM source_registry"
        ).fetchone()[0],
    )

    # Hot events (top 6 by confidence)
    rows = db.execute(
        "SELECT * FROM event_registry ORDER BY confidence DESC LIMIT 6"
    ).fetchall()
    hot_events = [_build_dossier(db, row_to_dict(r)) for r in rows]

    # Map events (country non-null, distinct by country for broad coverage)
    map_rows = db.execute(
        "SELECT DISTINCT event_id, title, location_country as country, event_type, confidence "
        "FROM event_registry WHERE location_country IS NOT NULL AND location_country != '' "
        "ORDER BY confidence DESC LIMIT 20"
    ).fetchall()
    map_events = [
        MapEvent(
            event_id=r["event_id"], title=r["title"], country=r["country"],
            impact_level=r["event_type"], confidence=r["confidence"],
        )
        for r in map_rows
    ]

    db.close()
    return DashboardResponse(metrics=metrics, hot_events=hot_events, map_events=map_events)


def _build_dossier(db, row: dict) -> EventDossier:
    """Convert a raw event_registry row into a full EventDossier."""
    from models.schemas import (
        SAOEntity, Action, Location, SourceInfo,
    )

    return EventDossier(
        event_id=row["event_id"],
        title=row["title"] or "",
        summary=row.get("summary"),
        event_type=row["event_type"] or "Other",
        stage=row["stage"] or "active",
        confidence=row["confidence"] or 0.0,
        coherence=row.get("coherence") or 0.0,
        subject=SAOEntity(
            entity_id=None,
            name=row.get("subject_name") or "",
            type=row.get("subject_type") or "Other",
        ),
        action=Action(
            type=row.get("action_type") or "OTHER",
            detail=row.get("action_detail"),
        ),
        object=SAOEntity(
            entity_id=None,
            name=row.get("object_name") or "",
            type=row.get("object_type") or "Other",
        ),
        location=Location(country=row.get("location_country"), region=None),
        source=SourceInfo(
            primary_source=row.get("primary_source_id", ""),
            primary_source_id=row.get("primary_source_id"),
            authority=_lookup_authority(db, row.get("primary_source_id")),
            source_count=row.get("source_count") or 0,
            sources=_extract_source_names(row),
        ),
        actors=row.get("actors") or [],
        keywords=row.get("keywords") or [],
        related_entities=row.get("related_entities") or [],
        article_count=row.get("article_count") or 0,
        first_seen=row.get("first_seen"),
        last_updated=row.get("last_updated"),
        evidence=row.get("evidence") or [],
        source_chain=row.get("source_chain") or [],
        timeline=row.get("timeline") or [],
        llm_analysis=row.get("llm_analysis"),
        extraction_method=row.get("extraction_method"),
    )


def _lookup_authority(db, primary_source_id: str | None) -> int:
    """Look up authority from source_registry."""
    if not primary_source_id:
        return 0
    try:
        r = db.execute(
            "SELECT authority FROM source_registry WHERE source_id=?",
            (primary_source_id,),
        ).fetchone()
        return r[0] if r else 0
    except Exception:
        return 0


def _extract_source_names(row: dict) -> list[str]:
    """Extract source names from source_chain JSON."""
    chain = row.get("source_chain")
    if isinstance(chain, list):
        return list({sc.get("source_name", "") for sc in chain if sc.get("source_name")})
    if isinstance(chain, str):
        try:
            import json
            data = json.loads(chain)
            if isinstance(data, list):
                return list({sc.get("source_name", "") for sc in data if sc.get("source_name")})
        except Exception:
            pass
    return []

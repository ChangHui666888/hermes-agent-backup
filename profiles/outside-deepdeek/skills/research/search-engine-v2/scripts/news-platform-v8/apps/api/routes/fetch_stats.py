"""routes/fetch_stats.py — Domain strategy statistics endpoint."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from apps.api.database import get_db
import os

router = APIRouter(prefix="/internal", tags=["internal"])

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")


def verify(x_token: str = Header(None, alias="X-Internal-Token")):
    if not x_token or x_token != INTERNAL_TOKEN:
        raise HTTPException(403)


@router.post("/fetch_stats")
def ingest_fetch_stats(stats: list[dict], _=Depends(verify), db: Session = Depends(get_db)):
    """Receive domain-strategy statistics from pipeline."""
    ok = fail = 0
    for s in stats:
        try:
            db.execute(text("""
                INSERT INTO fetch_stats (domain, strategy, ok_count, fail_count, run_at)
                VALUES (:d, :s, :o, :f, :t)
            """), {"d": s["domain"], "s": s["strategy"], "o": s["ok"], "f": s["fail"], "t": s["run_at"]})
            ok += 1
        except Exception:
            fail += 1
    db.commit()
    return {"ok": ok, "fail": fail}


@router.get("/admin/fetch_stats")
def get_fetch_stats(db: Session = Depends(get_db)):
    """Query domain-strategy aggregate statistics."""
    rows = db.execute(text("""
        SELECT domain, strategy, SUM(ok_count) as ok, SUM(fail_count) as fail,
               ROUND(SUM(ok_count)*100.0/MAX(SUM(ok_count)+SUM(fail_count),1),1) as rate
        FROM fetch_stats
        GROUP BY domain, strategy
        ORDER BY SUM(ok_count+fail_count) DESC
        LIMIT 50
    """)).fetchall()
    return [{"domain": r[0], "strategy": r[1], "ok": r[2], "fail": r[3], "rate": r[4]} for r in rows]

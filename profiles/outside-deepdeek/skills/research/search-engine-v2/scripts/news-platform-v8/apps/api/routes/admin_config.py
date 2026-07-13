"""routes/admin_config.py — Pipeline Config page API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import Setting
from apps.api.routes.auth import get_admin

router = APIRouter(prefix="/admin/pipeline", tags=["admin"])


@router.get("/config")
def get_config(_=Depends(get_admin), db: Session = Depends(get_db)):
    """Get all pipeline config key-value pairs."""
    rows = db.query(Setting).all()
    return {r.key: r.value for r in rows}


@router.put("/config/{key}")
def set_config(key: str, value: dict, _=Depends(get_admin), db: Session = Depends(get_db)):
    """Update a config key. value is JSON."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()
    return {"ok": True}

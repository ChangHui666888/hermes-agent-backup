# PG Data Migration Pattern

One-shot SQLite → PostgreSQL migration with upsert support.

## Pattern

```python
import sqlite3, json
from sqlalchemy import text
from apps.api.database import SessionLocal

# 1. Read from SQLite
conn = sqlite3.connect("/path/to/news_intel.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM event_registry").fetchall()

# 2. Insert into PG with upsert
db = SessionLocal()
for r in rows:
    ev = dict(r)
    db.execute(text("""
        INSERT INTO events (event_id, title, ...)
        VALUES (:a, :b, ...)
        ON CONFLICT (event_id) DO UPDATE SET
            title=EXCLUDED.title, confidence=EXCLUDED.confidence
    """), {
        "a": ev.get("event_id"),
        "b": ev.get("title", ""),
    })
db.commit()
db.close()
```

## Key Rules

- Use `text()` wrapper for raw SQL in SQLAlchemy 2.0
- Use `ON CONFLICT (event_id) DO UPDATE` for idempotent re-runs
- JSON fields (evidence, source_chain, timeline) must be serialized with `json.dumps()`
- Drop old tables with FK constraints using `DROP TABLE ... CASCADE`
- Always verify: `SELECT COUNT(*) FROM events` after migration

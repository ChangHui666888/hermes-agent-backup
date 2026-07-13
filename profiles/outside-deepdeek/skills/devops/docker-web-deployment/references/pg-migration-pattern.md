# PostgreSQL Table Migration Patterns

## Direct SQLite → PostgreSQL Migration

When migrating event data from a pipeline SQLite database to a cloud PostgreSQL instance:

```python
import sqlite3, json
from sqlalchemy import text
from apps.api.database import SessionLocal

# Read from SQLite
conn = sqlite3.connect("/tmp/source.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM event_registry").fetchall()

# Write to PostgreSQL via ORM session
db = SessionLocal()
for r in rows:
    ev = dict(r)
    db.execute(text("""
        INSERT INTO events (event_id, title, summary, event_type, stage, confidence, ...)
        VALUES (:a, :b, :c, :d, :e, :f, ...)
        ON CONFLICT (event_id) DO UPDATE SET title=EXCLUDED.title
    """), {
        "a": ev.get("event_id"), "b": ev.get("title", ""), ...
    })
db.commit()
```

## Table Re-creation with FK Constraints

When the ORM model changes and tables need to be recreated:

1. Drop with CASCADE (raw SQL — ORM can't handle FK chains)
2. Recreate with ORM (for proper column types)

```python
from sqlalchemy import text
from apps.api.database import engine

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS event_article CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS event_entity CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS insights CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS events CASCADE"))
    conn.commit()

from apps.api.models import Event, Entity
Event.__table__.create(engine, checkfirst=True)
Entity.__table__.create(engine, checkfirst=True)
```

## Docker PYTHONPATH for Nested Modules

When the app uses `apps.api.models` (nested module structure):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app          # REQUIRED for apps.api.* imports
```

Without PYTHONPATH, `ModuleNotFoundError: No module named 'apps'`.

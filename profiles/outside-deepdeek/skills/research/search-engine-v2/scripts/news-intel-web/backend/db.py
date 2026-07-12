"""SQLite read-only adapter for v4.4 event_registry in Docker.

The event_registry is mounted at /data/news_intel.db (read-only volume).
We use URI mode with immutable=1 to prevent SQLite from trying to
create WAL/SHM files on the read-only mount.
"""

import sqlite3
import os
import json

# Path to the v4.4 pipeline's news_intel.db
# Override via DB_PATH env var for Docker mount: /data/news_intel.db
PIPELINE_DB = os.environ.get(
    "DB_PATH",
    os.path.join(
        os.path.expanduser("~"),
        "AppData", "Local", "hermes", "profiles", "outside-deepdeek",
        "skills", "research", "search-engine-v2", "scripts", "news_intel",
        "news_intel.db",
    ),
)


def get_db() -> sqlite3.Connection:
    """Open read-only connection. Uses URI mode with immutable=1 for Docker."""
    if os.environ.get("DB_PATH"):
        # Docker: volume is mounted read-only, SQLite needs immutable flag
        uri = f"file:{PIPELINE_DB}?mode=ro&immutable=1"
        db = sqlite3.connect(uri, uri=True)
    else:
        # Local Windows development
        db = sqlite3.connect(f"file:{PIPELINE_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def parse_json_field(value: str | None) -> list | dict | None:
    """Parse a JSON string field from event_registry."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert sqlite3.Row to plain dict, parsing JSON fields."""
    d = dict(row)
    json_fields = [
        "article_ids", "doc_refs", "actors", "keywords",
        "related_entities", "evidence", "source_chain",
        "timeline", "llm_analysis",
    ]
    for k in json_fields:
        if k in d:
            d[k] = parse_json_field(d[k])
    return d

"""
news_intel/db.py - News Intelligence Database (v4.4: 6 tables)

Article Layer (3 tables):
  rss_raw            - RSS raw data (immutable)
  news_intelligence  - scoring + classification + tags + entities
  news_content       - fetched content + analysis results

Event Layer (3 tables, new in v4.4):
  event_registry     - event dossier (event_id PK, 21+ fields)
  source_registry    - source entity (source_id, type, authority)
  entity_registry    - entity ID standardisation (entity_id, name, type)
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_intel.db")


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """Create all 6 tables + indexes."""
    db = get_db()

    # ---- Layer: Raw RSS -----------------------------------------
    db.executescript("""
        CREATE TABLE IF NOT EXISTS rss_raw (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            guid            TEXT UNIQUE NOT NULL,
            source_name     TEXT NOT NULL,
            source_domain   TEXT,
            feed_url        TEXT,
            article_url     TEXT NOT NULL,
            title           TEXT,
            description     TEXT,
            content_encoded TEXT,
            author          TEXT,
            published_at    TEXT,
            updated_at      TEXT,
            language        TEXT,
            category_raw    TEXT,
            tags_raw        TEXT,
            image_url       TEXT,
            enclosure_url   TEXT,
            raw_xml         TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_raw_published ON rss_raw(published_at);
        CREATE INDEX IF NOT EXISTS idx_raw_source ON rss_raw(source_name);
        CREATE INDEX IF NOT EXISTS idx_raw_domain ON rss_raw(source_domain);
    """)

    # ---- Layer: Intelligence ------------------------------------
    db.executescript("""
        CREATE TABLE IF NOT EXISTS news_intelligence (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id          INTEGER UNIQUE REFERENCES rss_raw(id),
            score_total     INTEGER DEFAULT 0,
            score_source    INTEGER DEFAULT 0,
            score_impact    INTEGER DEFAULT 0,
            score_entity    INTEGER DEFAULT 0,
            score_market    INTEGER DEFAULT 0,
            score_velocity  INTEGER DEFAULT 0,
            tier            TEXT,
            category        TEXT,
            tags            TEXT,
            entities        TEXT,
            importance      TEXT,
            velocity_count  INTEGER DEFAULT 0,
            velocity_window INTEGER DEFAULT 0,
            scored_at       TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_intel_score ON news_intelligence(score_total);
        CREATE INDEX IF NOT EXISTS idx_intel_tier ON news_intelligence(tier);
        CREATE INDEX IF NOT EXISTS idx_intel_category ON news_intelligence(category);
    """)

    # ---- Layer: Content -----------------------------------------
    db.executescript("""
        CREATE TABLE IF NOT EXISTS news_content (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            intel_id        INTEGER REFERENCES news_intelligence(id),
            article_url     TEXT UNIQUE NOT NULL,
            content_md      TEXT,
            content_html    TEXT,
            content_len     INTEGER DEFAULT 0,
            fetch_strategy  TEXT,
            fetch_cost      INTEGER DEFAULT 0,
            fetch_at        TEXT,
            summary_cn      TEXT,
            summary_en      TEXT,
            key_points      TEXT,
            source_headline TEXT,
            published_at    TEXT,
            author_name     TEXT,
            extraction_method TEXT,
            llm_model       TEXT,
            llm_cost        REAL DEFAULT 0.0,
            temporal_check  TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_content_url ON news_content(article_url);
        CREATE INDEX IF NOT EXISTS idx_content_method ON news_content(extraction_method);
    """)

    # ---- Layer: Source Registry (new v4.4) ----------------------
    db.executescript("""
        CREATE TABLE IF NOT EXISTS source_registry (
            source_id       TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            display_name    TEXT,
            type            TEXT NOT NULL DEFAULT 'MEDIA',
            authority       INTEGER NOT NULL DEFAULT 5,
            country         TEXT,
            language        TEXT,
            url             TEXT,
            first_seen      TEXT,
            last_seen       TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_source_type ON source_registry(type);
        CREATE INDEX IF NOT EXISTS idx_source_authority ON source_registry(authority);
    """)

    # ---- Layer: Entity Registry (new v4.4) ----------------------
    db.executescript("""
        CREATE TABLE IF NOT EXISTS entity_registry (
            entity_id       TEXT PRIMARY KEY,
            canonical_name  TEXT NOT NULL,
            aliases         TEXT,
            type            TEXT NOT NULL DEFAULT 'Other',
            country         TEXT,
            importance      INTEGER DEFAULT 50,
            first_seen      TEXT,
            last_seen       TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_entity_type ON entity_registry(type);
        CREATE INDEX IF NOT EXISTS idx_entity_name ON entity_registry(canonical_name);
    """)

    # ---- Layer: Event Registry (new v4.4) -----------------------
    db.executescript("""
        CREATE TABLE IF NOT EXISTS event_registry (
            event_id        TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            summary         TEXT,
            event_type      TEXT,
            stage           TEXT DEFAULT 'active',
            confidence      REAL DEFAULT 0.0,
            coherence       REAL DEFAULT 0.0,
            subject_name    TEXT,
            subject_type    TEXT,
            action_type     TEXT,
            action_detail   TEXT,
            object_name     TEXT,
            object_type     TEXT,
            location_country TEXT,
            primary_source_id TEXT,
            source_count    INTEGER DEFAULT 0,
            article_count   INTEGER DEFAULT 0,
            article_ids     TEXT,
            doc_refs        TEXT,
            actors          TEXT,
            keywords        TEXT,
            related_entities TEXT,
            evidence        TEXT,
            source_chain    TEXT,
            timeline        TEXT,
            first_seen      TEXT,
            last_updated    TEXT,
            llm_analysis    TEXT,
            extraction_method TEXT DEFAULT 'v4.4-saeo',
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_event_stage ON event_registry(stage);
        CREATE INDEX IF NOT EXISTS idx_event_type ON event_registry(event_type);
        CREATE INDEX IF NOT EXISTS idx_event_confidence ON event_registry(confidence);
        CREATE INDEX IF NOT EXISTS idx_event_first_seen ON event_registry(first_seen);
    """)

    db.commit()
    db.close()
    print(f"[db] v4.4 6-tables init: {DB_PATH}")


# ---- Article CRUD (unchanged) -----------------------------------

def insert_raw_article(db: sqlite3.Connection, article: dict) -> int | None:
    try:
        cur = db.execute("""
            INSERT OR IGNORE INTO rss_raw
                (guid, source_name, source_domain, feed_url, article_url,
                 title, description, content_encoded, author,
                 published_at, updated_at, language, category_raw, tags_raw,
                 image_url, enclosure_url, raw_xml)
            VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?,?, ?,?,?)
        """, (
            article.get("guid"),
            article.get("source_name"),
            article.get("source_domain"),
            article.get("feed_url"),
            article.get("article_url"),
            article.get("title"),
            article.get("description"),
            article.get("content_encoded"),
            article.get("author"),
            article.get("published_at"),
            article.get("updated_at"),
            article.get("language"),
            article.get("category_raw"),
            article.get("tags_raw"),
            article.get("image_url"),
            article.get("enclosure_url"),
            article.get("raw_xml"),
        ))
        db.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    except Exception as e:
        print(f"[db] insert_raw_article error: {e}")
        return None


def upsert_intelligence(db: sqlite3.Connection, raw_id: int, scores: dict,
                        tier: str, category: str, tags: list,
                        entities: dict, velocity_count: int = 0):
    db.execute("""
        INSERT INTO news_intelligence
            (raw_id, score_total, score_source, score_impact, score_entity,
             score_market, score_velocity, tier, category, tags, entities,
             velocity_count, scored_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
        ON CONFLICT(raw_id) DO UPDATE SET
            score_total=excluded.score_total,
            score_source=excluded.score_source,
            score_impact=excluded.score_impact,
            score_entity=excluded.score_entity,
            score_market=excluded.score_market,
            score_velocity=excluded.score_velocity,
            tier=excluded.tier,
            category=excluded.category,
            tags=excluded.tags,
            entities=excluded.entities,
            velocity_count=excluded.velocity_count,
            scored_at=datetime('now','localtime')
    """, (
        raw_id,
        scores.get("total", 0),
        scores.get("source", 0),
        scores.get("impact", 0),
        scores.get("entity", 0),
        scores.get("market", 0),
        scores.get("velocity", 0),
        tier,
        category,
        json.dumps(tags, ensure_ascii=False),
        json.dumps(entities, ensure_ascii=False),
        velocity_count,
    ))
    db.commit()


def upsert_content(db: sqlite3.Connection, intel_id: int, content: dict):
    db.execute("""
        INSERT INTO news_content
            (intel_id, article_url, content_md, content_html, content_len,
             fetch_strategy, fetch_cost, fetch_at,
             summary_cn, summary_en, key_points, source_headline,
             published_at, author_name, extraction_method, llm_model, llm_cost,
             temporal_check, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
        ON CONFLICT(article_url) DO UPDATE SET
            intel_id=excluded.intel_id,
            content_md=excluded.content_md,
            content_len=excluded.content_len,
            fetch_strategy=excluded.fetch_strategy,
            fetch_cost=excluded.fetch_cost,
            fetch_at=excluded.fetch_at,
            summary_cn=excluded.summary_cn,
            summary_en=excluded.summary_en,
            key_points=excluded.key_points,
            source_headline=excluded.source_headline,
            published_at=excluded.published_at,
            author_name=excluded.author_name,
            extraction_method=excluded.extraction_method,
            llm_model=excluded.llm_model,
            llm_cost=excluded.llm_cost,
            temporal_check=excluded.temporal_check,
            created_at=datetime('now','localtime')
    """, (
        intel_id,
        content.get("article_url"),
        content.get("content_md"),
        content.get("content_html"),
        content.get("content_len", 0),
        content.get("fetch_strategy"),
        content.get("fetch_cost", 0),
        content.get("fetch_at"),
        content.get("summary_cn"),
        content.get("summary_en"),
        json.dumps(content.get("key_points", []), ensure_ascii=False) if content.get("key_points") else None,
        content.get("source_headline"),
        content.get("published_at"),
        content.get("author_name"),
        content.get("extraction_method"),
        content.get("llm_model"),
        content.get("llm_cost", 0.0),
        json.dumps(content.get("temporal_check", {}), ensure_ascii=False) if content.get("temporal_check") else None,
    ))
    db.commit()


# ---- Source Registry (new v4.4) ---------------------------------

def upsert_source(db: sqlite3.Connection, source_id: str, name: str,
                  source_type: str = "MEDIA", authority: int = 5,
                  display_name: str = None, country: str = None,
                  language: str = None, url: str = None):
    """Register or update a source entity."""
    db.execute("""
        INSERT INTO source_registry (source_id, name, display_name, type, authority,
                                     country, language, url, first_seen, last_seen)
        VALUES (?,?,?,?,?,?,?,?,
                COALESCE((SELECT first_seen FROM source_registry WHERE source_id=?),datetime('now','localtime')),
                datetime('now','localtime'))
        ON CONFLICT(source_id) DO UPDATE SET
            name=excluded.name,
            display_name=COALESCE(excluded.display_name, source_registry.display_name),
            authority=excluded.authority,
            country=COALESCE(excluded.country, source_registry.country),
            last_seen=datetime('now','localtime')
    """, (source_id, name, display_name or name, source_type, authority,
          country, language, url, source_id))
    db.commit()


def get_source(source_id: str, db: sqlite3.Connection = None) -> dict | None:
    """Look up source by ID."""
    conn = db or get_db()
    row = conn.execute("SELECT * FROM source_registry WHERE source_id=?", (source_id,)).fetchone()
    if db is None:
        conn.close()
    return dict(row) if row else None


# ---- Entity Registry (new v4.4) ---------------------------------

def upsert_entity(db: sqlite3.Connection, entity_id: str, canonical_name: str,
                  entity_type: str = "Other", aliases: list = None,
                  country: str = None, importance: int = 50):
    """Register or update an entity with standardised ID."""
    db.execute("""
        INSERT INTO entity_registry (entity_id, canonical_name, aliases, type,
                                     country, importance, first_seen, last_seen)
        VALUES (?,?,?,?,?,?,
                COALESCE((SELECT first_seen FROM entity_registry WHERE entity_id=?),datetime('now','localtime')),
                datetime('now','localtime'))
        ON CONFLICT(entity_id) DO UPDATE SET
            canonical_name=excluded.canonical_name,
            aliases=COALESCE(excluded.aliases, entity_registry.aliases),
            importance=excluded.importance,
            last_seen=datetime('now','localtime')
    """, (entity_id, canonical_name, json.dumps(aliases or [], ensure_ascii=False),
          entity_type, country, importance, entity_id))
    db.commit()


def get_entity(entity_id: str, db: sqlite3.Connection = None) -> dict | None:
    conn = db or get_db()
    row = conn.execute("SELECT * FROM entity_registry WHERE entity_id=?", (entity_id,)).fetchone()
    if db is None:
        conn.close()
    return dict(row) if row else None


# ---- Event Registry (new v4.4) ----------------------------------

def upsert_event(db: sqlite3.Connection, event: dict) -> bool:
    """Insert or update an event dossier in event_registry."""
    try:
        db.execute("""
            INSERT INTO event_registry (
                event_id, title, summary, event_type, stage, confidence, coherence,
                subject_name, subject_type, action_type, action_detail,
                object_name, object_type, location_country,
                primary_source_id, source_count, article_count, article_ids,
                doc_refs, actors, keywords, related_entities,
                evidence, source_chain, timeline,
                first_seen, last_updated, llm_analysis, extraction_method, created_at
            ) VALUES (?,?,?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,datetime('now','localtime'))
            ON CONFLICT(event_id) DO UPDATE SET
                title=excluded.title, summary=excluded.summary,
                stage=excluded.stage, confidence=excluded.confidence,
                coherence=excluded.coherence,
                source_count=excluded.source_count, article_count=excluded.article_count,
                article_ids=excluded.article_ids,
                evidence=excluded.evidence, source_chain=excluded.source_chain,
                timeline=excluded.timeline,
                last_updated=excluded.last_updated,
                llm_analysis=COALESCE(excluded.llm_analysis, event_registry.llm_analysis)
        """, (
            event["event_id"], event.get("title", ""), event.get("summary", ""),
            event.get("event_type"), event.get("stage", "active"),
            event.get("confidence", 0.0), event.get("coherence", 0.0),
            event.get("subject", {}).get("name") if isinstance(event.get("subject"), dict) else None,
            event.get("subject", {}).get("type") if isinstance(event.get("subject"), dict) else None,
            event.get("action", {}).get("type") if isinstance(event.get("action"), dict) else None,
            event.get("action", {}).get("detail") if isinstance(event.get("action"), dict) else None,
            event.get("object", {}).get("name") if isinstance(event.get("object"), dict) else None,
            event.get("object", {}).get("type") if isinstance(event.get("object"), dict) else None,
            event.get("location", {}).get("country") if isinstance(event.get("location"), dict) else None,
            event.get("source", {}).get("primary_source_id") if isinstance(event.get("source"), dict) else None,
            event.get("source", {}).get("source_count") if isinstance(event.get("source"), dict) else 0,
            event.get("article_count", 0),
            json.dumps(event.get("article_ids", []), ensure_ascii=False),
            json.dumps(event.get("doc_refs", []), ensure_ascii=False),
            json.dumps(event.get("actors", []), ensure_ascii=False),
            json.dumps(event.get("keywords", []), ensure_ascii=False),
            json.dumps(event.get("related_entities", []), ensure_ascii=False),
            json.dumps(event.get("evidence", []), ensure_ascii=False),
            json.dumps(event.get("source_chain", []), ensure_ascii=False),
            json.dumps(event.get("timeline", []), ensure_ascii=False),
            event.get("first_seen"), event.get("last_updated"),
            json.dumps(event.get("llm_analysis", {}), ensure_ascii=False) if event.get("llm_analysis") else None,
            event.get("extraction_method", "v4.4-saeo"),
        ))
        db.commit()
        return True
    except Exception as e:
        print(f"[db] upsert_event error: {e}")
        return False


def list_events(stage: str = None, event_type: str = None, limit: int = 50,
                db: sqlite3.Connection = None) -> list[dict]:
    """List events from registry, optionally filtered."""
    conn = db or get_db()
    sql = "SELECT * FROM event_registry"
    params = []
    clauses = []
    if stage:
        clauses.append("stage=?")
        params.append(stage)
    if event_type:
        clauses.append("event_type=?")
        params.append(event_type)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY first_seen DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    if db is None:
        conn.close()

    result = []
    for row in rows:
        d = dict(row)
        for k in ("article_ids", "doc_refs", "actors", "keywords",
                  "related_entities", "evidence", "source_chain",
                  "timeline", "llm_analysis"):
            if d.get(k) and isinstance(d[k], str):
                try:
                    d[k] = json.loads(d[k])
                except json.JSONDecodeError:
                    pass
        result.append(d)
    return result


# ---- Seed source_registry from config ---------------------------

def seed_source_registry(db: sqlite3.Connection = None):
    """Populate source_registry from source_scores.json."""
    conn = db or get_db()
    try:
        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
        with open(os.path.join(config_dir, "source_scores.json"), encoding="utf-8") as f:
            data = json.load(f)
        scores = data.get("scores", {})
        for name, authority in scores.items():
            if name == "_default":
                continue
            source_id = _source_name_to_id(name)
            source_type = _infer_source_type(name)
            upsert_source(conn, source_id, name, source_type=source_type, authority=authority)
        print(f"[db] seeded {len(scores)-1} sources into source_registry")
    except Exception as e:
        print(f"[db] seed_source_registry error: {e}")
    finally:
        if db is None:
            conn.close()


def _source_name_to_id(name: str) -> str:
    """Convert source name to stable ID: 'Reuters' -> 'SRC_REUTERS'."""
    clean = name.upper().replace(" ", "_").replace("-", "_").replace("'", "")
    clean = "".join(c for c in clean if c.isalnum() or c == "_")
    return f"SRC_{clean}" if not clean.startswith("SRC_") else clean


def _infer_source_type(name: str) -> str:
    """Infer source type from name patterns."""
    gov_patterns = ["White House", "Fed ", "Federal Reserve", "SEC", "UN ", "UK Gov",
                    "ECB", "IMF", "World Bank", "OECD", "Bank of England", "BoE",
                    "NASA", "人民网", "新华网", "央视", "CCTV", "中国新闻网", "中国日报", "环球网"]
    for p in gov_patterns:
        if p in name:
            return "GOVERNMENT"
    if name in ("OpenAI", "Google AI", "GitHub", "ArXiv", "MIT Technology Review"):
        return "RESEARCH"
    if name in ("Reddit", "Hacker News"):
        return "SOCIAL"
    return "MEDIA"

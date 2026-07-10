"""
news_intel/db.py — News Intelligence Database (三表架构)

Raw Layer:    RSS原始数据（不可修改）
Intelligence: 评分 + 分类 + 标签 + 实体
Content:      抓取正文 + 分析结果
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_intel.db")


def get_db() -> sqlite3.Connection:
    """获取数据库连接（自动建表）"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """创建三表 + 索引"""
    db = get_db()

    # ── Layer: Raw RSS ─────────────────────────────────────────
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

    # ── Layer: Intelligence ─────────────────────────────────────
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
            tier            TEXT,       -- 'A'(>90) | 'B'(60-90) | 'C'(<60)
            category        TEXT,
            tags            TEXT,       -- JSON array
            entities        TEXT,       -- JSON: {companies, persons, countries}
            importance      TEXT,       -- 'critical'|'high'|'medium'|'low'
            velocity_count  INTEGER DEFAULT 0,
            velocity_window INTEGER DEFAULT 0,
            scored_at       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_intel_score ON news_intelligence(score_total);
        CREATE INDEX IF NOT EXISTS idx_intel_tier ON news_intelligence(tier);
        CREATE INDEX IF NOT EXISTS idx_intel_category ON news_intelligence(category);
    """)

    # ── Layer: Content ──────────────────────────────────────────
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
            key_points      TEXT,       -- JSON array
            source_headline TEXT,
            published_at    TEXT,
            author_name     TEXT,
            extraction_method TEXT,     -- 'rule_based'|'qwen3'|'deepseek-flash'|'deepseek-pro'
            llm_model       TEXT,
            llm_cost        REAL DEFAULT 0.0,
            temporal_check  TEXT,       -- JSON
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_content_url ON news_content(article_url);
        CREATE INDEX IF NOT EXISTS idx_content_method ON news_content(extraction_method);
    """)

    db.commit()
    db.close()
    print(f"[db] 初始化完成: {DB_PATH}")


# ── CRUD Helpers ────────────────────────────────────────────

def insert_raw_article(db: sqlite3.Connection, article: dict) -> int | None:
    """插入原始RSS文章，返回 raw_id"""
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
    """写入/更新评分和分类"""
    import json
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
    """写入/更新抓取内容和分析结果"""
    import json
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

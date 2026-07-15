# V8 Platform — Critical Patterns & Pitfalls

## SQLAlchemy 2.0 raw SQL
MUST wrap in `text()`: `from sqlalchemy import text; db.execute(text("INSERT INTO..."), params)`
Without this, SQLAlchemy 2.0 raises "Textual SQL expression should be explicitly declared as text()"

## Next.js Client Components
Pages that fetch API data MUST be client components ("use client").
Server Components try to resolve relative URLs against localhost:3000 which fails inside Docker.

## Nginx Route Proxy
Multiple location blocks for different API prefixes:
```
location /internal/ { proxy_pass http://backend:8000/internal/; }
location /news { proxy_pass http://backend:8000/news; }
location /api/ { proxy_pass http://backend:8000/api/; }
```
`/news` (no trailing slash) needed for query params like `/news?page=1`.

## SQLite → PG Migration
Use `sqlite3.connect("file:...?mode=ro&immutable=1", uri=True)` for read-only Docker mount.
For migration, use `src.backup(dst)` to create clean copy — immutable mode prevents WAL corruption.

## Scrapling Timeout Bug
Scrapling `fetch(url, timeout=X)` expects MILLISECONDS. Code passed 45 (seconds) → interpreted as 45ms.
Fix: `timeout=int(timeout_seconds * 1000)`. This was silently failing ALL Scrapling attempts.

## Direct Fetch Optimization
- Add Sec-Fetch-Dest/Mode/Site headers (reduces 403 from 60% → 20%)
- ClientPool per domain for cookie persistence (no tldextract, use urlparse)
- Retry on 408/429/5xx (NOT 403) with exponential backoff
- Remove br from Accept-Encoding (keep gzip, deflate)
- Remove zh-CN from Accept-Language (en-US only)

## Docker Deployment Rules
- ALL Docker builds on cloud VPS, NOT local Windows
- `docker compose up -d --build` on 100.107.117.23
- After rebuild: `docker compose restart nginx` to clear stale upstream cache
- --no-cache builds exhaust 3.9GB RAM → avoid unless necessary

## Pipeline Fixes
- pipeline.py --fetch SQL: check `content_md IS NULL OR content_md = ''` not just `nc.id IS NULL`
- batch.py creates placeholder rows with empty content → need to catch both conditions
- auto-pipeline.py timeout: 480s for batch.py (200 URLs × cascade time)

## Geo Monitor SVG Performance
At 1000+ events, react-simple-maps SVG performance degrades.
Mitigation: region/type/limit filters on Geo Monitor page. Default Top 50.
V2 fix: MapLibre GL JS (WebGL canvas, not SVG).

## Git Workflow
- Main repo: hermes-agent-backup (pipeline + web code)
- Platform repo: news-platform-v8 (standalone deployable)
- Both must be committed after every change
- Large binaries (>.rar, .zip) cause push failures → .gitignore them

## PG Events Table
Full columns needed for event_registry sync:
evidence, source_chain, timeline, article_ids, doc_refs, actors, keywords,
related_entities, llm_analysis, subject_name, subject_type, action_type,
action_detail, object_name, object_type, location_country, primary_source_id,
source_count, article_count, coherence, first_seen, last_updated, extraction_method

ALTER with: `ALTER TABLE events ADD COLUMN IF NOT EXISTS {col} JSONB`

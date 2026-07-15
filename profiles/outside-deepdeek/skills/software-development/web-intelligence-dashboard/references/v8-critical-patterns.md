# V8 Critical Patterns — Do Not Repeat

## Scrapling Timeout Unit Mismatch
`fetchers.py` passes timeout in SECONDS but Scrapling's `StealthyFetcher.fetch()` expects MILLISECONDS.
Fix: `resp = fetcher.fetch(url, timeout=int(timeout * 1000))`. Without this, all Scrapling attempts fail in 45ms.

## Direct Client Pool (Cookie Persistence)
Domain-isolated httpx.Client pool with LRU eviction. Thread-safe via `threading.Lock`. Module-level singleton.
Only applies to `fetch_direct` — NOT archive/google_cache/scrapling/browser.
Uses `urlparse` for domain extraction (no tldextract dependency).

## Article Time Fallback Chain
PG articles may have NULL `published_at`. Use 3-level fallback:
1. `published_at` (RSS original publish date)
2. `fetched_at` (when content was fetched)
3. `created_at` (when ingested into DB)

## PG Content Push-Back Gap
Pipeline pushes articles to PG during sync (metadata only). Content fetched later by batch.py stays in SQLite.
Fix: add Step 2.5 in auto-pipeline.py that POSTs articles with `content_len > 0` to `/internal/news/batch`.

## V8 URL Prefix Convention
Old-platform routes (news, auth, admin, ads, categories) are served WITHOUT `/api/` prefix.
Only Sentinel V1 routes use `/api/v1/`. Frontend pages must use `/news/hot`, `/auth/login`, `/admin/dashboard`.

## Dynamic Import Failures in Docker Builds
`import("maplibre-gl")` and dynamic D3 sub-package imports fail in Next.js Docker builds.
Always use static imports: `import maplibregl from "maplibre-gl"` + CSS import, `import * as d3 from "d3"`.
Remove individual d3 sub-packages — use the single `d3` umbrella package.

## Article Transition Page Pattern
Article detail pages should show AI-generated summary first, then a prominent CTA button linking to the original source.
Use `rel="noopener noreferrer nofollow"` on external links. VIP content expandable behind "Show Full Content" toggle.
This is a transition/intermediate page optimized for SEO and user flow — NOT a full-article display.

## auto-pipeline.py Architecture
6-step automated pipeline triggered by Hermes cron (15min):
1. Sync+Score (python -m news_intel.pipeline --hours 2, ~3s)
2. Fetch (batch.py, ThreadPoolExecutor, ~2-5min, timeout 480s)
2.5. Push articles with content to PG (HTTP POST /internal/news/batch)
3. Aggregate (aggregator.py, ~0.1s)
4. Cloud Sync (HTTP POST /internal/events/batch, ~5s)
5. Summary log

## SQLAlchemy 2.0 text() Wrapper
All raw SQL in FastAPI endpoints MUST be wrapped in `text()`:
```python
from sqlalchemy import text
db.execute(text("INSERT INTO events (...) VALUES (...)"))
```
Without `text()`, SQLAlchemy 2.0 raises "Textual SQL expression should be explicitly declared as text()".

## PG ALTER TABLE for V8 Dossier Fields
V8 events table needs 22 additional columns beyond the basic 12 from the old schema. 
Fields: article_ids, doc_refs, actors, keywords, related_entities, evidence, source_chain, timeline, llm_analysis (all JSONB),
plus SAO fields (subject_name, subject_type, action_type, action_detail, object_name, object_type),
plus location_country, primary_source_id, source_count, article_count, coherence, first_seen, last_updated, extraction_method, tone, goldstein.

## Geo Monitor SVG Performance Mitigation
When event count exceeds ~200, SVG WorldMap markers cause browser performance collapse. Mitigations before MapLibre migration:
1. Region filter (Middle East/Europe/Asia-Pacific/Americas/Africa)
2. Event type filter (Military/Diplomacy/Economic/etc.)
3. Limit selector (Top 25/50/100/All — default Top 50)
Keeps SVG rendering under 50 markers and defers WebGL migration.

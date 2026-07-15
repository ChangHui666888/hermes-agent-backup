---
name: sentinel-intelligence-platform
description: Build, deploy, and maintain the Sentinel Intelligence Platform — Event Dossier pipeline + unified Next.js web dashboard on cloud Docker.
version: 1.0.0
platforms: [linux, windows]
tags: [news-intelligence, event-aggregation, docker, nextjs, fastapi, postgresql, sqlite]
---

# Sentinel Intelligence Platform

End-to-end platform for news event intelligence: RSS pipeline → event aggregation → web dashboard.

## Architecture

```
Pipeline (Windows)              Web (Cloud Docker)
─────────────────              ──────────────────
RSS → Score → Fetch             nginx (:80)
     → Aggregate                 ├── /api/v1/* → FastAPI (PG)
     → Event Dossier             ├── /news/*, /auth/*, /admin/* → FastAPI
                                 └── /* → Next.js 16

Data: PostgreSQL (articles, users, ads, settings)
      + events, entities, sources (event_registry migrated from SQLite)
```

## Key Rules

1. **No local builds** — all Docker builds and deployment on cloud VPS only
2. **No hardcoded secrets** — INTERNAL_TOKEN and JWT_SECRET in .env (gitignored)
3. **No SQLite on cloud** — PG is the single data source
4. **No SFTP** — HTTP POST /internal/events/batch for data sync
5. **Git after every task** — `git add -A && git commit && git push` after each phase
6. **Browser verify** — test all pages in browser, not just API curl
7. **Zero LLM** — aggregation pipeline uses pure rules, no API calls

## API Prefix Rule

V8 unified backend serves old-platform routes WITHOUT `/api/` prefix:
- `/news/`, `/news/hot`, `/news/latest` (not `/api/news/`)
- `/auth/login`, `/auth/me` (not `/api/auth/`)
- `/admin/dashboard`, `/admin/pipeline/config` (not `/api/admin/`)

Sentinel routes KEEP `/api/v1/` prefix:
- `/api/v1/dashboard`, `/api/v1/events`, `/api/v1/sources`, `/api/v1/search`, `/api/v1/map/events`

Nginx config must explicitly proxy ALL backend routes:
```nginx
location /api/     { proxy_pass http://backend:8000/api/; }
location /internal/{ proxy_pass http://backend:8000/internal/; }
location /auth/    { proxy_pass http://backend:8000/auth/; }
location /admin/   { proxy_pass http://backend:8000/admin/; }
location /news     { proxy_pass http://backend:8000/news; }
location /news/    { proxy_pass http://backend:8000/news/; }
location /ads/     { proxy_pass http://backend:8000/ads/; }
location /categories { proxy_pass http://backend:8000/categories; }
```

## Project Structure

Single directory (no cross-directory build references):
```
news-platform-v8/
├── apps/api/          ← FastAPI backend (23 routes, PG)
├── frontend/          ← Next.js 16 (12 pages, 15 components)
├── docs/              ← Architecture, Deployment, V1 Acceptance
├── docker-compose.yml ← build: ./frontend + build: . + Dockerfile.backend
├── Dockerfile.backend ← python:3.12-slim, PYTHONPATH=/app
├── nginx.conf         ← proxy /api/*, /news/*, /auth/*, /admin/*, /ads/*
└── .env               ← INTERNAL_TOKEN, JWT_SECRET (gitignored)
```

## Deployment

```
# On cloud VPS:
cd /home/administrator/news-platform-v8
docker compose up -d --build
docker compose restart nginx  # after config changes

# Upload code from Windows (never build locally):
tar czf project.tar.gz --exclude node_modules --exclude .next --exclude __pycache__ .
# Upload via paramiko/SFTP, extract, then docker compose up -d --build
```

## Common Pitfalls

| Issue | Fix |
|-------|-----|
| Frontend pages empty (no data) | Check fetch URL prefix — old routes use `/news/` not `/api/news/` |
| Frontend "API unavailable" (Dashboard) | Page is Server Component; make it `"use client"` with useEffect fetch. SSR resolves `/api/v1` against `localhost:3000` which has no API |
| SQLite "unable to open database file" in Docker | Use `sqlite3.connect("file:/path?mode=ro&immutable=1", uri=True)` — immutable=1 prevents WAL/SHM file creation on read-only volume |
| 502 Bad Gateway | `docker compose restart nginx` (stale upstream cache) |
| SQLAlchemy 2.0 raw SQL error | Wrap in `text()`: `from sqlalchemy import text; db.execute(text("..."))` |
| PG FK cascade on DROP | Use `DROP TABLE ... CASCADE` for tables with FK dependencies |
| passlib bcrypt fails on Python 3.12 | Use hashlib.sha256 as fallback; pin bcrypt>=4.1 |
| GitHub push rejected (>100MB) | `git reset --soft HEAD~N; git rm --cached largefile; git commit` |
| GitHub push timeout | Files are too large; check with `git rev-list --objects` |
| Docker build cache stale | `docker compose build --no-cache frontend` |
| Port 80 conflict | Only one nginx on :80; old platform on alternate port |
| Next.js dev port conflict (Windows) | Port 3000/8648 EADDRINUSE: `taskkill //F //IM node.exe` then restart |
| `NEXT_PUBLIC_API_URL` not inlined | Hardcode `/api/v1` in fetch paths; add `env.NEXT_PUBLIC_API_URL` in next.config.ts |

## Task Plan Pattern

Always use structured phases with acceptance criteria:
1. **P0 Security**: Secrets migration, DB foundation
2. **P1 Backend**: Route unification, ingest endpoints
3. **P2 Auth**: bcrypt, JWT middleware
4. **P3 Frontend**: Page migration, AuthProvider
5. **P4 Migration**: SQLite → PG data transfer
6. **P5 Config**: Pipeline config page
7. **P6 Deploy**: docker-compose, cleanup old instances

Each phase: verify ALL endpoints, commit, push, then continue.

## Pipeline Health Check

Use `news_intel/pipeline_check.py` for Agent-readable diagnostics:

```bash
python pipeline_check.py check   # Full health: RSS→Scorer→Fetcher→Aggregator→SQLite→Sync→API
python pipeline_check.py run     # Full pipeline execution
python pipeline_check.py fetcher # Single stage
```

Output is YAML-style with STATUS, STAGE, RESULT, DETAIL, COMMAND, VERIFY fields.
First failed stage sets STOP=true; Agent reads COMMAND to fix, VERIFY to confirm.

## Workflow Rules

- **NEVER make changes without approval** — before modifying any file, present the plan and wait for explicit approval. If the user says "经过我同意没有？" or "回退", you made an unauthorized change. Use `git checkout -- <file>` to revert, then ask. This is the single most important rule. Applies especially to: domain_profiles, nginx, docker-compose, and production config files.

- **Don't over-polish** — when user says "不要继续打磨", stop immediately and move to the next task.
- **Don't deploy locally** — all builds and runs on cloud VPS. Windows is development only.
- **Undo on request** — when user says "马上撤销", use `git reset --hard HEAD~1 && git push --force` on both repos.
- **Verify with browser** — curl is not enough; use `browser_navigate` to confirm pages render with real data.
- **Commit after every task** — `git add -A && git commit -m "..." && git push` after each completed phase.

## Fetch Engine Pitfalls

### Scrapling timeout: milliseconds vs seconds
`Scrapling.StealthyFetcher.fetch(url, timeout=...)` expects **milliseconds**, not seconds.
Passing `timeout=45.0` (45s) is interpreted as **45ms**, causing instant timeout.
**Fix**: `resp = fetcher.fetch(url, timeout=int(timeout * 1000))` — located in `core/fetchers.py`.

### Aggregator: JSON string entities
The `entities` field in `news_intelligence` is stored as a **JSON string**, but `aggregator.py` expects a **dict**.
When aggregator calls `e.get("companies", [])` on a string, it raises `AttributeError: 'str' object has no attribute 'get'`.
**Fix**: Add `if isinstance(e, str): e = json.loads(e)` before every entity access in aggregator.
This occurs in 5 locations: `build_fingerprint()`, `_compute_entity_idf()`, and `aggregate_events()` (3 times).

### Pipeline SQL: empty content rows
`pipeline.py` fetches articles with `LEFT JOIN news_content WHERE nc.id IS NULL`.
Articles with placeholder rows (id exists, content_md empty) are **skipped**.
**Fix**: `WHERE nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = ''`
This catches articles that had a row created but never fetched.

### Batch results import after timeout
When `pipeline.py` times out (300s subprocess limit), batch.py may have completed successfully
but the results in `_fetch_tmp.jsonl` were never imported into `news_content`.
**Fix**: Read JSONL manually and UPDATE news_content rows:
```python
with open('news_intel/_fetch_tmp.jsonl') as f:
    for line in f:
        l = json.loads(line)
        if l['ok']:
            db.execute('UPDATE news_content SET content_md=?, content_len=?, fetch_strategy=?, fetch_cost=?, fetch_at=datetime("now","localtime") WHERE article_url=?',
                       (l['content'], len(l['content']), l['strategy_used'], l['total_cost'], l['url']))
db.commit()
```

## References

- `references/pg-migration-pattern.md` — SQLite → PG data migration with upsert
- `references/sftp-to-http-sync.md` — Replace SFTP with HTTP POST for data sync
- `references/cloud-deploy-pattern.md` — Cloud deployment workflow
- `references/v8-architecture.md` — V8 architecture details
- `references/fetch-engine-optimization.md` — Fetch headers, retry, ClientPool, Scrapling timeout fix

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

## Deployment

```
# On cloud VPS:
cd /home/administrator/news-intel-web
docker compose up -d --build
docker compose restart nginx  # after config changes

# Upload code from Windows:
tar czf project.tar.gz --exclude node_modules --exclude .next .
# Upload via paramiko/SFTP, extract, then docker compose up -d --build
```

## Common Pitfalls

| Issue | Fix |
|-------|-----|
| Frontend pages empty (no data) | Check fetch URL prefix — old routes use `/news/` not `/api/news/` |
| 502 Bad Gateway | `docker compose restart nginx` (stale upstream cache) |
| SQLAlchemy 2.0 raw SQL error | Wrap in `text()`: `from sqlalchemy import text; db.execute(text("..."))` |
| PG FK cascade on DROP | Use `DROP TABLE ... CASCADE` for tables with FK dependencies |
| passlib bcrypt fails on Python 3.12 | Use hashlib.sha256 as fallback; pin bcrypt>=4.1 |
| GitHub push rejected (>100MB) | `git reset --soft HEAD~N; git rm --cached largefile; git commit` |
| GitHub push timeout | Files are too large; check with `git rev-list --objects` |
| Docker build cache stale | `docker compose build --no-cache frontend` |
| Port 80 conflict | Only one nginx on :80; old platform on alternate port |

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

# V8 Unified Architecture Pattern

Lessons from merging old news-intel-platform (Vue.js + PostgreSQL) with Sentinel V1 (Next.js + SQLite) into a single unified instance.

## Architecture Decision: Single PG Data Source

**Problem**: Old platform used PostgreSQL (articles, users, ads), Sentinel V1 used SQLite (event_registry). Two data sources = join impossible, dual maintenance, sync race conditions.

**Solution**: PostgreSQL becomes the single source of truth. Pipeline writes events via HTTP POST `/internal/events/batch` instead of SCP'ing the entire SQLite file.

## SFTP Retirement Pattern

Before (fragile):
```
cron-sync.py → aggregate_events() → SCP news_intel.db → SSH docker restart
```

After (atomic):
```
cron-sync.py → aggregate_events() → httpx POST /internal/events/batch → PG transaction
```

Benefits: no paramiko dependency, no file corruption from SCP, no container restart needed, immediate visibility after push.

## Key Migration Steps

1. **P0: Security first** — Audit all `.py` files for hardcoded secrets (`grep -rn "secret\|token\|password"`), migrate to `.env`, rotate all exposed values.

2. **P0: Recover PG data** — Check if `docker volume ls` shows the old `pgdata` volume. If yes, `docker compose up postgres` and `pg_dump --schema-only` before designing migrations.

3. **P1: Unify ingest** — Add `POST /internal/events/batch` alongside existing `POST /internal/news/batch`. Both use the same `INTERNAL_TOKEN` for auth.

4. **P1: Retire SFTP scripts** — Delete `sync-db-to-cloud.py`. Rewrite `cron-sync.py` to use `httpx.post()` instead of `paramiko` + `SCP` + `SSH`.

5. **P2: Upgrade auth** — Replace custom `hashlib.sha256` with `passlib[bcrypt]`. Keep backward compatibility for old hashes (auto-upgrade on login).

6. **P3: Port old pages** — Vue.js pages (Home, Detail, Category, Login, Admin, Search) → Next.js pages. VIP content masking based on JWT `user.level`.

## DB Migration Discipline

**Hard rule**: Use Alembic for ALL schema changes. Never hand-run SQL in production. Every schema change = one migration file, linked to ORM models.

Before:
```
models.py ☓ (out of sync with actual schema)
migrate_v1.sql (manual, no rollback)
```

After:
```
alembic revision --autogenerate -m "add event_registry fields"
alembic upgrade head
```

## Dual Instance → Single Instance Merge Decision

When evaluating whether to merge two platforms vs run them side-by-side:

1. **Can backends merge?** Same framework (FastAPI) → yes. Different → consider proxy.
2. **Can frontends merge?** Same framework (React/Vue) → yes. Different → must port pages.
3. **Can data sources merge?** Schema compatible → yes. Different DB engines → pick one as primary.
4. **Effort**: ~13h for full merge (P0-P6), vs 0.5h for side-by-side (two ports).

Rule: merge if backends share a framework AND the primary data source can absorb the secondary. Side-by-side is acceptable for prototypes but becomes technical debt in production.

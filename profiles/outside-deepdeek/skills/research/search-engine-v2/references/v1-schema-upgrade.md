# V1 Schema Upgrade (Event-centric)

## Migration Path

Article-centric → Event-centric PostgreSQL schema.

### Tables Added (11 new)
`sources`, `entities`, `categories`, `tags`, `events`, `insights`, `assets`, `article_entity`, `event_article`, `event_entity`, `article_category`, `article_tag`

### Migration Result (2026-07-11)
- 160 articles → 24 sources, 35 entities, 8 tags
- 210 article-entity links, 196 article-tag links
- Source: `articles.source_name` → `sources.name` lookup
- Entity: `articles.entities` JSON → `entities` table + `article_entity` links
- Tags: `articles.tags` JSON → `tags` table + `article_tag` links

### Key Pitfalls
- `metadata` is reserved in SQLAlchemy → rename to `extra`
- JSON columns: `::text::jsonb` cast needed when data stored as JSON strings
- `jsonb_each_text` fails on arrays → check `jsonb_typeof` first
- `ON CONFLICT` needs UNIQUE constraint → add constraint first
- psycopg2 `cur.execute()` returns None → use `cur.fetchall()` separately
- Docker internal: use `postgres` hostname, not public IP

### Cleanup
After migration verified: `DROP COLUMN source_name, source_domain, tags, entities, analysis, key_points`

# Hermes → SQLite → Wiki → Git Pipeline

> Pipeline pattern for auto-generating wiki pages from Hermes session data stored
> in SQLite state.db. Used by `scripts/llm-wiki-pipeline.py`.

## Architecture

```
Hermes Runtime
    │
    ▼  (every session writes to state.db)
SQLite (state.db)
    │  sessions table, messages table
    ▼
Pipeline Script
    │  1. Query recent sessions
    │  2. Extract topics (keyword taxonomy)
    │  3. Generate topic pages  →  topics/<slug>.md
    │  4. Generate session pages → entities/<slug>.md
    │  5. Build graph.json (typed edges)
    │  6. Rebuild data.json (wiki-graph.py)
    ▼
Git Commit
    ▼
Obsidian Vault (human layer)
```

## State DB Schema (Hermes default)

```sql
-- Core tables
sessions(id TEXT, title TEXT, started_at REAL, ended_at REAL,
         message_count INTEGER, model TEXT, input_tokens INTEGER,
         output_tokens INTEGER)
messages(id INTEGER, session_id TEXT, role TEXT, content TEXT,
         timestamp REAL, token_count INTEGER)
```

## Key Design Decisions

### Topic vs Session Pages
- **topics/** — Knowledge Layer: one page per domain concept, cross-linked to entities/skills
- **entities/** — Traceability Layer: one page per Hermes session, linked to parent topics
- Both layers use YAML frontmatter with `links:`, `tags:`, `model:` fields

### Topic Extraction
Map session titles to domain topics via keyword taxonomy:
```python
TOPIC_KEYWORDS = {
    "AI Agent":    ["ai agent", "agent", "autonomous", "multi-agent"],
    "SQLite":      ["sqlite", "database", "db", "state.db"],
    "Development": ["python", "git", "deploy", "install"],
}
```

### Graph Building
Use the 4-layer Knowledge Graph schema with typed edges:
- `is_a`: Concept → Topic
- `requires`: Skill → Concept
- `implements`: Entity → Concept
- `references`: Session → Topic
- `depends_on`: Concept → Concept

## SAT Health Check

Run `scripts/sat-health-check.py` after pipeline execution to verify integrity:
- SQLite: can connect and query sessions table
- Wiki: all pages have frontmatter and wikilinks
- Graph: nodes have correct types, edges have correct semantics
- Git: changes can be committed without conflicts

## Pitfalls

- **Column name mismatch:** Hermes state.db uses `started_at`/`ended_at` (REAL timestamps),
  not `created_at`/`updated_at`. Convert via `datetime.fromtimestamp()`.
- **WAL lock:** Running the pipeline while Hermes is active may hit WAL write contention.
  Use `--dry-run` first, or schedule during idle periods.
- **Session titles may be empty:** Always filter with `WHERE title IS NOT NULL AND title != ''`.
- **Graph deduplication:** When rebuilding graph.json, deduplicate edges by (source, target, type)
  to avoid exponential edge growth on repeated runs.

# SAT (System Acceptance Test) Methodology

> Based on ChatGPT-derived six-layer acceptance framework.
> Reference: `scripts/sat-health-check.py`

## The Six Layers

```
Task  →  Hermes Runtime  →  SQLite  →  LLM Wiki  →  Obsidian  →  Git  →  Graph  →  Recall
```

Each layer must pass independently for the system to be "running."

## Layer Details

### Layer 1: Hermes Runtime (Execution Layer)
- **Goal:** Verify Hermes can execute a skill and produce output
- **Tests:** CLI availability, config file, skill directory, state.db freshness
- **Fallback:** If Hermes runs in-process (no separate .exe), check state.db last-modified time instead

### Layer 2: SQLite (State Layer)
- **Goal:** Every execution adds records to the database
- **Tests:** DB file exists, core tables (sessions, messages) present, WAL mode active, CLI available
- **Schema check:** Hermes state.db has `sessions` table with columns: id, title, started_at, ended_at, message_count, model, input_tokens, output_tokens
- **Messages table:** id, session_id, role, content, timestamp

### Layer 3: LLM Wiki (Knowledge Layer)
- **Goal:** Each session produces a traceable wiki node
- **Tests:** Directory structure intact, core files present, page count >= 3, frontmatter on all pages, wikilink connectivity
- **Two-layer structure:**
  - `topics/` — Knowledge layer (abstract, semantic)
  - `entities/` — Traceability layer (concrete, session-sourced)

### Layer 4: Obsidian (Cognitive Layer)
- **Goal:** Knowledge is immediately visible in the human-facing tool
- **Tests:** .obsidian/ config exists, wikilink compatibility, vault root readability
- **Requirements:** Wikilinks enabled, Dataview plugin config ready

### Layer 5: Git (Version Layer)
- **Goal:** Every change is traceable and reversible
- **Tests:** Repo exists, commit history >= 3, worktree can be clean, commit/rollback works
- **Commit convention:** `pipeline: wiki sync [YYYY-MM-DD HH:MM] (N topics, M sessions)`

### Layer 6: Graph (Relationship Layer)
- **Goal:** Knowledge is interconnected, not flat
- **Tests:** graph.json exists, nodes >= 5, edges >= 5, semantic type diversity >= 2, auto-rebuild works
- **Required types:** meta, topic, entity, skill (4 node types)
- **Required edges:** contains, belongs_to, uses, references (4 edge types)

## Recall Test (Layer 7, Bonus)

- **Goal:** Knowledge from a previous session can be found and reused
- **Tests:** Topic pages have `links:` frontmatter, graph.json is queryable, data.json index exists
- **Query example:** `graph.json["edges"] where type == "contains"` retrieves all topic→entity relationships

## When to Run

1. After initial pipeline setup
2. After upgrading any component
3. Before declaring the system "working"
4. Weekly cron job for regression detection
5. After any manual wiki edit that might break the graph

## Expected Output

```
Layer 1: Hermes Runtime    ✅
Layer 2: SQLite            ✅
Layer 3: LLM Wiki          ✅
Layer 4: Obsidian          ✅
Layer 5: Git               ✅
Layer 6: Graph             ✅
Layer 7: Recall Test       ✅

System Healthy
```

Any layer with ⚠️ or ❌ means the cognitive pipeline is broken at that point.

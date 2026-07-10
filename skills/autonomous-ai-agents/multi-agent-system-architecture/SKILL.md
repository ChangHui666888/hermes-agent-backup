---
name: multi-agent-system-architecture
description: "Design patterns for multi-agent systems on Hermes: profile-per-role architecture, constitutional governance, tiered model routing, cost management, knowledge base partitioning, and modular pipeline construction. Not about task routing (use kanban-orchestrator) — about system architecture."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [multi-agent, architecture, governance, profiles, pipelines, cost-management]
    related_skills: [kanban-orchestrator, kanban-worker, plan, hermes-agent]
---

# Multi-Agent System Architecture

> Design patterns for building production multi-agent systems on Hermes.
> Covers the **architecture layer** — profile design, constitutional governance,
> model routing, cost management, knowledge partitioning, pipeline modularity.
> For **task routing** within the system, see `kanban-orchestrator`.

## Core Architecture: Profile-Per-Role

Each role team = one Hermes profile with:
- **Independent memory** — per-profile `memories/` and `state.db`
- **Independent skill/skill whitelist** — per-profile `skills/` directory
- **File & knowledge base permissions** — enforced via `terminal.cwd` and file path conventions
- **Independent model configuration** — per-profile `config.yaml` (provider + model)
- **Isolated cron jobs** — per-profile `cron/jobs.json`

### Minimum Viable Profiles for a 3-Flywheel System

| Profile | Role | Model | Toolset Notes |
|---|---|---|---|
| `c0orchestrator` | Master Control: task decomposition, dispatch, approval gate, human reporting | Anthropic (sonnet, cost-efficient) | Full — C0 needs to see everything to approve |
| `devteam` | Development: build tools/scripts/skills, CI/CD, deployments | DeepSeek (execution) + Anthropic (acceptance) | Full, but constrained by shadow CI |
| `medteam` | Media/Sentiment: content production, platform publishing, sentiment harvesting | DeepSeek + local Gemma | Web access for scraping; write to media_analytics/ only |
| `invteam` | Investment: data pipelines, quantitative research, simulated trading | DeepSeek (execution) + Anthropic (acceptance) | DB access for financial data; no real-money trading |
| `a1auditor` | Auditor: read-only monitoring of logs, costs, task health | Scripts preferred; Anthropic only on anomaly detection | **Strictly read-only** — no write-capable tools |

### Profile Setup Steps

```bash
# Create profile (clone from default to inherit API keys)
hermes profile create <name> --clone-from default --no-alias --description "role description"

# Set model routing
hermes -p <name> config set model.provider <anthropic|deepseek|llm>
hermes -p <name> config set model.default <model-name>

# Set working directory (AGENTS.md auto-inject from here)
hermes -p <name> config set terminal.cwd <path-to-role-cwd>

# Place AGENTS.md in the role's cwd so it auto-loads on session start
```

## Constitutional Governance (CONSTITUTION + AGENTS.md)

Three-layer governance that separates identity from role constraints from project conventions:

### Layer 1: SOUL.md (global identity)
- `~/.hermes/SOUL.md` — loaded into EVERY session (all profiles)
- Sets the system identity: "you are part of the X/Y/Z multi-agent team"
- Contains the **irreducible constraints** that apply to all agents:
  - Observer roles are read-only (cannot modify system state)
  - High-risk operations must be logged to governance.db and go through human approval
  - Token cost breaker cannot be bypassed
  - Investment lines simulate only (2% position / 5% stop-loss)
  - Cross-role collaboration prefers internal channels (Kanban/public DB/files)

### Layer 2: profile AGENTS.md (role constraints)
- One per role cwd (not shared, not in home)
- Loaded automatically when that profile starts from its cwd
- Contains: role's must-do, must-never-do, internal communication channels, preferred model routing

### Layer 3: CONSTITUTION.md (detailed governance document)
- Single source of truth in `workspace/system/CONSTITUTION.md`
- Human-readable, chapters by topic (vision, power boundaries, org structure, collaboration, knowledge governance, lifecycle)
- Referenced by SOUL.md and AGENTS.md; not auto-loaded (too long)
- Mirrored to Obsidian Vault `_governance/` for easy reference by human

### Template: SOUL.md tail appendage

```markdown
---
[Multi-agent system member] You are part of the <X/Y/Z> three-flywheel agent team.
You must obey the system constitution at workspace/system/CONSTITUTION.md:
- Observer-class agents are read-only (see/log/report only, never modify)
- High-risk operations must be logged to governance.db and approved by human
- Token daily cost breaker cannot be bypassed
- Investment line: simulated only (2% position / 5% stop-loss)
- Cross-role collaboration: prefer internal channels (Kanban / public DB / files), not LLM relay
```

### Template: AGENTS.md structure

```markdown
# AGENTS.md — <Role Name> (<Role Code>)

> Loaded by profile `<profile-name>`. Must obey CONSTITUTION.md.

## Who you are
<one-paragraph role description>

## What you must do
<numbered list of core duties>

## What you must NEVER do
<numbered list of red-line prohibitions — AI boundaries are more important than capabilities>

## Model routing
<which provider/model to use for which task class>

## Internal channels
<Kanban board, governance DB, wiki paths — never LLM relay>
```

## Model Routing Strategy

The most expensive provider should never be the default for execution. Route by task class:

| Task Class | Execution Model | Verification Model | Rationale |
|---|---|---|---|
| Architecture / Governance / Creative | Anthropic (opus or sonnet) | — | High-uncertainty, high-consequence |
| Explicit development / analysis | **DeepSeek** | Anthropic | DeepSeek is ~30× cheaper; Anthropic catches edge cases |
| Content rewriting / formatting | **DeepSeek** | — | High volume, low cost |
| High-frequency / deterministic | **Script (0 tokens)** or local Gemma | — | Cost-free; every script-gateable task should be scripted |
| Anomaly detection | **Script (0 tokens)** | Anthropic (only when triggered) | Scripts detect; only anomalies need LLM judgment |

**Principle**: if a task can be done by a deterministic script, it MUST be done by a script, not an LLM. This includes: data transformation, state recording, format validation, scheduled polling, record-keeping.

## Cost Management: Tiered Circuit Breaker

### Architecture
```
token_breaker.py (cron every 10m)
    │
    ├── pct < SOFT_PCT (default 80%) → normal operation (Anthropic)
    ├── SOFT_PCT ≤ pct < 100% → soft downgrade: Anthropic → DeepSeek
    └── pct ≥ 100% → hard lock: switch to local Gemma (free), lock all cloud API
```

### Implementation
- `token_breaker.py` reads Hermes `state.db` sessions table (has `estimated_cost_usd` per session)
- For providers Hermes doesn't price (e.g. DeepSeek), estimates from token counts using known pricing
- Soft downgrade calls `provider_switcher.py` (which **verifies target availability before switching**)
- Hard lock writes a lock file (`BREAKER_LOCKED`) with unlock time = next midnight
- Midnight auto-reset: lock expires → restore original provider
- All actions logged to `governance.db: high_risk_actions`

### Configuration
```bash
# In .env
TOKEN_DAILY_LIMIT_USD=10          # Hard limit (default)
SOFT_DOWNGRADE_PCT=80            # Soft threshold (default)
BREAKER_MODE=enforce             # enforce | detect (detect logs only)
```

### Provider Switcher
`provider_switcher.py` supports `--to anthropic|deepseek` with `--model` override.
**Always verifies target before switching**: sends a minimum completion to confirm the API is reachable and the key works. Refuses to switch if target is down (exits 2).

## Knowledge Base Partitioning (Obsidian Vault)

Physical directory isolation with role-based write permissions enforced by convention:

```
Obsidian Vault/
├── raw/                    # All agents: append-only writes, NO modification/deletion
│   ├── web_snapshots/      # Raw web page captures
│   ├── financial_reports/  # Earnings reports, regulatory filings
│   ├── code_repos/         # Code snapshots
│   └── media_sources/      # Image/video/audio material library
│
├── wiki/                   # DEV + INV only writes; MED read-only
│   ├── entities/           # Entity pages (companies, assets, projects)
│   ├── concepts/           # Concept pages (terms, methods, strategies)
│   ├── skills_index/       # Pipeline tools index
│   ├── dev_ops/            # Development deterministic knowledge
│   └── finance/            # Financial/quantitative knowledge
│
├── media_analytics/        # MED writes; INV reads (sentiment weighting)
│   ├── traffic_daily/      # Daily traffic data
│   ├── sentiment/          # Sentiment signals with timestamps
│   └── hot_topics/         # Trending topics
│
├── archive/                # Cold storage — out of core index
└── _governance/            # Constitution mirror + audit trail
    └── agents_md/          # All role AGENTS.md copies (for human review)
```

**Key principles**:
- `raw/` is immutable once written (append-only)
- `wiki/` is the "filtered signal" zone — no clickbait or noise from MED
- `media_analytics/` is the "transient signal" zone — time-decay matters
- Archive stale pages > 90 days without references to prevent context window bloat

## High-Risk Operation Logging

Every operation that changes system state must log to `governance.db: high_risk_actions`:

```sql
CREATE TABLE high_risk_actions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,                    -- ISO timestamp
    actor TEXT,                 -- which agent/script
    trigger_task TEXT,           -- kanban task ID or description
    action TEXT,                -- action type constant
    detail TEXT                 -- JSON payload with context
);
```

### Action type constants (examples)
- `SWITCH_PROVIDER` — model provider changed
- `LOCK_AND_SWITCH_TO_LOCAL` — cost breaker triggered hard lock
- `DOWNGRADE_ANTHROPIC_TO_DEEPSEEK` — soft threshold downgrade
- `CI_PROMOTE` — tool code promoted to production
- `CI_BLOCK_DEPLOY` — tool code blocked from deployment
- `ADD_DRAFT` — content published to WeChat drafts
- `PUBLISH_REJECTED_NO_DISCLAIMER` — content rejected for non-compliance
- `UNLOCK` — manual or auto unlock

## Pipeline Modularity

### Tool Interface Standard (.iface.json)
Every tool script in the system must have a companion `.iface.json` describing:

```json
{
    "name": "tool_name.py",
    "purpose": "One-sentence description",
    "owner_role": "devteam|medteam|invteam",
    "exec_command": "python tool.py [args]",
    "inputs": [{"name": "--in", "type": "file", "required": true, "desc": "..."}],
    "outputs": [{"name": "stdout|--out", "type": "text|file", "desc": "..."}],
    "return_codes": {"0": "success", "1": "error", "2": "rejected"},
    "dependencies": {"python": ["stdlib|pkg"], "env": ["API_KEY"], "services": []},
    "side_effects": "none|writes file|network request|modifies config",
    "governance_logged": false,
    "version": "1.0"
}
```

Validate with `tool_iface.py --validate tool.py`; index a directory with `--index <dir>`.

### Development Guardrails (Shadow CI)

Before any tool code reaches production, it must pass:

```
shadow_ci.py --candidate new_tool.py --target /prod/path.py --runs 10 --run-args=--selftest
```

Guarantees:
1. Copy to isolated temp directory (never modify production directly)
2. Run N times (min 10) under monitoring: timeout, non-zero exit, memory spike (>512MB), deadlock
3. ALL pass → atomic replace (backup old version first)
4. ANY fail → abort (production untouched), alert to ci_alerts.log + governance.db

### Domain Rate Limiting (for Scrapers)

Every tool that makes outbound HTTP requests to external APIs must use `RateLimiter`:

```python
from rate_limiter import RateLimiter
rl = RateLimiter(default_rpm=20)
if rl.acquire("https://api.example.com/resource"):
    # proceed with request
```

SQLite-backed sliding window (60 second), configurable per-domain RPM. Non-blocking mode available.

## Verification Checklist

After setting up a multi-agent system, verify before declaring done:

- [ ] Each role profile exists (`hermes profile list`) and has correct model routing
- [ ] Each role's AGENTS.md is in its cwd directory
- [ ] SOUL.md has the system identity + constitutional pointer appended
- [ ] CONSTITUTION.md exists in `workspace/system/` and mirrored to `_governance/`
- [ ] Token breaker cron is registered (`hermes cron list`)
- [ ] Governance DB has the required tables (`sqlite3 ... .tables`)
- [ ] Each pipeline tool has a valid `.iface.json`
- [ ] Shadow CI passes on a test candidate
- [ ] Rate limiter works (can block a burst of requests)
- [ ] Provider switcher can verify then switch (`provider_switcher.py --verify <provider>`)
- [ ] Knowledge base partitions exist with README permission rules

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
- **AGENTS.md at profile root** — `profiles/<name>/AGENTS.md` for Hermes auto-injection (NOT just in cwd)
- **Role-differentiated SOUL.md** — per-profile with role-specific constraints, not a global cookie-cutter

### AGENTS.md Deployment: Two Locations

**Critical: AGENTS.md must exist in TWO locations, not one.**

```
# ✅ Correct deployment
profiles/<name>/AGENTS.md         ← Hermes auto-injects this on session start
workspace/roles/<name>/           ← Working directory for file access (optional copy)

# ❌ Wrong deployment (detected in real-world audit)
workspace/roles/<name>/AGENTS.md  ← Agent can read it, but it's NOT auto-injected
profiles/<name>/AGENTS.md         ← MISSING! No auto-injection happens
```

The difference: AGENTS.md at the profile root is loaded into the system prompt automatically. AGENTS.md only in the cwd directory is just a regular file the agent might stumble on. Deploy via:

```bash
# deploy-agents.sh — copy from SSoT to each profile
cp "_governance/agents_md/C0-orchestrator.AGENTS.md" "profiles/c0orchestrator/AGENTS.md"
cp "_governance/agents_md/DEV-team.AGENTS.md" "profiles/devteam/AGENTS.md"
cp "_governance/agents_md/MED-team.AGENTS.md" "profiles/medteam/AGENTS.md"
```

### SOUL.md: Per-Role Differentiation (Not Cookie-Cutter)

All profiles must NOT share the same SOUL.md. Each role gets a differentiated version:

| Profile | SOUL.md must include | SOUL.md must NOT include |
|---------|---------------------|-------------------------|
| c0orchestrator | "You are the approval gate. Never self-approve your own cards." | Task execution details |
| devteam | "You build tools. Execute with DeepSeek, accept with Anthropic." | Media production rules |
| medteam | "You produce content. ❌ Never write to ~/wiki/. ✅ raw/ + media_analytics/ only." | CI/CD deployment rules |
| outside-deepdeek | "You search and fetch. Cron worker profile." | Multi-agent system membership |

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

# Set working directory
hermes -p <name> config set terminal.cwd <path-to-role-cwd>

# ⚠️ CRITICAL: AGENTS.md must be at TWO locations:
#   1. profiles/<name>/AGENTS.md — this is WHERE HERMES ACTUALLY LOADS IT
#      (auto-injected into system prompt at session start)
#   2. workspace/roles/<name>/AGENTS.md — for reference when agent starts in cwd
#
# The workspace/roles/ location is NOT sufficient alone — Hermes loads AGENTS.md
# from the profile root directory, not from terminal.cwd.
#
# Common pitfall: AGENTS.md exists in workspace/roles/*/ but NOT in profiles/*/
# → role instructions NEVER reach the agent. Always verify deployment.
cp _governance/agents_md/<role>.AGENTS.md profiles/<name>/AGENTS.md
```

### Deploy AGENTS.md from SSoT to All Profiles

Maintain a deploy script to sync from the single source of truth (e.g., Obsidian Vault `_governance/agents_md/`) to all profiles:

```bash
#!/bin/bash
# deploy-agents.sh — Sync AGENTS.md from SSoT to all Hermes profiles
# Run after any AGENTS.md update. Add to cron for auto-deploy.

SSOT="C:/Users/<user>/Documents/Obsidian Vault/_governance/agents_md"
HERMES="C:/Users/<user>/AppData/Local/hermes/profiles"

cp "$SSOT/C0-orchestrator.AGENTS.md" "$HERMES/c0orchestrator/AGENTS.md"
cp "$SSOT/DEV-team.AGENTS.md"        "$HERMES/devteam/AGENTS.md"
cp "$SSOT/MED-team.AGENTS.md"        "$HERMES/medteam/AGENTS.md"
# Add other profiles as needed
echo "[OK] AGENTS.md deployed at $(date)"
```

**Verification**: after deployment, check that each `profiles/<name>/` directory has a non-empty `AGENTS.md` file. Missing AGENTS.md is the #1 reason role-specific instructions don't reach the agent.`

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

## System Audit & Reconnaissance

> When asked to **scan/audit/recon** an existing multi-agent system (not design/build one).
> This section covers how to systematically discover and document a running system's architecture.

### Scan Order (10-step)

Proceed in this order for maximum parallelization and minimum guesswork:

| Step | What to Check | What You Learn |
|------|---------------|----------------|
| 1 | **Profile Inventory** — list all profiles, their models, gateway status | Profile names, active status, default models |
| 2 | **Config Sweep** — read each profile's `config.yaml` + `profile.yaml` | Model routing, terminal cwd, gateway config |
| 3 | **Cron Inventory** — read `cron/jobs.json`; check `cron/output/` directories | Scheduled jobs, run counts, last-run timestamps |
| 4 | **Script Inventory** — search for `.py` in `$HERMES_HOME/scripts/` | Pipeline scripts the cron jobs invoke |
| 5 | **Workspace Governance** — read `workspace/ENVIRONMENT.md`, `workspace/system/CONSTITUTION.md`, `governance.db` | System constitution, environment, audit trail |
| 6 | **Pipeline Tools** — search for `.iface.json` in `workspace/system/pipelines/` | Tool definitions, owned-by roles, side effects |
| 7 | **Usage & Costs** — Hermes Studio API for usage stats + available models | Token/cost totals, model breakdown, daily trend |
| 8 | **Knowledge Bases** — scan ALL locations (see pitfall below) | Dual-wiki state |
| 9 | **Skill Inventory** — list installed skills, check directories | Bundled vs custom skills, categories |
| 10 | **Channel Status** — read each profile's `channel_directory.json` | Platform bindings (often empty) |

### Pitfall: Dual Knowledge Base Discovery

When scanning a multi-agent system's knowledge layer, **always check BOTH locations**:

```
Location 1: LLM Wiki (Karpathy-style, ~/wiki/)
  ├── index.md         — Content catalog
  ├── topics/          — Knowledge layer
  ├── entities/        — Entity/session pages
  ├── concepts/        — Concept pages
  ├── guides/          — How-to pages
  ├── BOSS_Doc/        — Operations manual
  └── RSS-Digest/      — Daily RSS digest

Location 2: Obsidian Vault (Documents/Obsidian Vault/)
  ├── _governance/     — Constitution + AGENTS.md + KB_README
  ├── agents_md/       — Role definitions (C0/P0/DEV/MED/INV/A1)
  ├── raw/             — Images, video, audio (append-only)
  ├── wiki/            — Skills index, pipeline docs
  ├── media_analytics/ — Sentiment data (MED writes)
  ├── archive/         — Cold storage
  └── _index/          — Auto-generated comprehensive index
```

**Why both matter:**
- **LLM Wiki** = auto-generated technical KB, RSS digests, git-versioned, pipeline-fed
- **Obsidian Vault** = constitutional governance, role AGENTS.md mirrors, raw material library, quadrants with write-permission rules

Failing to scan either one produces an incomplete architecture picture. The Obsidian Vault contains the **constitutional layer** and **role definitions** that explain *how* the system is governed.

### Report Output Template

After the 10-step scan, structure the report:

```
# Architecture Analysis Report

## Overview — one-paragraph summary
## Hermes Engine Layer — version, providers, proxy
## Profiles & Role Architecture — table of profiles + models
## Cron Automation — table of jobs + run counts
## Pipeline & Tools — pipelines, tools, sample outputs
## Knowledge Bases — dual-wiki state
## Governance — constitution, db, breakers
## Cost Analysis — 30-day totals, model breakdown
## Capability Map — what works, what's missing
## Architecture Diagram — ASCII/structure hierarchy
## Key Findings — observations, gaps, paused items
```

### Other Scan Pitfalls

- **Cron jobs may be paused** — compare run count vs expected (epoch ÷ interval). 72 runs in 24 days needs scrutiny.
- **Empty channel_directory.json is informative** — platform bridges not configured yet. Report as finding, not error.
- **Usage stats can be bursty** — one big architecture day then weeks of cron-only. Normal multi-agent pattern.
- **AGENTS.md in Obsidian vs profile cwd** — governance mirror is for human review; the active injection file must be in the profile's working directory.

## Auditing an Existing Multi-Agent System

> **Inverse of the build workflow.** Use this when joining an existing system, doing a health check, or before planning upgrades.
> Rule: every read-only pass is cheaper than an LLM call — batch independent reads in parallel.

### Scan Order (breadth-first, parallelize independent reads)

```
① Profiles + Gateways        (hermes studio profiles list, gateway status)
② Cron jobs                  (hermes cron list, inspect job output dirs)
③ Workspace governance       (CONSTITUTION.md, ENVIRONMENT.md, governance.db)
④ Skills                     (skills_list, check pipeline tool .iface.json files)
⑤ Wiki / Knowledge bases     (ALL of them — check ~/wiki/ AND Obsidian Vault/)
⑥ Model providers + costs    (available_models, usage_stats, state.db)
⑦ External integrations      (connected services, platform channels, OAuth status)
```

### Pitfalls (from real experience)

1. **Never assume one wiki.** The user may have TWO (or more) knowledge bases in different directories — e.g. `~/wiki/` for LLM Wiki (technical knowledge, pipeline output) and a separate `Documents/Obsidian Vault/` for governance, raw materials, and skills index. Scan both explicitly.
2. **Profile channel_directory.json is a trap.** A profile may show `gatewayStatus: running` but have ALL channel arrays empty — meaning it can't receive or send messages on any platform. Always check `channel_directory.json` per profile.
3. **Usage stats reveal effective cost.** Look for models that burned tokens on a single day vs. zero-cost periods. In a healthy system, cron scripts and local models should handle the routine, and expensive cloud APIs only on high-uncertainty tasks.
4. **Transient cron job states.** A cron job may show "completed X times" but be in paused state — check both the count AND the most recent execution timestamp.
5. **GitHub/proxy pattern for blocked sites.** When external projects are behind a firewall (common in China):
   - Use `curl -sL --proxy http://127.0.0.1:10808 <url>` for raw files (README, YML)
   - Use Python `urllib.request` with a custom User-Agent for GitHub API trees
   - Prefer raw.githubusercontent.com over github.com for markdown content

### Gap Analysis Methodology

After scanning, compare current state against the architecture template (sections above). Score each dimension:

| Dimension | Good | Warning | Missing |
|-----------|------|---------|---------|
| Profiles | All roles have profiles with correct model routing | Profiles exist but channels/platforms not bound | Roles defined in constitution but no profile exists |
| Cron | All critical automations registered and running | Jobs exist but paused/stalled | No cron for core pipeline |
| Governance | CONSTITUTION + AGENTS + governance.db complete | Constitution draft exists but no governance logging | Not implemented |
| Knowledge | All partitions exist with content | Partitions exist but empty | Single wiki, no separation |
| Cost | 0-cost routine days, cloud only for high-value | Cloud API used for routine tasks | No breaker at all |
| Platform | Channels bound, messages flowing | Gateway running but no channels bound | Not connected to any platform |
| Pipelines | Tools have .iface.json, tested, versioned | Tools exist but no interface files | Ad-hoc scripts only |

### External Project Evaluation Pattern

When integrating an open-source project (like OpenWiki) into the existing system architecture:

1. **Read primary docs** — README, examples, API docs. Focus on architecture, not marketing.
2. **Map to existing capabilities** — what does it do that the current system already does? (Don't rebuild what works.)
3. **Identify complements** — what does it do that the current system lacks? (This is the gap.)
4. **Check compatibility** — model providers, file formats, auth methods, OAuth flows.
5. **Recommend staged adoption** — format first (OKF frontmatter), then connectors, then CI/CD.

### Reference Files

- `references/resilient-web-retrieval.md` — Patterns for accessing blocked external resources (GitHub, API docs) via SOCKS5 proxy from Hermes on Windows
- `references/openwiki-analysis-reference.md` — Summary of the OpenWiki CLI project evaluation (OKF format, connectors, CI/CD pattern, agent wiki injection)

## Verification Checklist

After setting up a multi-agent system, verify before declaring done:

- [ ] Each role profile exists (`hermes profile list`) and has correct model routing
- [ ] Each role's AGENTS.md is in **profile root** (`profiles/<name>/AGENTS.md`), not just cwd
- [ ] SOUL.md is **differentiated per role**, not a global cookie-cutter
- [ ] Each role's skill set is scoped to its responsibilities (not all roles same)
- [ ] Only 1 profile has cron jobs (the worker profile); others have ticker-only cron
- [ ] Knowledge base has been normalized: each class has SSoT, no duplicates
- [ ] Dual-wiki overlap detected and resolved per the SSoT mapping table
- [ ] CONSTITUTION.md exists in `workspace/system/` and mirrored to `_governance/`
- [ ] Token breaker cron is registered (`hermes cron list`)
- [ ] Governance DB has the required tables (`sqlite3 ... .tables`)
- [ ] Each pipeline tool has a valid `.iface.json`
- [ ] Shadow CI passes on a test candidate
- [ ] Rate limiter works (can block a burst of requests)
- [ ] Provider switcher can verify then switch (`provider_switcher.py --verify <provider>`)
- [ ] Knowledge base partitions exist with README permission rules

## Reference Files

- `references/dual-wiki-normalization.md` — Detailed double-wiki normalization patterns, audit commands, and Python scripts for deduplication and AGENTS.md deployment.

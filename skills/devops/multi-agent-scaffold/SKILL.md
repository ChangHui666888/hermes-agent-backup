---
name: multi-agent-scaffold
description: "Map an org chart onto Hermes: profiles as agent roles, Kanban as task dispatch, constitution as governance."
version: 1.0.0
author: agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [multi-agent, profiles, kanban, governance, constitution]
---

# Multi-Agent Scaffold on Hermes

Turn an organizational structure into running Hermes agents without building a custom framework. Each agent becomes an independent Hermes **profile** with its own memory, skill whitelist, file permissions, and model routing. Task dispatch uses the built-in **Kanban** queue (SQLite-backed, atomic claim, auto-block on failure). Constitutional governance is enforced via `SOUL.md` (global identity/constraints) + `AGENTS.md` per profile (role-specific rules).

## Scope

Use this skill when you need to build a team of autonomous agents where:

- Each agent has **different responsibilities, permissions, and model cost budgets**.
- Agents need an **auditable shared task queue** without LLM-mediated handoffs.
- There is a **constitution** that no agent can override — observation/execution separation, cost limits, approval gates.
- Cross-agent communication should happen via **shared DB/files** (inner lines), not by prompting each other.

Do NOT use this skill for:
- A single-agent assistant (use a single profile).
- Quick parallel subtasks (use `delegate_task` instead).
- Agents that exclusively talk to each other via natural language.

## Architecture

```
Human
  └─ SOUL.md (global constitution pointer)
       └─ Profile "orchestrator" → AGENTS.md
            │  Kanban dispatch (hermes kanban)
            ├── Profile "team-alpha" → AGENTS.md + model A
            ├── Profile "team-beta" → AGENTS.md + model B
            └── Profile "auditor" → AGENTS.md (read-only)
```

### Key mappings

| Org concept | Hermes primitive |
|---|---|
| Agent role | A named profile (`hermes profile create`) |
| Role constraints | `AGENTS.md` in profile's cwd directory |
| Global constitution | `SOUL.md` (appended with pointer to CONSTITUTION.md) |
| Task dispatch | Kanban board + dispatcher (`hermes kanban`) |
| Cross-agent data | Shared DB or files (inner lines — 0 LLM cost) |
| High-risk audit log | A shared `governance.db` every profile can write to |
| Model routing | Per-profile `config.yaml` `model.default`/`model.provider` |

## Setup Sequence

### 1. Define the constitution

Write a single `CONSTITUTION.md` covering:

- Core red lines: who can read vs execute, what requires human approval.
- Cost safety: daily budget, what happens when exceeded.
- Authority chain: who reports to whom, who holds the approval gate.
- Storage rules: which agents can write where.

Place it at a known path (e.g. `workspace/system/CONSTITUTION.md`). Mirror a copy into the KB vault.

### 2. Append global pointers to SOUL.md

Edit `~/.hermes/SOUL.md` to append a multi-agent preamble at the bottom (do NOT overwrite the existing identity):

```
---
[Multi-agent system member] You are part of a multi-agent team.
Obey CONSTITUTION.md at <path>: read-only agents never modify,
high-risk ops are logged and require human approval,
cross-agent communication uses shared DB/files (inner lines), not LLM pass-through.
```

SOUL.md is injected into every session regardless of the active profile.

### 3. Create one profile per role

```bash
# Clone from the default profile to inherit API keys and provider config
hermes profile create alpha --clone-from default --no-alias \
  --description "Two-sentence role description"

# Set model routing (Anthropic for governance, DeepSeek for execution, etc.)
hermes -p alpha config set model.default claude-sonnet-4-6
hermes -p alpha config set model.provider anthropic

# Set cwd to a role-specific workspace so AGENTS.md auto-loads
hermes -p alpha config set terminal.cwd "~/workspace/roles/alpha"
```

Create a dedicated role workspace directory with its `AGENTS.md`:

```bash
mkdir -p ~/workspace/roles/alpha
# Place AGENTS.md there — Hermes auto-injects it when the profile
# starts with that cwd
```

### 4. Write AGENTS.md per profile

Each AGENTS.md should answer:

- **Who you are**: one-sentence role summary + reporting line.
- **What you must do**: specific, actionable responsibilities.
- **What you must NOT do**: clear prohibitions (especially for read-only roles).
- **Model routing**: which provider/model to use and when (e.g. "DeepSeek execute, Anthropic verify").
- **Inner lines**: which shared DBs/files to read/write.
- **Cost discipline**: tips for minimizing token burn.

Read-only agents (**critical red line**) must have one additional section:

```
## You can only do four things: see, record, report, prepare.
- ❌ You must NEVER modify, delete, or fix anything autonomously.
- ❌ You must NEVER execute any state-changing operation.
- Your anomalies are reported to the orchestrator, never auto-repaired.
```

### 5. Initialize Kanban

```bash
hermes kanban init
hermes kanban boards create my-stream \
  --description "Description of this work stream"

# Switch to the board
hermes kanban boards switch my-stream
```

The dispatcher ticks every 60s (config: `kanban.dispatch_interval_seconds`) and automatically assigns ready tasks to the configured profile. Tasks are claimed atomically; failed tasks auto-block after `kanban.failure_limit` consecutive failures.

### 6. Seed the knowledge base

If using Obsidian, create the four zones described in the constitution:

```
Obsidian Vault/
  raw/             — append-only source data (snapshots, feeds, reports)
  wiki/            — deterministic compiled knowledge (entities, concepts, skills index)
  media_analytics/ — ephemeral sentiment/hot-topic signals (physically separate from wiki)
  archive/         — cold storage for stale wiki pages (out of GraphRAG index)
```

Each zone gets a README.md defining who can write and who can read.

## Multi-Tier Cost Circuit Breaker

A common requirement: when the daily budget hits a soft threshold, downgrade from an expensive provider to a cheap one; when it hits the hard limit, switch to a free local model.

This is implemented as a standalone Python script that:

- Reads per-session cost from `state.db` (sessions table has `estimated_cost_usd`/`actual_cost_usd`).
- On cron tick (e.g., every 10min), calculates today's rolling total.
- At 80% (configurable): calls `provider_switcher` to downgrade from Anthropic→DeepSeek.
- At 100%: writes lock file, sets config to local model.
- At midnight auto-reset: clears lock, restores original provider.

A companion `provider_switcher.py` script handles **bidirectional switching with pre-verification**: before any toggle, it fires one real API completion to confirm the target provider is reachable. If the target returns HTTP 401/402/429 (key invalid, exhausted, rate-limited), the switch is **refused** and the config is left unchanged.

```bash
# Manual usage
python provider_switcher.py --status
python provider_switcher.py --to deepseek        # Anthropic→DeepSeek (with verification)
python provider_switcher.py --to anthropic       # DeepSeek→Anthropic (with verification)
```

## Pitfalls

1. **SOUL.md must NOT be overwritten** — append only. The existing identity text is Hermes's own. Losing it will break the agent's fundamental self-awareness.
2. **AGENTS.md loads by cwd, not by profile name.** Set `terminal.cwd` in each profile to a unique directory that holds that profile's AGENTS.md. Without this, the wrong (or no) AGENTS.md loads.
3. **Kanban dispatcher needs a running gateway.** Without a running gateway process, the dispatcher never ticks and tasks stay in 'ready' forever. Run `hermes gateway run` or install as a service.
4. **Cost circuit breaker only affects NEW sessions.** Already-running agent sessions have prompt-cached context and do not pick up model changes mid-conversation. A `/reset` or fresh `hermes` invocation is required.
5. **AGENTS.md caps at 20K chars.** If a role's constraints are very long, split into a concise AGENTS.md + referenced docs the agent can read on demand.

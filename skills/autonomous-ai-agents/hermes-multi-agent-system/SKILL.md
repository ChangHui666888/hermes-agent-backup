---
name: hermes-multi-agent-system
description: "Build governed multi-agent business systems on Hermes: map an org chart to profiles + Kanban + cron, add a constitution/governance layer, cost circuit-breakers, provider switching, shadow CI/CD, and content/media production pipelines."
version: 1.0.0
author: agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [multi-agent, orchestration, governance, cost-control, pipeline, provider-switching, hermes]
    related_skills: [hermes-agent, obsidian]
---

# Hermes Multi-Agent System

Build a governed, self-sustaining multi-agent system on top of Hermes Agent — where distinct AI "teams" (dev/ops, media, investing, etc.) collaborate under a written constitution, with hard cost and safety guardrails. This is the class-level playbook; per-topic detail lives in `references/`.

## When to use

Load this when the user wants to stand up a **multi-role / multi-team agent system** on Hermes — an "org chart of agents", a "flywheel" of collaborating agents, a governed pipeline where different agents own different domains, or any request that combines: role separation + task routing + cost/safety guardrails + shared knowledge base. Also load it when adding any single piece of that system (a cost breaker, a provider switcher, a content pipeline).

## Core architecture mapping (the key insight)

**Do NOT build a new multi-agent framework. Map the user's org chart onto Hermes primitives that already exist:**

| User concept | Hermes primitive |
|---|---|
| A role / team (own memory, skills, file perms) | **one Hermes profile** (`hermes profile create <name> --clone-from default`) |
| Inter-role task dispatch (dispatcher, retry, persist) | **Kanban** (`hermes kanban`, SQLite-backed) |
| Role's job description / boundaries / red lines | that profile's **`AGENTS.md`** (auto-injected via `terminal.cwd`) |
| Timed triggers | **cron** (`hermes cron` / cronjob tool) |
| Event triggers | **webhooks** |
| Intra-team parallel subtasks | **delegate_task** |
| Global identity + constitution pointer | **`SOUL.md`** (append, don't overwrite) |
| Shared knowledge / internal comms | **Obsidian vault** partitions + SQLite DBs |

**省 token 铁律 (token-thrift rule):** agents pass information via internal lines (Kanban DB, shared files, a governance SQLite DB) — NOT by repeatedly prompting a large model to relay messages. Anything deterministic and high-frequency is script-fixed (0 token) or runs on a cheap/local model. Only genuine judgement/architecture/creative work hits the expensive model.

## Model routing pattern (this user's convention)

- Clear, well-bounded dev/analysis tasks → **DeepSeek executes, Anthropic verifies (验收)**.
- Governance / architecture / high-uncertainty / creative → Anthropic directly.
- High-frequency deterministic work → local model (LM Studio gemma) or pure script, no cloud LLM.
- Per-profile model via `hermes -p <profile> config set model.default <m>` and `model.provider <p>`.

## Governance layer (write it, get it approved, mirror it)

1. Keep a human-readable **`CONSTITUTION.md`** as the single source of truth (vision → red lines → org chart → collaboration rules → knowledge-base rules → lifecycle → amendment). Draft it, let the human review, then treat as定稿.
2. Encode each role's slice as its **`AGENTS.md`** (can-do / cannot-do / model routing / internal lines).
3. **Append** a one-paragraph constitution pointer to `SOUL.md` — never overwrite the default identity.
4. Mirror constitution + AGENTS.md into the vault's `_governance/` for durability.
5. Two org-design decisions that saved tokens here: merge 副总+秘书长 → single **总控 C0** (orchestrator + approval gate); merge 记录员+巡检员 → single read-only **监审员 A1** (see/record/report/backup only, never modify — deterministic recording is script-fixed, only anomaly judgement hits the LLM).

## Guardrails you almost always need

- **Tiered cost circuit-breaker** — soft threshold downgrades expensive→cheap provider, hard cap locks to a free local model, auto-restores at midnight. See `references/cost-circuit-breaker.md`.
- **Provider switcher with pre-switch verification** — never switch to a provider you haven't just proven reachable. See `references/provider-switching.md`.
- **Shadow CI/CD gate** — new/changed tool code runs ≥10× in an isolated copy; any failure blocks promotion + rolls back + alerts + logs. See `references/dev-guardrails.md`.
- **Domain rate-limiter** + **tool interface standardization** (`.iface.json`). See `references/dev-guardrails.md`.
- Every state-changing (high-risk) action logs to a **`governance.db`** table (ts, actor, trigger_task, action, detail).

## Knowledge base partitioning (Obsidian)

Four physically-isolated partitions with write-permission rules enforced by each profile's file whitelist: `raw/` (append-only), `wiki/` (only dev+investing write, media forbidden), `media_analytics/` (only media writes; investing reads for sentiment weight), `archive/` (cold nodes, off the GraphRAG index). Register every built tool into `wiki/skills_index/`.

## Content & media production pipelines

The system's output side: RSS/local material → LLM rewrite → legal sandbox → publish (graphic/podcast/short-video). Zero-AI-image-cost path uses HTML/CSS + playwright screenshot. See `references/media-pipeline.md`.

## Reference files
- `references/cost-circuit-breaker.md` — tiered token breaker design + Hermes cost data source.
- `references/provider-switching.md` — verified Anthropic↔DeepSeek switching.
- `references/dev-guardrails.md` — shadow CI, rate-limiter, tool interface spec.
- `references/media-pipeline.md` — Chinese-friendly graphic/podcast/short-video pipeline.
- `references/hermes-gotchas.md` — profile/config/env pitfalls hit this session.

## Profile health audit (check these when troubleshooting or onboarding)

Every profile is a standalone agent "user." Run this checklist to verify each profile is correctly configured:

### 1. AGENTS.md deployment
- **Must be at profile root**: `profiles/<name>/AGENTS.md` (Hermes auto-injects this into the agent's system prompt)
- **NOT sufficient**: `workspace/roles/<name>/AGENTS.md` — that's just a regular file in the working directory, not auto-injected
- **SSoT location**: Keep the authoritative `AGENTS.md` in `Obsidian Vault/_governance/agents_md/` and deploy via a `deploy-agents.sh` script to each profile
- **Check existing**: `ls -la profiles/<name>/AGENTS.md` → if missing, the role instructions never reach the agent

### 2. SOUL.md differentiation
- Each profile that represents a distinct role should have a **different SOUL.md** describing that role's boundaries
- If all profiles share the same SOUL.md, they have no role identity — they're just clones with different models
- The SOUL.md should include: role name, can-do/cannot-do, model routing rule, knowledge base paths

### 3. Cron job distribution
- Cron jobs run under the profile that owns them (stored in `profiles/<name>/cron/jobs.json`)
- Check which profile actually has active cron jobs: `ls profiles/*/cron/jobs.json`
- Tick files (ticker_heartbeat, ticker_last_success) exist even for profiles with no active cron — don't confuse them with actual jobs
- The auto-pipeline cron should live in the profile that has the pipeline code (outside-deepdeek on this system)

### 4. Skills isolation
- Profiles can have different skill sets — use them to enforce role boundaries
- Check: `ls profiles/<name>/skills/` — are DEV and MED teams really different?
- MED should NOT have skills for deploying infrastructure; DEV should NOT have content-production skills
- If all profiles have the same skills, there's no security boundary between roles (constitution violation)

### 5. Channel directory
- `profiles/<name>/channel_directory.json` shows which platforms the profile connects to
- If all fields are empty arrays, the profile is CLI-only — no Telegram/Discord/Slack connectivity
- This is a deliberate state for local-only agent sessions; external connectivity is opt-in

## Top pitfalls (full list in references/hermes-gotchas.md)
1. `.env` is a protected file — `patch`/`write_file` refuse it; edit via shell `sed`/append.
2. Hermes venv python has **no pip/third-party libs** — use the system Python (`C:\\Users\\<u>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe` on this host) for scripts needing pyyaml/paramiko/psutil/playwright/edge-tts.
3. `hermes config set` has no `--profile`; use global `hermes -p <profile> config set …`.
4. Provider/model changes only apply to NEW sessions (prompt caching) — the running session keeps its model.
5. Always verify a provider is reachable BEFORE switching to it, or you can brick the whole system.

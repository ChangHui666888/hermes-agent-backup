---
name: ai-coding-agents
description: "Delegate coding tasks to external AI coding agent CLIs: Claude Code, Codex, OpenCode. Covers install, auth, one-shot tasks, interactive TUI sessions, PR reviews, parallel worktrees, and monitoring."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Automation, CI-CD, Refactoring, Delegation]
    related_skills: [hermes-agent, github-pr-workflow]
---

# AI Coding Agents — Orchestration Guide

Delegate coding tasks to external AI coding agent CLIs via the Hermes terminal.
This umbrella skill covers three supported agent CLIs, each with its own
installation, authentication, and orchestration patterns.

## Supported Agents

| Agent | CLI | Auth | Best for |
|-------|-----|------|----------|
| **Claude Code** | `claude` | `ANTHROPIC_API_KEY` or OAuth | Complex multi-step tasks, deep reviews |
| **Codex** | `codex` | `OPENAI_API_KEY` or OAuth | Quick one-shots, feature builds |
| **OpenCode** | `opencode` | Provider env vars (OpenRouter, Anthropic) | Provider-agnostic, open source |

## Installation by Agent

### Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude auth login  # browser OAuth, or set ANTHROPIC_API_KEY
claude --version   # requires v2.x+
```

### Codex

```bash
npm install -g @openai/codex
# OPENAI_API_KEY env var, or Codex OAuth
```

### OpenCode

```bash
npm i -g opencode-ai@latest
# brew install anomalyco/tap/opencode
opencode auth login
```

## Common Orchestration Pattern

All three agents follow the same two-mode pattern:

### Print Mode (One-Shot, Preferred)

```
terminal(command="<agent> <run|exec|-p> 'task description' [flags]", workdir="/project", timeout=120)
```

No PTY needed. Runs and exits. Use for:
- One-shot coding tasks (fix bug, add feature, refactor)
- CI/CD automation
- Structured output extraction

### Interactive PTY Mode (Multi-Turn)

Use `pty=true` + background for iterative sessions:

```
terminal(command="<agent> [flags]", workdir="/project", background=true, pty=true)
# Send prompts
process(action="submit", session_id="<id>", data="Implement OAuth refresh")
# Monitor
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")
# Exit
process(action="write", session_id="<id>", data="\\x03")
```

## Agent-Specific Details

### Section A: Claude Code (`skills/claude-code`)

See the full detailed skill at `autonomous-ai-agents/claude-code`.

**Install:** `npm install -g @anthropic-ai/claude-code`
**Print mode:** `claude -p 'task' --allowedTools 'Read,Edit' --max-turns 10`
**PTY:** Requires tmux for interactive orchestration. Dialog handling needed on first run (trust + permissions).

Key flags: `-p` / `--print` (one-shot), `--output-format json`, `--max-turns N`, `--dangerously-skip-permissions`, `--allowedTools`, `--model`, `--continue`/`--resume`.

**PR review:** `claude -p 'Review this diff' --from-pr N` or pipe `git diff | claude -p 'Review'`

**Settings hierarchy:** CLI flags > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`
**Memory files:** `~/.claude/CLAUDE.md` (global) > `./CLAUDE.md` (project) > `.claude/CLAUDE.local.md` (local)

### Section B: Codex (`skills/codex`)

See the full detailed skill at `autonomous-ai-agents/codex`.

**Install:** `npm install -g @openai/codex`
**Print mode:** `codex exec 'task'` (use pty=true)
**Requires git repo** — use `mktemp -d && git init` for scratch work.

Key flags: `exec "prompt"` (one-shot), `--full-auto` (sandbox auto-approve), `--yolo` (no sandbox).

**PR review:** Clone to temp dir, check out PR, `codex review --base origin/main`

**Parallel fixes:** Use git worktrees — one per issue — run Codex in each.

### Section C: OpenCode (`skills/opencode`)

See the full detailed skill at `autonomous-ai-agents/opencode`.

**Install:** `npm i -g opencode-ai@latest` or `brew install anomalyco/tap/opencode`
**Print mode:** `opencode run 'task'` (no pty needed)
**Interactive:** `opencode` with pty=true (background). Exit with Ctrl+C, NOT `/exit`.

Key flags: `run 'prompt'` (one-shot), `--file`/`-f` (attach files), `--thinking`, `--model`, `--agent` (build or plan).

**PR review:** `opencode pr N` or `opencode run 'Review PR' -f $(git diff --name-only)`

**Session management:** `opencode session list`, `opencode stats` for cost tracking.

## Parallel Work Pattern

Run multiple agent instances in isolated worktrees:

```bash
# Create worktrees
git worktree add -b fix/issue-78 /tmp/issue-78 main
git worktree add -b fix/issue-99 /tmp/issue-99 main

# Launch agents in each (background + pty)
terminal(command="codex exec --full-auto 'Fix issue #78'", workdir="/tmp/issue-78", background=true, pty=true)
terminal(command="opencode run 'Fix issue #99'", workdir="/tmp/issue-99", background=true, pty=true)

# Monitor
process(action="list")

# Clean up
git worktree remove /tmp/issue-78
```

## PR Reviews

### Quick Review (Print Mode)

```bash
git diff main...HEAD | claude -p 'Review this diff for bugs, security issues' --max-turns 1
```

### Deep Review (Worktree)

```bash
git fetch origin pull/N/head:pr-N
git checkout pr-N
claude -p 'Review all changes vs main' --max-turns 10
```

### Batch Reviews

```bash
git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'
claude -p 'Review PR #86' --max-turns 10
opencode pr 86
```

## Verification Checklist

- [ ] Agent CLI installed (`<agent> --version`)
- [ ] Auth configured (`<agent> auth status` or equivalent)
- [ ] Git repo exists (required by all agents)
- [ ] One-shot mode works for simple test task
- [ ] Workdir set correctly for the project
- [ ] Parallel sessions in separate worktrees/dirs

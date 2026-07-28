# OpenWiki Project Analysis

> Evaluation of [langchain-ai/openwiki](https://github.com/langchain-ai/openwiki) (13.3k stars, MIT license, TypeScript CLI)
> for integration into an existing Hermes multi-agent knowledge base.

## Project Overview

OpenWiki is a CLI by LangChain AI that "writes and maintains agent documentation for your codebase."
It generates and runs scheduled wiki-update PRs via a single `npm install -g openwiki` command.
Supports two modes: **code mode** (per-repo docs in `openwiki/` dir) and **personal mode** (personal brain in `~/.openwiki/wiki/`).

## Key Capabilities

| Capability | OpenWiki | Existing System (Hermes) | Gap |
|---|---|---|---|
| **Format** | OKF v0.1 (YAML type/title/description/tags) | Ad-hoc markdown, no standard frontmatter | ❌ Needs OKF injection |
| **Connectors** | Git, Notion, Gmail, X, Slack, Hacker News, Web (Tavily) | RSS only (98 sources via custom cron) | ⚠️ No OAuth connectors |
| **Auto-update** | GitHub Actions PR | cron → git commit | ✅ Existing is comparable |
| **AGENTS.md injection** | `<!--OPENWIKI:START-->` blocks | Manual AGENTS.md in cwd dir | ⚠️ Semi-complete |
| **Mermaid diagrams** | Auto-generated + validated + repaired | None | ❌ Missing |
| **CI/CD** | First-party workflow template | Custom shadow CI | ⚠️ Different approach |
| **Model providers** | 14+ (OpenAI, Anthropic, OpenRouter, Gemini, Bedrock, local) | 3-tier (Anthropic/DeepSeek/local) | ✅ Both support LM Studio |
| **Knowledge isolation** | None (single flat wiki) | 4-zone partitioned | ✅ Existing better |

## OKF v0.1 Format (the key takeaway)

OpenWiki uses Google's Open Knowledge Format — every concept page gets YAML frontmatter:

```yaml
---
type: Architecture overview | CLI usage | Workflow | Integration
title: "Page Title"
description: "One-line summary"
tags: [tag1, tag2, tag3]
timestamp: "ISO-date"
---
```

The root `openwiki/index.md` declares:
```yaml
---
okf_version: "0.1"
---
```

## Compatible Providers

OpenWiki natively supports LM Studio + DeepSeek — both already configured in the Hermes system:

```bash
# LM Studio (already running at localhost:1234)
OPENWIKI_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_API_KEY=<any-key>
OPENAI_COMPATIBLE_BASE_URL=http://localhost:1234/v1
OPENWIKI_MODEL_ID=google/gemma-4-e4b

# DeepSeek
OPENWIKI_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_API_KEY=<deepseek-key>
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com/v1
OPENWIKI_MODEL_ID=deepseek-v4-flash
```

## Recommended Staging

| Phase | Action | Reason |
|---|---|---|
| P0 | Inject OKF frontmatter into existing wiki .md files | Zero new tooling, immediate Agent retrieval improvement |
| P1 | Install OpenWiki, `personal --init` | Low-risk validation of integration |
| P2 | Add OKF output adapter to existing RSS scanner | Existing cron feeds OpenWiki without replacing it |
| P3 | OpenWiki code mode on hermes + wiki repos | Auto-generated codebase documentation |

## Avoid

- Do NOT replace the existing RSS pipeline — OpenWiki has no RSS connector.
- Do NOT use OpenWiki for governance/knowledge-partitioned content — it has no access control.
- Do NOT install via `bun` on Windows (needs C++ build tools for better-sqlite3); use `npm install -g openwiki`.

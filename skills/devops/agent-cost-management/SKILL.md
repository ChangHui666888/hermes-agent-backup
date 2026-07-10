---
name: agent-cost-management
description: "Multi-agent system cost management for Hermes: tiered token cost breaker, provider switcher with pre-verification, governance logging, cron-based monitoring, and cost-aware model routing. Covers the integration between cost monitoring and provider lifecycle."
version: 1.0.0
author: system (auto-architected)
tags:
  - cost-management
  - token-breaker
  - provider-switch
  - multi-agent
  - governance
  - hermessystems
platforms: [windows, linux, macos]
triggers:
  - user mentions 'token cost', 'API cost', 'spending limit', 'circuit breaker', 'budget cap', '熔断', '费用上限'
  - user asks to switch model providers (Anthropic ↔ DeepSeek ↔ local)
  - user wants to integrate cost control into an agent system
  - user encounters a 'cost too high' problem in a multi-agent workflow
  - setting up a new multi-agent system and needs cost guardrails
---

# Agent Cost Management — Multi-Agent System Cost Control for Hermes

## Core Principles

1. **Tiered reaction, not binary cutoff.** A hard cutoff at the limit is disruptive. Use a **soft threshold** (default 80% of hard limit) that downgrades to a cheaper cloud provider first, then a **hard threshold** (100%) that freezes all cloud API calls and switches to a free local model. This keeps the system running longer and avoids sudden total blackout.

2. **Verify before switching.** Never `hermes config set` a provider without first confirming it's reachable. Fire one real `minimal completion` (5 max_tokens, "ping" content) against the target API. If it fails (401/402/429/connection refused), **refuse the switch** and report why. A blind switch to a dead provider takes down the whole system.

3. **Governance logging is non-negotiable.** Every provider switch, threshold trip, lock, and unlock must be recorded in `governance.db: high_risk_actions` with timestamp, actor, trigger task, action taken, and detail. This is both audit trail and debugging aid.

4. **Cron-based autonomous monitoring.** A cron job every 5-10 minutes (no-agent mode, 0 token cost) checks current spend against limits. This catches runaway costs between human checks.

5. **Model routing by task type.** Not all tasks need expensive models. Classify work:
   - High-frequency / deterministic / formatting → **free script or local model** (0 cost)
   - Clear specification, low ambiguity → **cheap cloud (DeepSeek)** (~$0.28/M in, ~$0.42/M out)
   - Governance / architecture / high-uncertainty / acceptance review → **expensive cloud (Anthropic)** (~$3/M in, ~$15/M out)

## Architecture Overview

```
cron (every 10m)
  └─→ token_breaker.py
       ├── check daily spend from state.db (sessions.estimated_cost_usd)
       ├── if <80%:  nothing (full speed)                ──── 🟢
       ├── if ≥80%:  soft_downgrade()                     ──── 🟡
       │    └──→ Anthropic → DeepSeek (via provider_switcher with verify)
       ├── if ≥100%: hard_lock()                          ──── 🔴
       │    └──→ DeepSeek → local gemma (free, offline)
       │    └──→ write BREAKER_LOCKED file (unlock_ts = next midnight)
       └── if locked + midnight passed: auto_restore()    ──── ⏰
            └──→ restore original provider from saved state
                 └──→ clear lock file and soft-downgrade marker
```

## Key Components

### 1. token_breaker.py — Core monitor
```
python token_breaker.py --status                 # JSON status (total, limit, pct, locked)
python token_breaker.py --detect                 # read-only check, no config changes
python token_breaker.py --reset                  # manual unlock + restore provider
python token_breaker.py --no-soft                # disable soft threshold (hard-only)
```
- Reads `sessions.estimated_cost_usd` from `state.db` (Hermes native cost tracking)
- Falls back to token-count × price-per-model for providers without cost data (e.g. DeepSeek)
- Price table should be maintained in `PRICE_PER_M` dict
- Lock file `BREAKER_LOCKED` contains JSON with `locked_at`, `unlock_ts` (next midnight), `total_usd`, `limit_usd`, `breakdown`

### 2. provider_switcher.py — Safe provider lifecycle
```
python provider_switcher.py --to deepseek            # switch + verify + log
python provider_switcher.py --to anthropic            # switch + verify + log
python provider_switcher.py --verify anthropic        # check-only
python provider_switcher.py --profile devteam --to deepseek   # switch a specific profile
```
- **Model validation**: refuses models not in `known_models` list for that provider (exit code 3)
- **Pre-verification**: fires a real API call (5-token ping) before any config change
- **Failure detection**: decodes HTTP codes — 401=invalid_key, 402=quota_exhausted, 429=rate_limited, 403=forbidden
- **Governance logging**: `SWITCH_PROVIDER`, `SWITCH_REFUSED_TARGET_DOWN` in high_risk_actions

### 3. Cron-based monitoring
```bash
hermes cron create "every 10m" --script "token-breaker-cron.py" --no-agent --name "token-breaker"
```
- Cron entry script is a thin wrapper that calls the system Python (not Hermes venv, which may lack pyyaml)
- `no-agent` mode → 0 token cost, stdout is delivered directly

## Provider Price Table (example, adjust to your providers)
```python
PRICE_PER_M = {
    "deepseek-v4-flash": {"in": 0.28, "out": 0.42},
    "deepseek-v4-pro":   {"in": 0.55, "out": 2.19},
    "claude-opus-4-8":   {"in": 15.0, "out": 75.0},  # native cost from state.db
    "claude-sonnet-4-6": {"in": 3.0,  "out": 15.0},
    "_default_cloud":    {"in": 1.0,  "out": 3.0},
}
```

## Integration Points

### With provider switcher (loose coupling via subprocess)
```python
# token_breaker calls provider_switcher as a subprocess
subprocess.run([python, "provider_switcher.py", "--to", "deepseek", "--model", "deepseek-v4-flash"])
# provider_switcher handles verification + logging internally
```

### With governance database
```sql
high_risk_actions table:
  ts TEXT, actor TEXT, trigger_task TEXT, action TEXT, detail TEXT

daily_cost_log table:
  ts TEXT, day TEXT, total_usd REAL, limit_usd REAL, tripped INTEGER, breakdown TEXT
```

### With cron
- `token-breaker` cron (every 10m): runs `token_breaker.py` with default enforce mode
- `rss-scan` cron (every 5m): separate scanner, independent cost profile

## Configuration Knobs

| Env var | Default | Purpose |
|---|---|---|
| `TOKEN_DAILY_LIMIT_USD` | 10 | Hard cutoff amount |
| `SOFT_DOWNGRADE_PCT` | 80 | % of limit that triggers soft downgrade to cheaper provider |
| `BREAKER_MODE` | enforce | `enforce` or `detect` (read-only) |

## Pitfalls

1. **Current session doesn't switch mid-conversation.** Hermes preserves prompt caching — a config change only takes effect on *new* sessions (`/reset`). Notify the user that running sessions continue with the old provider until restarted.
2. **state.db cost may lag.** `sessions.estimated_cost_usd` is written when a session ends. Active long-running sessions may not have their cost reflected yet. The token-based fallback helps but underestimates.
3. **System Python vs venv Python.** The cron entry script must explicitly use the system Python (with pyyaml installed), not Hermes's venv Python which may lack pip/packages.
4. **Unlock at midnight is a timestamp, not a timezone-smart reset.** The script uses `datetime.datetime.now()` local time. If the system runs in UTC and the user expects CST, the unlock hour will be offset.
5. **Price estimates for uncosted providers.** DeepSeek and other third-party providers may show `cost_status: "unknown"` in state.db. The breaker must fall back to token-count × manual price table for these.
6. **Multiple profiles share the global config.** Switching the `default` profile's model affects all profiles that inherit from it. To isolate, set model per profile in `profiles/<name>/config.yaml`.

## Verification Pattern (reusable for any provider check)

```python
def verify_provider(provider, model):
    """Fire one minimal completion. Returns (ok, msg). Handles 401/402/429."""
    key = os.environ.get(f"{provider.upper()}_API_KEY")
    if not key:
        return False, f"{provider}_API_KEY not set"
    try:
        if provider == "anthropic":
            # Anthropic messages API
            resp = urlopen_with_timeout(anthropic_endpoint, {...}, timeout=25)
        else:
            # OpenAI-compatible chat completions
            resp = urlopen_with_timeout(openai_endpoint, {...}, timeout=25)
        data = json.loads(resp.read())
        if "choices" in data or "content" in data:
            return True, "OK"
        return False, f"unexpected response: {str(data)[:80]}"
    except HTTPError as e:
        hints = {401: "key invalid", 402: "quota exhausted", 429: "rate limited"}
        return False, f"HTTP {e.code} {hints.get(e.code,'')} {e.reason[:80]}"
```

## Related
- `hermes-agent` skill: provider setup, profiles, config, cron (builtin, bundled)
- `news-resilient-retrieval` skill: RSS fallback pattern for news scraping
- Constitution `CONSTITUTION.md`: governance rules for cost, security, and approval chains

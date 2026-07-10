# Dev/Ops Guardrails (Shadow CI, Rate-Limiter, Interface Spec)

The護欄 layer that lets a dev-agent write/modify tools without directly overwriting production.

## Shadow CI/CD gate (`shadow_ci.py`)
Rule: generated/changed tool code NEVER overwrites production directly. Instead:
1. Copy candidate into an isolated tempdir (the "shadow env").
2. Run it **≥10 times** (force min 10) with a self-test arg (`--run-args=--selftest`).
3. Monitor each run: timeout, non-zero exit, deadlock (comm timeout), memory-exceeded (peak RSS via psutil, cap e.g. 512MB).
4. Any failure → **block promotion, roll back (prod untouched), alert (log file + governance.db), exit 2** — don't even finish the remaining runs.
5. All pass → **atomic promote**: back up old prod file (`.bak.<ts>`), copy candidate to a `.tmp`, `os.replace` onto target.
6. `--no-promote` = validate-only (dry).
Governance actions: `CI_PROMOTE`, `CI_BLOCK_DEPLOY`, `CI_ALERT`, `CI_PASS_DRY`.
argparse gotcha: pass a leading-dash value as `--run-args=--selftest` (with `=`), not space-separated, or argparse eats it as a flag.

## Domain rate-limiter (`rate_limiter.py`)
Per-domain RPM cap (sliding 60s window) to avoid IP bans on scraped sites. SQLite-backed so it works cross-process. `acquire(url, blocking=True)` blocks until a slot frees or `max_wait` exceeded (returns False non-blocking). Per-domain overrides dict (e.g. seekingalpha=10, nitter=6, weixin=30, deepseek=60), default RPM otherwise. Importable as a library AND a `--check`/`--stats` CLI.

## Tool interface standardization (`tool_iface.py`)
Every tool ships a `<tool>.iface.json`: name, purpose, owner_role, exec_command, inputs, outputs, return_codes, dependencies, side_effects, governance_logged, version. Lets the orchestrator call tools by contract instead of reading source (省 token). `--validate` / `--scaffold` / `--index <dir>` (index exits 2 if any tool lacks a spec). Return-code convention across the system: 0=ok, 1=error, 2=validation/business reject, 3=compliance reject, 4=external-config missing (e.g. IP whitelist).

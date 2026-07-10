# Guardrail patterns: shadow-CI, rate-limiter, governance log

## Shadow-CI deployment gate (never overwrite prod directly)
Candidate code must survive isolated repeated runs before it can replace a
production file.

Flow:
1. Copy candidate into a fresh `tempfile.mkdtemp(prefix="shadow_ci_")`.
2. Run it N times (enforce N>=10 per constitution 2.3.2). Each run monitors:
   - **timeout** (kill + fail),
   - **nonzero exit** (fail, capture stderr tail),
   - **deadlock** (communicate timeout after process end),
   - **memory** peak via `psutil` (fail if > cap, e.g. 512 MB).
3. Any failure → **stop early**, alert (governance row + `ci_alerts.log`),
   leave prod untouched, `exit(2)`.
4. All pass → **atomic promote**: back up existing target to
   `target.bak.<ts>`, copy candidate to `target.tmp`, `os.replace(tmp, target)`.

Run the candidate's own `--selftest` as the exercised command. Pass it as
`--run-args="--selftest"` (with `=`; a space makes argparse consume it as a flag).

Verified behaviors: healthy tool → 10/10 promote+backup; crashing tool →
blocked on run 1; hanging tool → timeout-blocked; failures logged + alerted.

## Crawler RPM rate-limiter (prevent IP bans)
SQLite-backed sliding window (60s), one row per (domain, ts), shared across
processes. `acquire(url, blocking=True)` deletes rows older than the window,
counts recent hits for the domain, inserts+returns if under the per-domain RPM,
else sleeps until the oldest in-window hit ages out (respect a `max_wait`).
Per-domain caps in a dict; default for the rest. Importable as a library:
```python
from rate_limiter import RateLimiter
rl = RateLimiter(default_rpm=20)
rl.acquire("https://site.com/...")   # blocks until allowed
```
Test with a short window (`WINDOW=3.0`) so you can watch it actually block and
then release, instead of waiting a real 60s.

## Governance / high-risk audit log
One SQLite DB, table `high_risk_actions(id, ts, actor, trigger_task, action,
detail)`. EVERY state-changing action writes a row before/at execution: config
changes, deploys, publishes, trades, model swaps, breaker locks/unlocks. This
is the constitution's "no record → no execution" rule made concrete. Add a
`daily_cost_log` table for the breaker's trend. Dedup tables (e.g.
`media_picked_articles(link PK, ...)`) also live here so pipelines skip
already-processed items over the internal wire instead of re-reasoning.

## Tool interface standardization
Each tool gets `<tool>.iface.json`: `name, purpose, owner_role, exec_command,
inputs[], outputs[], return_codes{}, dependencies{python,env,services},
side_effects, governance_logged, version`. A validator scans a dir and reports
which tools lack a spec. The orchestrator then dispatches by contract (reads the
JSON), never by loading the tool's source — a concrete token saving.

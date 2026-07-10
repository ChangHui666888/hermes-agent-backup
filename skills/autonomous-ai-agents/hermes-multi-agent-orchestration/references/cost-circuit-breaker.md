# Token Daily Cost Circuit-Breaker — implementation notes

Goal: hard-cap cloud LLM spend per day. Trip at a USD limit, freeze cloud API
for new sessions by swapping the default model to a free local one, auto-unlock
at next local midnight, log every action to a governance DB.

## Where the cost data lives
Hermes' `state.db` already computes per-session cost. Table `sessions` has:
`model, billing_provider, input_tokens, output_tokens, cache_read_tokens,
cache_write_tokens, estimated_cost_usd, actual_cost_usd, cost_status, started_at`.
`hermes insights` derives from these. So the breaker does NOT need to hook the
API — it just aggregates `sessions` for today.

```python
midnight = datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
cur.execute("""SELECT model, billing_provider,
  COALESCE(actual_cost_usd, estimated_cost_usd, 0), cost_status,
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
  FROM sessions WHERE started_at >= ?""", (midnight,))
```

Key nuance: providers Hermes hasn't priced (e.g. deepseek) report cost 0 /
`cost_status='unknown'`. Back-fill those with your own per-1M-token price table
so they still count toward the cap. Trust `estimated`/`actual` when present and
>0; otherwise token-estimate. Bias high (safety).

## Trip behavior
- Write a lock file (JSON) with `unlock_ts = next local midnight`.
- In enforce mode: `hermes config set model.provider <local>` +
  `... model.default <local_model>`, after saving the previous values to a
  state file for restore.
- Log a high-risk row: `(ts, actor, trigger_task, action, detail)`.
- `sys.exit(2)` so cron output distinguishes a trip.
- Detect mode: log only, don't touch config.

## Auto-unlock
On each run, if the lock's `unlock_ts` has passed, restore the saved
provider/model and delete the lock. Manual `--reset` does the same immediately.

## Deploy
- Main script in the project workspace; a thin cron entry in
  `<hermes_home>/scripts/` that invokes it with the **system** python
  (hardcode the path — venv python lacks pyyaml/pip).
- `hermes cron create "every 10m" --script "<entry>.py" --no-agent --name token-breaker`
  → runs at 0 token cost, delivers stdout.

## Config-value precedence gotcha
Make `read_env` prefer `os.environ` over the `.env` file so tests/cron can
override the limit (e.g. `TOKEN_DAILY_LIMIT_USD=0.01`) without editing `.env`.

## Testing safely
Run trip tests against a **temp `HERMES_HOME`** (copy `state.db` in, fake a
`config.yaml`), so a real trip never mutates the live profile. A mid-session
model swap does NOT affect the current session (Hermes freezes model per session
for prompt caching) — only new sessions/cron pick up the change.

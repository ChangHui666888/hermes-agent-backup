# Tiered Token Cost Circuit-Breaker

Protects the API budget in a system where agents make long-chain, high-frequency LLM calls. Runs on a cron (`every 10m`, no-agent script mode, 0 token).

## Data source: where Hermes keeps cost
`~/.hermes/state.db` → table `sessions` already carries per-session cost columns:
`estimated_cost_usd`, `actual_cost_usd`, `cost_status`, `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_write_tokens`, `model`, `billing_provider`, `started_at`.
Sum today's rows where `started_at >= local_midnight` and prefer `actual`>`estimated`.
**Caveat:** Hermes may not price every provider — DeepSeek often shows cost 0 / `cost_status='unknown'`. Back-fill those with a token-based estimate (`PRICE_PER_M` table, in/out ¢/1M) so the breaker isn't blind. Bias estimates HIGH (safety first). `hermes insights --days N` uses the same table and is a quick human check.

## Three tiers (this is the useful shape)
1. **Normal** (<soft%): full-speed expensive model.
2. **Soft downgrade** (≥80%, `SOFT_DOWNGRADE_PCT`): switch Anthropic→DeepSeek to keep working cheaply-but-capably. Only acts when current provider is anthropic; drops a marker file so it doesn't re-fire. Calls the provider_switcher (WITH pre-switch verification).
3. **Hard lock** (≥ daily USD cap, `TOKEN_DAILY_LIMIT_USD`): write a lock file (with `unlock_ts` = next local midnight), switch default model→local free gemma, clear soft marker, log high-risk, exit 2.
4. **Auto-reset**: on any run past the lock's `unlock_ts`, restore the saved provider and remove lock + soft marker.

Save the pre-change provider/model to a state file so restore is exact. Log every LOCK / DOWNGRADE / UNLOCK / REFUSE to `governance.db.high_risk_actions`.

## Config knobs (read from .env or env, env wins for testing)
`TOKEN_DAILY_LIMIT_USD` (default 10), `SOFT_DOWNGRADE_PCT` (default 80), `BREAKER_MODE` (enforce|detect), `--no-soft`, `--detect` (read-only), `--reset`, `--status`.

## Testing without wrecking real config
The breaker calls `hermes config set`, which mutates real config. To test tier logic safely: monkeypatch `hermes_set` / `switch_via_switcher` / `_current_provider` / `save_prev_provider` and redirect `SOFT_MARKER`/`STATE_FILE` to tempdirs, then call the tier functions directly. For end-to-end, use a throwaway `HERMES_HOME` with a copied `state.db` and a fake `config.yaml`. Verified behaviors: soft acts only when anthropic; skips when already deepseek; hard-lock clears soft marker; expired lock auto-restores.

## Gotcha
`read_env()` must check `os.environ` FIRST, then the .env file — otherwise env-var overrides in tests silently don't apply.

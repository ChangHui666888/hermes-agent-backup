# Verified Provider Switching (Anthropic ↔ DeepSeek)

A one-shot script to swap Hermes' default provider/model when one is over-budget or down, and swap back when it recovers. **The whole point is: verify the target is reachable BEFORE switching**, so you never brick the system by pointing it at a dead provider.

## Must-have behaviors
1. **Model-name match check** — refuse a model that isn't in the target provider's known-models list (exit 3). Real names this session: anthropic = `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-fable-5`; deepseek = `deepseek-v4-flash`, `deepseek-v4-pro`.
2. **Pre-switch verification** — send a minimal real completion to the target and require success (exit 2 on failure, and DON'T touch config). HTTP status maps to cause: 402 = over-budget/quota, 429 = rate-limited, 401 = bad key, 403 = no permission. This is how "Anthropic超额" is detected automatically.
3. **Apply via** `hermes -p <profile> config set model.provider <p>` + `model.default <m>` (global `-p` prefix; `config set` itself has NO `--profile` flag).
4. **Log** the switch (and any refusal) to `governance.db.high_risk_actions`.
5. Multi-profile: `--profile <name>` targets a specific role.

## Verify endpoints
- Anthropic: `POST https://api.anthropic.com/v1/messages`, headers `x-api-key`, `anthropic-version: 2023-06-01`, body `{model, max_tokens:5, messages:[{role:user,content:"ping"}]}`. (Direct works on this host — no proxy needed for the API even though the chat model is proxied.)
- DeepSeek (OpenAI-shape): `POST https://api.deepseek.com/chat/completions`, `Authorization: Bearer …`. `GET /models` lists available model IDs.

## CLI shape
`--status` | `--to anthropic|deepseek [--model M] [--profile P]` | `--verify <provider>` | `--no-verify`.

## Reminder
Config change applies to NEW sessions only (prompt caching). Tell the user to `/reset` or open a fresh `hermes` session for the switch to take effect.

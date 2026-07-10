# China Proxy/Middleman Services for AI APIs

Known proxy/middleman services that relay Anthropic, OpenAI, and other AI API traffic to users behind the Great Firewall of China. Always test connectivity before accusing an API key of being invalid.

## 0011.ai (by HASSIUM LIMITED / affiliated with WildAI/bewild.ai)

| Property | Value |
|----------|-------|
| **Provider** | Hassium Limited (HK) |
| **Anthropic Base URL** | `https://aicoding.0011.ai` |
| **API Mode** | `anthropic_messages` (Anthropic Messages API compatible) |
| **Auth** | API key obtained from bewild.ai subscription |
| **Usage model** | Token-based or subscription |
| **Related site** | `https://bewild.ai/subscribe` for subscription |
| **Models** | Claude Opus 4.7, Claude Sonnet 4.6, GPT-5.4, etc. |

### Known Quirks
- Requires `ANTHROPIC_AUTH_TOKEN` env var in addition to `ANTHROPIC_API_KEY` (both set to the same value) for Claude Code CLI
- Uses a separate user token system — Anthropic-native API keys won't work here
- Error `"Token 不存在, record not found"` means the key isn't registered on this platform

### Setup in Hermes Studio
Use `hermes_studio_use_provider_add`:
- `base_url`: `https://aicoding.0011.ai`
- `api_mode`: `anthropic_messages`
- API key obtained from bewild.ai account

## apikey.fun (Fun API)

| Property | Value |
|----------|-------|
| **Provider** | apikey.fun operators |
| **Anthropic Base URL** | `https://api.apikey.fun` |
| **API Mode** | `anthropic_messages` |
| **Chat Completions Base URL** | `https://api.apikey.fun/v1` |
| **API Mode** | `chat_completions` |
| **Auth** | API key |
| **Models** | claude-sonnet-4-6, claude-opus-4-6, gpt-5.4, claude-haiku-4-5, etc. |

### Known Quirks
- Uses standard Anthropic API format at `https://api.apikey.fun/v1/messages`
- Error `"INVALID_API_KEY"` means the key is not recognized on this platform
- Separate subscription from 0011.ai — different user database

## Hermes Built-in Proxy Providers

Hermes ships with built-in provider presets for these services (visible in `hermes_studio_use_available_models` output):
- `fun-claude` → apikey.fun Anthropic endpoint
- `fun-codex` → apikey.fun Codex endpoint
- `opencode-zen` / `opencode-go` → OpenCode.ai proxy services
- `kimi-coding` → Kimi/Moonshot proxy

These builtin presets have empty API keys by default — the user must provide their own key.

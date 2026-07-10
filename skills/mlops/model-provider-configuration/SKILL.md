---
name: model-provider-configuration
description: "Configure, test, and troubleshoot AI model providers in Hermes Studio — API endpoints, credentials, proxy/middleman services, and connectivity verification."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [hermes, provider, api-key, anthropic, proxy, china, troubleshooting, configuration]
    related_skills: [hermes-agent]
---

# Model Provider Configuration

Configure, test, and troubleshoot AI model providers in Hermes Studio. Covers setting up API keys, choosing the right API mode, configuring custom/proxy endpoints, and handling connectivity restrictions (e.g. Great Firewall of China).

## When to Load This Skill

- User asks to "add a model" or "configure a provider"
- User provides an API key and wants it wired into Hermes
- API calls return 403 / "forbidden" / "invalid API key" — need to test and triage
- User needs to use a **proxy/middleman** service (e.g. for users in China)
- Checking or reviewing current provider/credential configuration

## Workflow

### 1. Check Current Provider Configuration

Use the Hermes Studio MCP tools to inspect what's already configured:

```python
# List profiles
hermes_studio_use_profiles_list(profile="default")

# List available models + providers for a profile
hermes_studio_use_available_models(profile="default")

# Get full config
hermes_studio_api_request(path="/api/hermes/config", profile="default")
```

### 2. Test API Connectivity Directly

Always test the API key with `curl` before configuring it in Hermes. This isolates credential issues from Hermes config issues.

**Anthropic Messages API** (api_mode: `anthropic_messages`):
```bash
curl -s --max-time 15 https://api.anthropic.com/v1/messages \
  --header "x-api-key: YOUR_KEY" \
  --header "anthropic-version: 2023-06-01" \
  --header "content-type: application/json" \
  --data '{"model": "claude-sonnet-4-6", "max_tokens": 50, "messages": [{"role": "user", "content": "hi"}]}'
```

**OpenAI Chat Completions** (api_mode: `chat_completions`):
```bash
curl -s --max-time 15 https://api.openai.com/v1/chat/completions \
  --header "Authorization: Bearer YOUR_KEY" \
  --header "content-type: application/json" \
  --data '{"model": "gpt-4o", "max_tokens": 50, "messages": [{"role": "user", "content": "hi"}]}'
```

**OpenAI Codex** (api_mode: `codex_responses`):
```bash
curl -s --max-time 15 https://api.openai.com/v1/responses \
  --header "Authorization: Bearer YOUR_KEY" \
  --header "content-type: application/json" \
  --data '{"model": "gpt-5.3-codex", "input": "hi"}'
```

### 3. Interpret Common Error Responses

| Error | Likely Cause | Next Step |
|-------|-------------|-----------|
| `"Request not allowed"` (403) | API key lacks model access, or is expired/revoked | Verify key on provider dashboard; try a different model |
| `"Invalid API key"` (401) | API key is malformed or not recognized | Check key format; verify it matches the target proxy |
| `"Token 不存在, record not found"` | Key not registered on the proxy/middleman service | User must subscribe/register first |
| Connection timeout | Network blocked or proxy needed | Try through a middleman endpoint |
| `"Insufficient quota"` | Account has exceeded rate/cost limits | Check billing dashboard |

### 4. Configure via Hermes Studio MCP

Use `hermes_studio_use_provider_add` to add or update a provider:

```python
hermes_studio_use_provider_add(
    profile="default",
    name="My Provider",           # Display name
    base_url="https://api.example.com",  # API endpoint
    api_key="sk-...",             # API key
    model="model-name",           # Default model to use
    api_mode="chat_completions",  # or: anthropic_messages, codex_responses, bedrock_converse
    providerKey="custom:my-provider",  # Provider key for custom providers
)
```

**API modes:**
- `chat_completions` — OpenAI-compatible `/v1/chat/completions`
- `anthropic_messages` — Anthropic `/v1/messages`
- `codex_responses` — OpenAI Codex `/v1/responses`
- `bedrock_converse` — AWS Bedrock Converse API
- `codex_app_server` — OpenAI Codex App Server

### 5. Update Default Model

After adding the provider, set it as the default for the profile:
```python
hermes_studio_use_provider_add(
    profile="default",
    name="...",
    base_url="...",
    api_key="...",
    model="model-name",
    api_mode="...",
)
```

## Pitfalls

- **China/GFW** — `api.anthropic.com` and `api.openai.com` may be unreachable from China. The "Request not allowed" error is often NOT an API key issue but network blocking. Always test through a proxy/middleman endpoint.
- **Duplicate keys** — Adding a provider with the same key twice via the MCP tool writes over the first. No "duplicate" warning is given.
- **Model names differ between direct API and proxy** — A proxy like `0011.ai` may use `claude-sonnet-4-6` while the actual Anthropic API expects a different string. Use the model names advertised by the proxy service.
- **API key vs AUTH_TOKEN** — Some services (0011.ai) require both `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` set to the same value. Hermes only needs the key in the provider config, but CLI tools may need both env vars.

## Known Proxy/Middleman Services (China)

See `references/china-proxy-services.md` for a curated list of known working proxy endpoints.

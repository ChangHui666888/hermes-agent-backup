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

## Hermes Dual-Process Proxy Architecture (Critical)

Hermes has **two independent HTTP client stacks** — they handle proxy env vars differently. This is the most common source of "works in CLI but not Web UI" connectivity issues.

| Process | HTTP Library | Auto-reads `HTTPS_PROXY`? |
|---------|-------------|---------------------------|
| **Python CLI** (`hermes` command) | `httpx.Client()` + `openai-python` SDK | ✅ **Yes** — httpx natively reads `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` env vars. If the env vars are set in the terminal session, the CLI routes through the proxy. |
| **Node.js Web UI / Gateway** (`hermes-web-ui`) | `undici.fetch()` / Node.js native `fetch` | ❌ **No** — Node.js's built-in `fetch` and `undici` do NOT automatically check proxy env vars. The gateway makes outbound API calls directly. |

**Consequence**: A user in China who sets `HTTPS_PROXY` in their terminal will find the Python CLI works fine (httpx routes through the proxy), but the Web UI / Studio / MCP tools may fail to reach blocked APIs because the Node.js gateway process ignores those env vars.

**Fix options:**
1. **Launch Web UI with proxy in the environment**: `HTTPS_PROXY=http://127.0.0.1:10808 hermes web-ui ...` or set it in the process environment before starting the service.
2. **Use a global HTTP agent** in Node.js: configure `globalDispatcher` for `undici` (requires code change to the Web UI startup).
3. **Use a third-party proxy/middleman** service that translates the blocked API endpoint to a reachable one (see `references/china-proxy-services.md`).

### Diagnostic Test: Isolate the Layer

When a provider fails, test at two layers to determine where the breakdown is:

```bash
# Layer 1 — curl (simulates any HTTP client, raw network)
curl -s --max-time 15 https://api.anthropic.com/v1/messages \
  --header "x-api-key: YOUR_KEY" --header "anthropic-version: 2023-06-01" \
  --header "content-type: application/json" \
  --data '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'

# Layer 2 — Python httpx (simulates Hermes CLI's HTTP path)
python3 -c "
import httpx, os
# Unset proxy to test direct connection
for k in ['HTTPS_PROXY','HTTP_PROXY','https_proxy','http_proxy']:
    os.environ.pop(k, None)
r = httpx.post('https://api.anthropic.com/v1/messages',
    headers={'x-api-key':'YOUR_KEY','anthropic-version':'2023-06-01','content-type':'application/json'},
    json={'model':'claude-sonnet-4-6','max_tokens':10,'messages':[{'role':'user','content':'hi'}]},
    timeout=15)
print(r.status_code, r.text[:200])
"
```

| curl OK | Python httpx OK | Diagnosis |
|---------|----------------|-----------|
| ❌ | ❌ | **Network blocking** — ISP/GFW. Add proxy. |
| ✅ | ❌ | Unlikely (same tcp stack). Check httpx version or proxy collision. |
| ✅ | ✅ | **Network is fine**. Issue is inside Hermes itself — likely Node.js gateway proxy gap. |

## Known Proxy/Middleman Services (China)

See `references/china-proxy-services.md` for a curated list of known working proxy endpoints.
See `references/hermes-proxy-architecture.md` for deep-dive on the CLI vs Gateway proxy behavior.

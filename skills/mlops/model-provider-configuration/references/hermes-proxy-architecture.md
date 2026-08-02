# Hermes Proxy Architecture: CLI vs Gateway

## Background

This document captures the key finding from a real troubleshooting session:

> **Question**: Why can't Hermes use DeepSeek API without opening the proxy?
> **Answer**: It depends on *which* Hermes process is making the API call.

## The Two Hermes HTTP Stacks

### Python CLI (`httpx`)

The Hermes agent CLI runs in Python and uses `httpx.Client()` plus the `openai-python` SDK for all provider API calls.

```python
# In agent/agent_runtime_helpers.py — create_openai_client()
client = _ra().OpenAI(**client_kwargs)  # Uses httpx internally
```

**httpx proxy behavior**: `httpx` automatically reads `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` environment variables (and their lowercase variants) when creating a `Client()` without an explicit proxy override. This is documented in the httpx docs as "Environment-Loaded Proxy Configuration".

Hermes also has a normalization layer in `utils.py`:
- `normalize_proxy_env_vars()` — rewrites `socks://` to `socks5://` for httpx compatibility
- `_validate_proxy_env_urls()` — validates proxy URL format before httpx sees it

**Result**: If `HTTPS_PROXY=http://127.0.0.1:10808` is set in the terminal session, the Python CLI transparently routes all API traffic through the proxy.

### Node.js Web UI / Gateway (`undici`/`fetch`)

The Hermes Web UI runs on Node.js and uses `undici` (Node.js's built-in HTTP library, exposed via `fetch()`).

**undici proxy behavior**: Unlike `httpx`, `undici` does **not** automatically read `HTTP_PROXY`/`HTTPS_PROXY` env vars. The `undici.fetch()` implementation (used as Node.js `fetch()` since v18) makes direct TCP connections unless the code explicitly configures a `ProxyAgent` via `globalDispatcher`.

The Hermes Web UI server does include some proxy-related code in its bundled `index.js` (minified), but this appears to be for **inbound** proxy support (the Web UI acting as a proxy server for incoming connections, e.g. for browser tooling) rather than **outbound** proxy support (routing API calls through a proxy).

## Real Test Data (Windows 10, China, ISP=联通/移动)

All tests done from `DESKTOP-IU8HLAO` (100.126.188.44) with DNS server 192.168.42.129:

### DeepSeek API (`api.deepseek.com`)

| Condition | Result | Timing |
|-----------|--------|--------|
| Direct connection (no proxy) | HTTP 401 | 0.25s total, 0.056s TCP connect |
| Via proxy 127.0.0.1:10808 | HTTP 401 | 0.16s total, 0.001s TCP connect |

**DNS resolution**: `api.deepseek.com` → `api.deepseek.com.eo.dnse1.com` → Chinese IPs (111.29.14.183, 36.131.221.89, etc.)

### Anthropic API (`api.anthropic.com`)

| Condition | Result | Timing |
|-----------|--------|--------|
| Direct connection (no proxy) | HTTP 403 | Reachable (varies by ISP/time) |

## Diagnostic Pattern

When a user says "it doesn't work without proxy", use this decision tree:

```
Does curl work without proxy?
 ├── YES → Network is fine. Check Hermes process type:
 │    ├── Python CLI? → Should work. Check env vars.
 │    └── Node.js Web UI? → Known gap. Set proxy in Web UI's environment.
 └── NO  → Provider is blocked. Must use proxy anyway.
```

## Key Environment Vars

```bash
HTTPS_PROXY=http://127.0.0.1:10808   # Hermes Python CLI reads this
HTTP_PROXY=http://127.0.0.1:10808     # Also read by httpx
ALL_PROXY=socks5://127.0.0.1:10808    # Optional, socks variant
```

Note: Hermes config.yaml has `env_passthrough` in the `terminal:` section that passes proxy vars to the *terminal backend* (subprocesses), but this does NOT affect the Web UI Node.js process.

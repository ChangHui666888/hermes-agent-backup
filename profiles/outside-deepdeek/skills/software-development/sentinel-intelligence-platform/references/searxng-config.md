# SearXNG Configuration for Internal API Access

## Problem

SearXNG Docker container returns 403 Forbidden on `/search?q=...&format=json` even though:
- Web UI works at browser
- `formats: [html, json]` is configured

## Root Causes

1. **`bind_address: "127.0.0.1"`** — Docker containers can't reach each other via localhost. Must be `"0.0.0.0"` for Docker network access.
2. **`public_instance: true`** — Enables bot protection that blocks API calls. Must be `false` for internal service.
3. **Environment variable override** — `SEARXNG_PORT` in docker-compose overrides yaml `port`. Actual listening port is from env var, not yaml.

## Fix

```yaml
server:
  bind_address: "0.0.0.0"
  limiter: false
  public_instance: false

search:
  formats:
    - html
    - json
```

Then `docker restart searxng-core`.

## Verification

```bash
curl "http://100.107.117.23:8080/search?q=test&format=json"
# Should return JSON with results array
```

## Pipeline Integration

```python
SEARXNG_URL = "http://100.107.117.23:8080"

resp = httpx.get(f"{SEARXNG_URL}/search",
    params={"q": title, "format": "json"},
    headers={"User-Agent": "NewsIntelBot/1.0"},
    timeout=10)
data = resp.json()
alt_urls = [r["url"] for r in data.get("results", [])][:2]
```

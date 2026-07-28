# Resilient Web Retrieval Behind Proxy

> Patterns for accessing blocked or firewalled external resources (GitHub, API docs, npm/pip registries) from Hermes on Windows via SOCKS5/HTTP proxy.

## Environment

- **Proxy**: 127.0.0.1:10808 (Clash/V2Ray SOCKS5 + HTTP)
- **OS**: Windows 11 via git-bash
- **Blocked sites common in China**: github.com, raw.githubusercontent.com, huggingface.co, api.github.com, pypi.org, npmjs.com

## curl (shell)

```bash
# Raw GitHub markdown files (preferred over github.com UI)
curl -sL --proxy http://127.0.0.1:10808 \
  https://raw.githubusercontent.com/langchain-ai/openwiki/main/README.md

# GitHub API
curl -sL --proxy http://127.0.0.1:10808 \
  "https://api.github.com/repos/langchain-ai/openwiki"
```

## Python urllib (for structured data)

```python
import urllib.request, json

req = urllib.request.Request('https://api.github.com/repos/langchain-ai/openwiki/git/trees/main?recursive=1')
req.add_header('User-Agent', 'hermes-agent')
req.set_proxy('http://127.0.0.1:10808', 'http')  # or 'https'

resp = urllib.request.urlopen(req, timeout=15)
data = json.loads(resp.read())
```

NOTE: `set_proxy` only sets the proxy for that specific request, not globally.
For global proxy in Python, set env vars `HTTP_PROXY`/`HTTPS_PROXY` before the interpreter starts.

## Global proxy via env vars

```bash
export HTTP_PROXY=http://127.0.0.1:10808
export HTTPS_PROXY=http://127.0.0.1:10808
export ALL_PROXY=socks5://127.0.0.1:10808
```

Scoped to a single command:
```bash
HTTPS_PROXY=http://127.0.0.1:10808 npm install -g openwiki
```

## URL Priority

When fetching from source repos:
1. **raw.githubusercontent.com** — best for markdown files (README, configs, examples). Fast, no auth, plain text.
2. **api.github.com** — for repository metadata (file trees, stats). Requires `User-Agent` header.
3. **github.com UI** — last resort (needs browser rendering, heavy). Use browser tools only for interactive pages.

## Known Issues

- SearXNG (self-hosted search engine) cannot do URL extraction — it's search-only.
- GitHub API unauthenticated calls are rate-limited to 60/hr. For heavy scanning, generate a GitHub token and pass `Authorization: Bearer <token>`.

## When to Add to a Skill's reference/

Write this pattern into a reference file the first time you discover and exercise it. After that, the skill's audit or setup section can link to it. Do NOT turn the proxy requirement into a blanket "tool X doesn't work" memory claim.

# Hermes Studio API Reference

Hermes Studio (Hermes' web UI) runs on port 8648. It's a Vue.js SPA that communicates with the Hermes backend via REST API.

## Base URL

```
http://localhost:8648/
```

## Public Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check — returns `{"status":"ok",...}` with agent bridge info |
| `/status` | GET | Returns the SPA HTML (root page) |
| `/api/health` | GET | Alias for /health |
| `/api/auth/status` | GET | Auth status |
| `/api/hermes/runtime-versions` | GET | Hermes runtime version info |

## Authenticated Endpoints

Most `/api/*` endpoints require authentication. Key API prefixes:

| Prefix | Purpose |
|--------|---------|
| `/api/hermes/profiles/*` | Profile CRUD, avatar, gateway control, restart |
| `/api/hermes/sessions/*` | Session CRUD, rename, export, workspace, messages/paginated |
| `/api/hermes/config` | Config read/write, credentials, auxiliary models |
| `/api/hermes/search/sessions` | Full-text session search |
| `/api/hermes/usage/stats` | Usage analytics |
| `/api/hermes/download` | File download |
| `/api/hermes/runtime-versions/*` | Runtime/webui version management |

## Frontend Route Discovery

The SPA is served from `/assets/js/index-<hash>.js`. To discover frontend routes:

```bash
curl -s http://localhost:8648/ | grep -oP 'src="[^"]*"' | head -5
# Find API endpoints in JS bundles:
curl -s http://localhost:8648/assets/js/index-D0gI7PCB.js | tr '.' '\n' | grep -i "api/v\|/api/" | sort -u
```

## Integration Patterns

### Embedding Custom Tools in Hermes Studio

Hermes Studio currently supports:
- **Plugin inventory** at `/plugins` page (read-only display of backend plugins)
- **Kanban** board for multi-agent work queue
- **Skills** management page
- **MCP** server management
- **Cron** job management

Custom tools can be added as:
1. **External web tool** — host your own web app on a different port and link to it
2. **Plugin** — write a Hermes backend plugin (limited UI integration)

### Health Check (Public)

```bash
curl -s http://localhost:8648/health
# {"status":"ok","platform":"hermes-agent","version":"v0.16.0","webui_version":"0.6.14","gateway":"running",...}
```

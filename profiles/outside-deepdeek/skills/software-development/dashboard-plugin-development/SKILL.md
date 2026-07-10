---
name: dashboard-plugin-development
description: Build and extend Hermes dashboard plugins — plugin manifest, backend FastAPI routes, frontend JS bundle, SDK component surface, and kanban plugin extension patterns.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, dashboard, plugin, frontend, kanban, SDK]
    related_skills: [hermes-agent, kanban-orchestrator]
---

# Hermes Dashboard Plugin Development

> How to extend the Hermes web dashboard with custom tabs, API endpoints, and modifications to built-in plugins (like kanban).

## Architecture Overview

A dashboard plugin lives at:

```
~/.hermes/plugins/<name>/dashboard/
├── manifest.json       # Plugin metadata — name, label, icon, routes
├── plugin_api.py       # FastAPI backend routes (mounted at /api/plugins/<name>/)
├── dist/
│   └── index.js        # Frontend JS bundle (React, pre-built)
└── (optional assets)
```

For **built-in plugins** (like kanban), the source lives in the Hermes repo under `plugins/<name>/dashboard/`. Modifications go directly there.

## Plugin Manifest (`manifest.json`)

```json
{
  "name": "kanban",
  "label": "Kanban Board",
  "icon": "columns",
  "routes": ["/board", "/tasks", "/config", "/toolsets"],
  "version": "1.0.0"
}
```

## Backend API (`plugin_api.py`)

Use FastAPI `APIRouter`:

```python
from fastapi import APIRouter, Query
router = APIRouter()

@router.get("/toolsets")
def list_toolsets():
    """API docs auto-generated."""
    return {"toolsets": sorted_names}
```

### Patterns

- Mount path is `/api/plugins/<name>/` (automatic via plugin system)
- Accept `board: Optional[str] = Query(None)` for multi-board support
- Use `withBoard(url, board)` helper on frontend to append `?board=<slug>`
- Return JSON dicts; FastAPI serializes automatically
- Errors: raise `HTTPException(status_code=4xx, detail="msg")`
- Import kanban_db, toolsets, config etc. lazily inside handlers

## Frontend SDK Surface

The dashboard exposes React components via `SDK.components`:

```javascript
const {
  Card, CardContent,
  Badge, Button, Input, Label,
  Select, SelectOption,
  Checkbox,     // newer hosts only; fallback to <input type="checkbox">
} = SDK.components;
```

Other SDK exports:
- `SDK.hooks`: `useState`, `useEffect`, `useCallback`, `useMemo`, `useRef`
- `SDK.utils`: `cn` (classnames), `timeAgo`
- `SDK.fetchJSON(url, options)` — authenticated fetch wrapper

### Using Select (single-select dropdown)

Follow the kanban plugin's established pattern:

```javascript
// Helper for wiring Select onValueChange to a setter
function selectChangeHandler(setter) {
  return {
    onValueChange: function (v) { setter(v == null ? "" : v); },
    onChange: function (e) {
      const v = e && e.target ? e.target.value : e;
      setter(v == null ? "" : v);
    },
  };
}

// Usage
h(Select, {
  value: currentValue,
  className: "h-8",
  onValueChange: function (v) { /* custom logic */ },
},
  h(SelectOption, { value: "" }, "Default option"),
  options.map(function (opt) {
    return h(SelectOption, { key: opt, value: opt }, opt);
  }),
)
```

### Hybrid Input + Select Pattern (for multi-select values)

When you need multi-select but only have single-select `Select`:

1. Keep a text `Input` for the comma-separated value
2. Add a `Select` dropdown labeled "Quick add…" below it
3. On selection, parse current value, append if not duplicate, join with `", "`

```javascript
h(Input, {
  value: tools,
  onChange: function (e) { setTools(e.target.value); },
  placeholder: "tools (optional, comma-separated): terminal, file, web",
})
h(Select, {
  value: "",
  className: "h-7 text-xs flex-1",
  onValueChange: function (v) {
    if (v) {
      const curr = tools ? tools.split(",").map(s => s.trim()).filter(Boolean) : [];
      if (!curr.includes(v)) { curr.push(v); setTools(curr.join(", ")); }
    }
  },
},
  h(SelectOption, { value: "" }, "+ add toolset\u2026"),
  availableOptions.map(function (opt) {
    return h(SelectOption, { key: opt, value: opt }, opt);
  }),
)
```

### i18n

```javascript
const { t } = useI18n();
tx(t, "i18nKey", "English fallback text")
```

All string literals that users see should use `tx(t, key, fallback)`.

## Common Plugin Dev Workflow

1. **Find the source**: built-in plugins at `<repo>/plugins/<name>/dashboard/`
2. **Backend**: edit `plugin_api.py` — add route, handler, Pydantic model
3. **Frontend**: edit `dist/index.js` — this is a bundled JS file, so edits are minified JS
4. **Data flow**: frontend calls `SDK.fetchJSON(withBoard(`${API}/endpoint`, board))` → FastAPI handler → returns JSON
5. **Restart**: dashboard must be restarted (`Ctrl+C` + `hermes dashboard`) to pick up backend changes; frontend changes are hot if the dashboard serves from disk

## Adding a New Task Field (Kanban Plugin)

This is the most common modification. Full reference: `skill_view(name="dashboard-plugin-development", file_path="references/kanban-plugin-add-field.md")`

### Steps summary

1. **Schema** — Add column to `SCHEMA_SQL` in `hermes_cli/kanban_db.py` + `_migrate_add_optional_columns` migration
2. **Dataclass** — Add field to `Task` dataclass + `from_row` deserialization
3. **DB API** — Add parameter to `create_task()`, include in INSERT, include in event payload
4. **Dispatcher** — If needed, pass the new field to the worker (via CLI flag or env var)
5. **CLI** — Add argparse argument to `hermes_cli/kanban.py` `build_parser`
6. **Tool** — Add parameter + schema to `_handle_create` in `tools/kanban_tools.py`
7. **Plugin API** — Add field to `CreateTaskBody` Pydantic model, pass to `kanban_db.create_task()`
8. **Frontend** — Add state + input element + submit logic in `dist/index.js` `InlineCreate` component
9. **Detail drawer** — Add display row in the task detail JSX

## Pitfalls

- **Minified JS editing**: `dist/index.js` is minified. Patches must match exact text including whitespace. Use `patch` tool, not terminal sed.
- **Bundle not source**: There's no React source at `plugins/kanban/dashboard/src/`. The `dist/index.js` IS the source. The web/ directory at the repo root is the main dashboard, not plugin-specific.
- **sdk.components.Checkbox** may be undefined on older dashboard hosts. Always use the fallback pattern: `const Checkbox = SDK.components.Checkbox || function(props) { return h('input', {type: 'checkbox', ...}); }`
- **Stale DB columns**: New schema columns need a migration in `_migrate_add_optional_columns()`. Without it, `create_task()` crashes with `OperationalError: table tasks has no column named X`.
- **selectChangeHandler** wraps `onValueChange`. If you need custom append logic, use `onValueChange` directly instead.

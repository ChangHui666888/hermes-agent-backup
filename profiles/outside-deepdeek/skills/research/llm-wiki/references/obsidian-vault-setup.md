# Obsidian Vault Setup & Troubleshooting

## Vault Registration

The wiki directory must be registered as an Obsidian vault at the **wiki root**, not the `.obsidian/` subdirectory.

### Correct vs Incorrect

| Scenario | Path in obsidian.json | Result |
|----------|----------------------|--------|
| ✅ Correct | `C:\Users\<user>\wiki` | Obsidian shows all markdown files, graph view works |
| ❌ Incorrect | `C:\Users\<user>\wiki\.obsidian` | Obsidian shows empty vault — only config files visible |

### Fixing the Registration

The vault list is at `%APPDATA%/obsidian/obsidian.json`. Locate the entry and fix the path:

```json
{
  "vaults": {
    "30571030dc4d50d6": {
      "path": "C:\\Users\\ChangHui\\wiki",     // ← fix this
      "ts": 1782629403297,
      "open": true
    }
  }
}
```

### Nested .obsidian/ Directory

When Obsidian opens the wrong path, it creates a **nested** `.obsidian/` directory:

```
wiki/
  .obsidian/              ← incomplete (no core-plugins.json, workspace.json)
    .obsidian/            ← created by the misconfiguration
      core-plugins.json   ← real config lives here
      workspace.json
```

**Fix:** Copy `core-plugins.json` and `workspace.json` from the nested directory up to the real `.obsidian/`, then delete the nested one. Clean up any `未命名.base` / `未命名.canvas` junk files.

## .gitignore for .obsidian/

Track config files (`app.json`, `obsidian.json`, `core-plugins.json`), ignore transient files:

```gitignore
# Obsidian - track config, ignore transient
.obsidian/workspace*
.obsidian/cache
.obsidian/*.base
.obsidian/*.canvas
.obsidian/appearance.json
.obsidian/plugins/*/data.json
.obsidian/graph.json
```

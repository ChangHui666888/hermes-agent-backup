# V2 Frontend npm Package Gotchas

## Dynamic vs Static Import in Docker Builds

**Do NOT use dynamic `import()` for npm packages in Docker builds.**

```tsx
// ❌ FAILS in Docker: 
import("maplibre-gl").then(m => { ... })

// ✅ WORKS:
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
```

The dynamic import silently fails with no error messages. The page renders but the component is blank.

## D3: Single Package, Not Sub-Packages

```json
// ✅ CORRECT — single package:
"d3": "^7.9.0"

// ❌ WRONG — sub-packages conflict:
"d3-force": "^3.0.0",
"d3-selection": "^3.0.0",
"d3-drag": "^3.0.0",
"d3-zoom": "^3.0.0"
```

```tsx
// ✅ CORRECT import:
import * as d3 from "d3";

// Then use:
d3.select(), d3.forceSimulation(), d3.forceLink(), d3.drag(), d3.zoom()
```

The sub-packages have version conflicts with the main `d3` package. Using just `"d3"` bundles everything.

## Deploy Checklist After npm Dep Changes

1. Upload package.json + all component files
2. `docker compose build --no-cache frontend` (force npm install)
3. `docker compose up -d frontend`
4. `docker compose restart nginx`
5. Browser verify: navigate to the page with the new component

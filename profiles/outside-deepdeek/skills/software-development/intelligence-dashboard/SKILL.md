---
name: intelligence-dashboard
description: Build data intelligence dashboards (FastAPI + Next.js + shadcn/ui) on top of existing pipelines. Freeze product definition before coding. Situational Awareness, not data statistics.
version: 1.0.0
metadata:
  hermes:
    tags: [dashboard, web, fastapi, nextjs, intelligence, situational-awareness]
---

# Intelligence Dashboard Development

Build web dashboards that consume existing pipeline data (SQLite, PostgreSQL). The output is an **intelligence product**, not a CMS or admin panel.

## Trigger conditions

Use this skill when the user asks to:
- Build a web dashboard/Frontend for a data pipeline
- "productize" pipeline output into a UI
- Create an "event intelligence" or "situational awareness" interface
- Design a React/FastAPI stack on top of existing event/data registries

## Frozen principles

### 1. Freeze before build

Before writing ANY component code:
- Freeze the API Contract (TypeScript interfaces + Pydantic models, mirrored)
- Freeze the Product Definition (page responsibilities, reading order, color spec)
- Freeze the "not allowed" list (things V1 explicitly excludes)

Output: `PRODUCT.md` or equivalent frozen spec. The user must approve before Task-001 begins.

### 2. Situational Awareness, not data statistics

Dashboards are NOT CRUD tables. Every component must help the user answer a specific awareness question in under 30 seconds:
1. Where are things happening? (geographic)
2. What's most important? (ranking/heat)
3. What just changed? (feed/timeline)
4. Is the system healthy? (pipeline status)

Components that only display counts without context are wrong.

### 3. Intelligence reading order

For detail/dossier pages, respect the analyst's reading order:
1. What happened + why it matters (header: title, summary, significance)
2. Facts (structured SAO: Subject/Action/Object/Location/Time)
3. Evidence (quotes with sources, verification level)
4. Evolution (timeline with stage progress, not just timestamps)
5. Information Flow (who broke it, who followed — NOT "Source Chain")
6. AI Intelligence (deeper analysis last, not first)

### 4. Color philosophy

- Background: dark warm-gray (#080B12), NOT blue
- Cards: blue-gray (#141925), NOT pure blue
- Emphasis: amber (#F59E0B), NOT blue
- Interaction: blue (#3B82F6) — links, buttons, hover
- Status: red (#EF4444) critical, orange (#F97316) high, green (#22C55E) stable

Avoid the "enterprise dashboard" look (excessive blue, white backgrounds, data tables everywhere).

### 5. Component naming

- "Information Flow" not "Source Chain" (intelligence analysis, not RSS tracking)
- "Evolution" not "Timeline" (shows stage progress, not just chrono list)
- "Intelligence Feed" not "Event Stream" (emphasises analyst value)
- "Global Situation" not "World Map" (the map is one representation; the concept is awareness)

## Tech stack (frozen)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | FastAPI (Python) | Shares venv with pipeline, reads SQLite directly |
| Frontend | Next.js 14+ (App Router) | Server components for data fetching |
| Styling | Tailwind CSS 4 + shadcn/ui | Dark theme, rapid iteration |
| Maps | react-simple-maps | No API key, offline-capable |
| Animation | framer-motion | Page transitions only |
| DB | SQLite read-only adapter | Reads pipeline's production DB directly |

Do NOT introduce PostgreSQL write models, ORMs, or migration tools in V1.

## Project structure

```
~/workspace/<project-name>/
├── PRODUCT.md                 # Frozen product definition
├── backend/
│   ├── main.py                # FastAPI with CORS
│   ├── db.py                  # SQLite read-only adapter
│   ├── models/schemas.py      # Pydantic (mirrors frontend contracts)
│   ├── api/
│   │   ├── dashboard.py
│   │   ├── events.py
│   │   ├── sources.py
│   │   ├── search.py
│   │   └── map.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── contracts/         # TypeScript interfaces (mirrors Pydantic)
│       │   ├── event.ts
│       │   ├── dashboard.ts
│       │   └── source.ts
│       ├── lib/
│       │   ├── api.ts         # fetchAPI<T> wrapper
│       │   └── types.ts       # re-exports from contracts/
│       ├── components/
│       │   ├── layout/        # Header, Sidebar
│       │   ├── event/         # EventCard, EventHeader, FactPanel, etc.
│       │   └── dashboard/     # WorldMap, EventHeat, IntelligenceFeed
│       └── app/
│           ├── page.tsx       # Dashboard
│           ├── events/
│           │   ├── page.tsx   # Explorer
│           │   └── [id]/page.tsx  # Detail
│           ├── map/page.tsx
│           ├── sources/page.tsx
│           └── search/page.tsx
└── TASKS.md                   # 8-task development plan
```

## Build sequence (frozen)

```
Task-001  Init + Design System + API Contract
Task-002  Layout (Header + Sidebar + routes)  ||  Task-003  FastAPI Adapter
Task-005  Event Detail page (core validation) ← BUILD FIRST
Task-004  Dashboard (situational awareness)
Task-006  Event Explorer
Task-007  Sources + Search
Task-008  UI Polish + QA
```

Build the detail page BEFORE the dashboard. This validates the data pipeline → UI chain with the most complex component first.

## Support files

- `references/product-definition-template.md` — Frozen product spec with page responsibilities, reading order, color palette, anti-patterns
- `templates/8-task-plan.md` — 8-task build sequence template, priority-ordered (Detail first, Dashboard second)

Every task must pass:
```
[ ] Build succeeds (npm run build / python main.py)
[ ] Renders real pipeline data (NOT mock data)
[ ] Loading state visible (skeleton)
[ ] Empty state effective (0 data case)
[ ] Error state effective (API down case)
[ ] Hover effects match design spec
[ ] All colors use CSS variables (never hardcoded hex)
```

## V2 Extensions (built on V1 foundation)

### Article Transition Page
For news aggregation dashboards, use the transition page pattern for external article links:
- AI Summary first (third-person factual description)
- Source metadata + entity tags  
- CTA button: "→ Read Full Article on [Source]" with `rel="noopener noreferrer nofollow"`
- VIP-only expandable full content toggle
- See `references/article-transition-page.md` in sentinel-intelligence-platform skill

### MapLibre Migration
When SVG performance bottlenecks (>200 markers): replace react-simple-maps with `maplibre-gl` + CartoDB Dark Matter (free CDN). Use static import — dynamic `import()` fails in Docker builds.

### Time Field Fallback
Article display time priority: `published_at → fetched_at → created_at`. Apply in backend route, not frontend.

## Anti-patterns (what NOT to build in V1)

- User auth / login systems
- CRUD management interfaces
- Raw article/row tables
- Chart libraries beyond react-simple-maps
- Agent Chat integration
- Knowledge graph visualization
- PostgreSQL write models or migration scripts
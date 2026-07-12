---
name: web-intelligence-dashboard
description: Build a Web Intelligence Dashboard on top of v4.4 Event Registry — FastAPI read adapter + Next.js dark theme frontend. Frozen API Contract first, SQLite read-only, Event Dossier as primary acceptance criterion.
tags:
  - web-dashboard
  - fastapi
  - nextjs
  - event-registry
  - sqlite-readonly
  - dark-theme
  - intelligence
  - news
---

# Web Intelligence Dashboard V1 — Build Workflow

## Context

Built on top of the **v4.4 Event Registry** (search-engine-v2 skill). 
The pipeline already produces Event Dossiers in `event_registry` SQLite.
This skill covers building a **read-only Web dashboard** that displays those dossiers — NOT a news website, but an **Event Intelligence Cockpit**.

## Sidebar Navigation (frozen v2)

5 sections, grouped by purpose:

```
RADAR      ◉ Dashboard
EVENTS     ▣ Explorer
WORLD      ◎ World Map    (new v2 — separate from Dashboard)
SOURCES    ◈ Registry
TOOLS      ⌕ Search
──────────
System     ● Pipeline OK   (clickable → health detail)
```

World Map is a standalone entry point, not a Dashboard sub-component. Pipeline status is a green dot with "OK" label in the sidebar footer, clickable to show RSS/Fetcher/Aggregator/LLM health.

## Frozen Architecture Decision

```
event_registry (SQLite, read-only)
       ↓
  FastAPI Serializer (6 endpoints, Pydantic models)
       ↓
  Next.js 14 + Tailwind v4 + shadcn/ui (Dark Intelligence Theme)
       ↓
  User Browser (localhost:3000 / prod deployment)
```

**DO NOT**:
- Modify the v4.4 data production chain
- Add PostgreSQL migration in V1
- Build user auth, recommendation, or agent chat
- Make it a "news website" — this is an **intelligence dashboard**

## Project Structure

```
~/workspace/news-intel-web/
├── backend/
│   ├── main.py              # FastAPI app + CORS + 6 route registration
│   ├── db.py                # SQLite read-only connector (file:...?mode=ro)
│   ├── models/schemas.py    # 12 Pydantic models mirroring frontend contracts
│   ├── api/dashboard.py     # GET /api/v1/dashboard (metrics + hot_events + map_events)
│   ├── api/events.py        # GET /api/v1/events, GET /api/v1/events/{id}
│   ├── api/sources.py       # GET /api/v1/sources
│   ├── api/search.py        # GET /api/v1/search?q=
│   ├── api/map.py           # GET /api/v1/map/events
│   └── requirements.txt     # fastapi, uvicorn, pydantic
├── frontend/
│   ├── src/
│   │   ├── contracts/       # Frozen TypeScript interfaces (mirror Pydantic models)
│   │   │   ├── event.ts     # EventDossier, SAOEntity, Action, Location, SourceInfo, etc.
│   │   │   ├── dashboard.ts # DashboardMetrics, DashboardResponse, MapEvent
│   │   │   └── source.ts    # SourceEntity
│   │   ├── app/
│   │   │   ├── page.tsx              # Dashboard (KPI + Global Map + Event Cards)
│   │   │   ├── events/page.tsx       # Explorer (table + filters + pagination)
│   │   │   ├── events/[id]/page.tsx  # Event Detail (Facts → Timeline → Evidence → SourceChain → AI)
│   │   │   ├── sources/page.tsx      # Source Registry cards
│   │   │   └── search/page.tsx       # Search with debounce
│   │   ├── components/
│   │   │   ├── layout/Header.tsx     # 64px, logo + SearchBox + UTC clock
│   │   │   ├── layout/Sidebar.tsx    # 240px, 4-section nav
│   │   │   ├── dashboard/MetricCard.tsx
│   │   │   ├── dashboard/EventGrid.tsx
│   │   │   ├── dashboard/GlobalEventMap.tsx  # react-simple-maps
│   │   │   ├── event/EventCard.tsx
│   │   │   ├── event/EventHeader.tsx
│   │   │   ├── event/FactPanel.tsx
│   │   │   ├── event/Timeline.tsx
│   │   │   ├── event/SourceChain.tsx
│   │   │   ├── event/EvidenceCard.tsx
│   │   │   ├── event/IntelligencePanel.tsx
│   │   │   └── common/{Badge,StatusDot,SearchBox,Table}.tsx
│   │   ├── lib/api.ts        # Fetch wrapper with base URL + error handling
│   │   └── lib/types.ts      # Re-exports from contracts/
│   └── src/app/globals.css   # Dark Intelligence Theme tokens
└── TASKS.md                  # Frozen 8-task development plan
```

## 6 API Endpoints (frozen)

| Endpoint | Purpose | Source |
|----------|---------|--------|
| GET /api/v1/dashboard | KPI metrics + hot_events + map_events | event_registry |
| GET /api/v1/events | Paginated list + event_type/country/stage filter | event_registry |
| GET /api/v1/events/{id} | Full Event Dossier (JSON fields parsed) | event_registry |
| GET /api/v1/sources | Source registry + event_count | source_registry |
| GET /api/v1/search?q= | LIKE search on title/summary/keywords | event_registry |
| GET /api/v1/map/events | Geographic markers (country non-null) | event_registry |

## Execution Order (frozen)

```
Task-001  Init + Design System + API Contract
Task-002  Layout + Routing    ||  Task-003  FastAPI Read Adapter
Task-005  Event Dossier Detail ⭐⭐⭐ (core validation)
Task-004  Dashboard + Global Event Map
Task-006  Event Explorer (table + filters)
Task-007  Sources + Search
Task-008  UI Polish + QA
```

**Principle**: Deliver Event Detail first (validate intelligence loop), then Dashboard (breadth).

## Dark Theme Design Tokens (v2 — amber accent)

```css
--background: #080B12;    --foreground: #F8FAFC;
--card: #141925;          --border: #1E2A3A;
--accent-amber: #F59E0B;  --accent-blue: #3B82F6;
--status-critical: #EF4444; --status-high: #F97316;
--status-success: #22C55E;
--sidebar: #111827;       --sidebar-primary: #1D4ED8;
```

**Principle**: Deep gray base, warm gray cards (#141925, not blue-gray), amber (#F59E0B) for emphasis/highlights, blue (#3B82F6) for interactions only, red/orange/green for status. Avoid heavy blue everywhere — that makes it look like enterprise admin, not intelligence.

## Dashboard V2 — Situational Awareness Pattern

The Dashboard is NOT a data statistics page. It is a **Situational Awareness Center** that answers 4 questions in 30 seconds:

| Question | Component | Position |
|----------|-----------|----------|
| "Where is the world changing?" | World Map (react-simple-maps, country markers) | Left 60% |
| "What matters most right now?" | Hot Events (EventCard ×3 with SAO+stage bar) | Right 40% |
| "Which entities are driving events?" | Event Heat (horizontal bar chart, entity ranking) | Bottom left |
| "What changed recently?" | Intelligence Feed (NEW/UPDATE/ACTIVE stream) | Bottom right |

Layout is 3 rows, not flat cards:
```
Row 1: Global Situation — 5 metrics in a single card (Active/Breaking/High Impact/Today/Sources)
Row 2: World Map (60%) + Hot Events (40%)
Row 3: Event Heat (60%) + Intelligence Feed (40%)
```

## Event Card V2 Pattern

Each EventCard must show the v4.4 Event Dossier structure, not just title+badges:
```
┌────────────────────────────┐
│ ACTIVE              HIGH    │  ← Stage dot + impact badge
│ Title (2-line clamp)       │
│ Apple  SUES  OpenAI        │  ← SAO entities + action type
│ ████████░░░                │  ← Stage progress bar (5 segments)
│ 8 src · SRC_DW_NEWS   89%  │  ← Source count + name + confidence
└────────────────────────────┘
```
- Stage bar: 5 segments (Breaking→Developing→Active→Stable→Closed), amber for current
- Source name from `source.primary_source` (e.g. "Reuters", "DW News")
- Confidence in red if ≥80%, blue otherwise
- Critical events: 4px red left border

## Product Naming Convention

The header should read "SENTINEL INTELLIGENCE" in two lines, with a red background square logo. Sidebar sections use intelligence-domain names: INTELLIGENCE (Situation), EVENTS (Event Explorer), WORLD (Geo Monitor), SOURCES (Source Network), ANALYSIS (Search). Portal title in HTML `<title>` should be "Sentinel Intelligence".

## Verification Queries

```bash
# Validate backend
curl http://localhost:8000/api/v1/dashboard | python -c "import sys,json; d=json.load(sys.stdin); print(d['metrics'])"
curl http://localhost:8000/api/v1/events/EVT-20260710-006 | python -c "import sys,json; e=json.load(sys.stdin); print(e['subject']['name'], '->', e['action']['type'], '->', e['object']['name'])"

# Build frontend
cd ~/workspace/news-intel-web/frontend && npm run build
```

## Event Detail Intelligence Ordering (frozen v2)

The Event Detail page MUST render sections in this order. This is an **intelligence analysis reading order**, not alphabetical:

1. **EventHeader** — "What happened?" + "Why does it matter?"
   - Title, stage badge, impact badge, confidence % (all in Row 1)
   - One-line summary from event.summary (Row 2, "what happened")
   - AI significance from llm_analysis.significance, in amber (Row 3, "why it matters")
   - Confidence bar at top edge (amber if ≥80%, blue otherwise)
2. **FactPanel** — Structured SAO: Subject/Action/Object/Location/Time
   - Entity types get emoji: 🌍 Country, 🏢 Company, 👤 Person, 🏛 Organization
   - Show entity_id as a small code label next to the name
3. **EvidenceCard** — Original-source quotes with attribution
   - Italic blockquotes with "View Source →" links
   - Reserved for Phase2: verification level, cross-reference indicators
4. **Timeline → "Evolution"** — Stage progress bar + vertical timeline
   - Stage bar: 5 segments (Breaking→Official→Follow-up→Analysis→Verified)
   - Active stage in amber, past stages in blue/60%, future in border color
   - Vertical timeline nodes: first=blue ring, latest=amber ring, middle=border
5. **SourceChain → "Information Flow"** — Flow graph: BREAK→FOLLOW
   - BREAK node: blue border, PRIMARY label
   - FOLLOW node: gray border
   - Title reads "Information Flow" not "Source Chain"
6. **IntelligencePanel** — bg=#172554, handles populated and null llm_analysis
   - Shows: event_summary, market_effect, risk_level, forecast, significance
   - Empty state: "AI analysis not yet generated for this event."

**Core principle**: Tell the analyst "What happened → Why it matters → Facts → Evidence → How it evolved → Information flow → AI insight" — not "database fields in order".

The intelligence analysis workflow: **What → Why → Facts → Evidence → Evolution → Flow → Judgment**.

## Component Directory Convention

All event components go in `components/event/`, dashboard in `components/dashboard/`, and reusable UI in `components/common/`. Keep `components/ui/` for shadcn auto-generated components only.

## Page Responsibility Matrix (frozen — from PRODUCT.md)

Before building ANY page, first define its core responsibility and what it MUST NOT do. This prevents the dashboard from becoming a generic admin panel.

| Page | Core Responsibility | MUST NOT |
|------|-------------------|----------|
| Dashboard | Global situation + key events + intelligence feed | No data management, no CRUD |
| Event Detail | Event deep analysis: facts→evidence→evolution→AI insight | No raw article lists |
| Event Explorer | Event search, filter, sort, batch compare | No editing, no config |
| World Map | Geographic situation entry point | No detailed geo-analysis (Phase2) |
| Sources | Information source capability analysis (authority, break rate, coverage) | No simple media list |
| Search | Global search entry | No advanced queries (Phase2) |

**Allowed deps (V1)**: react-simple-maps, framer-motion, date-fns. **Forbidden**: recharts (use only for Event Heat), graph libraries, auth systems, agent chat.

## Product Definition Freeze Workflow

When building a web product over existing data pipelines:

1. **Freeze PRODUCT.md first** — page responsibilities, reading order, color tokens, allowed/forbidden dependencies
2. **Freeze API Contract** — TypeScript interfaces + Pydantic models, agreed by both sides
3. **Deliver core validation page first** (Event Detail) — verify the data→display loop
4. **Build breadth pages second** (Dashboard, Explorer, Sources, Search)
5. **Polish last** — loading/empty/error states, animations, QA

Never start with Dashboard first. The intelligence loop must be validated end-to-end before adding breadth.

## DB Path on Windows

The pipeline SQLite lives at:
```
~/AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2/scripts/news_intel/news_intel.db
```
Construct this path with `os.path.expanduser()` and `os.path.join()` — never hardcode the absolute path.

## Pitfalls

1. **create-next-app conflicts**: If frontend/ already has files (e.g. contracts/), move them to /tmp first, create the app, then restore.
2. **shadcn-ui deprecation**: Use `npx shadcn@latest init -d` (not shadcn-ui). The `--style new-york --base-color slate` flags no longer work in shadcn v4.
3. **shadcn v4 overwrites globals.css**: After `npx shadcn@latest init -d`, the generated `globals.css` uses Tailwind v4's default theme. You MUST completely rewrite it with the Dark Intelligence Theme tokens. The original should be replaced, not patched.
4. **@tailwindcss/postcss missing**: Install separately with `npm install @tailwindcss/postcss` after create-next-app.
5. **Event Detail as primary acceptance**: Don't build Dashboard first — verify the intelligence loop (What→Why→Facts→Evidence→Evolution→Flow) works end-to-end before adding breadth.
6. **SQLite read-only mode**: Use `file:...?mode=ro` URI to prevent accidental writes.
7. **JSON field parsing**: event_registry stores evidence/source_chain/timeline as TEXT; must `json.loads()` in the API adapter.
8. **TypeScript path aliases**: Contracts at `src/contracts/`, re-exported by `lib/types.ts` as `@/lib/types`.
9. **Field verification before coding**: Before any web task, verify 10 critical fields exist in event_registry with a Python query.
10. **Color palette choice**: Use amber (#F59E0B) for emphasis, not blue. Heavy blue makes the UI look like enterprise admin, not intelligence. Card background should be warm gray (#141925), not blue-gray.
11. **Section naming**: The Timeline component is titled "Evolution" with a stage progress bar. The SourceChain component is titled "Information Flow". These are intelligence-domain names, not developer names.
12. **Do NOT build admin-first**: If the user says "stop and think like a product manager", pause all code and freeze PRODUCT.md before resuming.

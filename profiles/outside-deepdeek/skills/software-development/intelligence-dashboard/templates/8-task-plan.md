# Intelligence Dashboard — 8-Task Build Plan (template)

## Task-001: Init + Design System + API Contract
- FastAPI backend skeleton (uvicorn, port 8000, CORS)
- Next.js 14 frontend (App Router, Tailwind, shadcn/ui)
- Dark theme CSS tokens (amber accent, no blue overload)
- `frontend/src/contracts/` TypeScript interfaces (mirror backend Pydantic)

## Task-002: Layout (Header + Sidebar + Route Skeleton)
- Header: Logo, SearchBox, UTC clock, Pipeline status indicator
- Sidebar: 5 sections (RADAR, EVENTS, WORLD, SOURCES, TOOLS)
- 6 route placeholders (Dashboard, Events, Event/[id], Map, Sources, Search)

## Task-003: FastAPI Read Adapter (SQLite only)
- 6 endpoints: /dashboard, /events, /events/{id}, /sources, /search, /map/events
- Pydantic models mirror frontend contracts 1:1
- Read-only SQLite connection to pipeline's event_registry
- NO PostgreSQL, NO ORM, NO write models

## Task-005: Event Detail (CORE — build first)
- Reading order: Header → Facts → Evidence → Evolution → Information Flow → AI
- 7 components: EventHeader, FactPanel, Timeline(Evolution), EvidenceCard, SourceChain(Information Flow), IntelligencePanel, EventCard

## Task-004: Dashboard (Situational Awareness)
- 30-second answer to: Where? What? What's new? Healthy?
- 3 core components: WorldMap(Global Situation), EventHeat, IntelligenceFeed
- KPI row: Active / High Impact / Today / Sources
- Grid: Map + Feed | Heat + Top Cards

## Task-006: Event Explorer
- Filterable table (topic, country, impact)
- Pagination
- Click → Detail page

## Task-007: Sources + Search
- Source cards (authority, event_count, type badge)
- Search with debounce

## Task-008: UI Polish
- Skeleton loading states
- Error boundaries with retry
- Empty states per page
- Mobile fallback (1024px min)
- Framer-motion page transitions

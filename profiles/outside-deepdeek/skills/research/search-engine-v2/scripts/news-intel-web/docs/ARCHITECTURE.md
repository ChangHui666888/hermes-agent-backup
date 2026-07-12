# News Intelligence Platform — Architecture (Frozen)

## System Overview

```
                  Internet User
                       │
                    Nginx (:80)
                       │
          ┌────────────┴────────────┐
          │                         │
     Next.js 16                  FastAPI
     (static export)             (Read Adapter)
     Dashboard                   /api/v1/events
     Event Detail                /api/v1/dashboard
     Explorer                    /api/v1/sources
     World Map                   /api/v1/search
     Sources                     /api/v1/map/events
     Search
          │                         │
          └────────────┬────────────┘
                       │
              Event Registry (SQLite)
              ├── event_registry
              ├── source_registry
              └── entity_registry
                       │
                       │ (read-only)
                       │
         ══════════════╪══════════════
         Windows 11    │
         Hermes Agent  │
                       ▼
         News Pipeline v4.4
         RSS → Score → Fetch → Aggregate
                       │
                       ▼
              Event Dossier (21 fields)
```

## Two Phases, Not One System

| Phase | System | Location | Purpose |
|-------|--------|----------|---------|
| **Pipeline v4.4** | search-engine-v2 | Windows (Hermes) | Produce Event Dossiers from 70 RSS sources |
| **Web V1** | news-intel-web | Cloud (Docker) | Display Event Intelligence Dashboard |

They are connected only by the Event Registry SQLite file. The Web reads it. The Pipeline writes it. Nothing else.

## What This Architecture Does NOT Include

- No PostgreSQL (V1 uses SQLite directly)
- No article-level CRUD (the unit is Event, not Article)
- No user authentication (read-only public dashboard)
- No real-time push (V1 is request/response)
- No old news-intel-platform (frozen, not removed)

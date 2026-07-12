# News Intelligence Platform — Data Flow (Frozen)

## End-to-End

```
┌─────────────────────────────────────────────────────────┐
│ WINDOWS 11 · HERMES AGENT                               │
│                                                         │
│  70 RSS feeds ──→ RSS Scanner ──→ rss-archive.db        │
│       (cron 30min)                                      │
│                          │                              │
│                          ▼                              │
│                   sync.py + scorer.py                    │
│                   (5-dim: source/impact/entity/          │
│                    market/velocity → tier A/B/C)         │
│                          │                              │
│                          ▼                              │
│                   news_intel.db (3 tables)              │
│                   rss_raw · news_intelligence            │
│                   · news_content                        │
│                          │                              │
│                          ▼                              │
│                   batch.py + fetchers.py                 │
│                   (httpx/trafilatura/Scrapling/          │
│                    Playwright → full text)               │
│                          │                              │
│                          ▼                              │
│                   aggregator.py v4.4                     │
│                   build_fingerprint → cluster            │
│                   → 21-field Event Object                │
│                          │                              │
│                          ▼                              │
│              ┌──────────────────────┐                   │
│              │  Event Registry      │                   │
│              │  event_registry      │                   │
│              │  source_registry     │ ← SQLite file      │
│              │  entity_registry     │                   │
│              └──────────┬───────────┘                   │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                          │ file path:
                          │ .../news_intel/news_intel.db
                          │
┌─────────────────────────┼───────────────────────────────┐
│ CLOUD VPS · DOCKER      │                               │
│                         ▼                               │
│              FastAPI Read Adapter                        │
│              opens SQLite in read-only mode              │
│              serves 6 JSON endpoints                     │
│                         │                               │
│                         ▼                               │
│              Next.js 16 (SSR)                            │
│              fetches API → renders HTML                  │
│                         │                               │
│                         ▼                               │
│              Nginx (:80)                                 │
│              reverse proxy → Next.js                     │
│              serves static assets                        │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                          ▼
                   Internet User
                   http://100.107.117.23
```

## Event Object Lifecycle

```
Article (80 in DB)
  │
  ├─ build_fingerprint()
  │    subject · action · object · topic · country
  │
  ├─ fingerprint_score()
  │    pairwise comparison: anchor match → 100
  │    location mismatch → 0 (hard reject)
  │
  ├─ cluster()
  │    EVENT_THRESHOLD=50 → event
  │    MERGE_THRESHOLD=75 → strong merge
  │
  └─ Event Dossier (9 events)
       ├─ evidence  [quotes from articles]
       ├─ source_chain [who broke, who followed]
       ├─ timeline  [key moments by hour]
       ├─ facts     [SAO structured]
       └─ confidence [4-factor: authority + coherence + diversity + volume]
```

## Key Files

| File | Role | Location |
|------|------|----------|
| `news_intel.db` | Event Registry SQLite | `~/.hermes/.../news_intel/` |
| `aggregator.py` | Produces Event Dossiers | `search-engine-v2/scripts/news_intel/` |
| `db.py` (backend) | FastAPI reads SQLite | `news-intel-web/backend/` |
| `main.py` | 6 API endpoints | `news-intel-web/backend/` |
| `page.tsx` (×6) | Next.js pages | `news-intel-web/frontend/src/app/` |

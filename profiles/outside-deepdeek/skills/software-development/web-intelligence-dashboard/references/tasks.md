# TASKS.md — Frozen 8-task development plan (v2)

Source: ~/workspace/news-intel-web/TASKS.md

## Task order (frozen)

```
Task-001  Init + Design System + API Contract (3 contract files)
Task-002  Layout + Routing    ||  Task-003  FastAPI Read Adapter (6 endpoints)
Task-005  Event Dossier Detail ⭐⭐⭐ (core validation: intelligence loop)
Task-004  Dashboard + Global Event Map + 3 core components
Task-006  Event Explorer (table + filters + pagination)
Task-007  Sources + Search
Task-008  UI Polish + QA
```

## 3 Dashboard core components (frozen v2)

1. **Global Situation** — numeric event distribution by region/topic (top-left)
2. **Event Heat** — entity/event heat ranking bar chart (bottom-left)
3. **Intelligence Feed** — real-time intelligence delta stream (right sidebar)

## 6 API Endpoints

| GET /api/v1/dashboard | KPI + hot_events + map_events |
| GET /api/v1/events | Paginated list + filters |
| GET /api/v1/events/{id} | Full Event Dossier |
| GET /api/v1/sources | Source registry + event_count |
| GET /api/v1/search?q= | LIKE search |
| GET /api/v1/map/events | Geographic markers |

## Generic acceptance checklist per task

```
[ ] Code compiles / builds (npm run build, python -c "import main")
[ ] Renders real data from event_registry (never mock)
[ ] Loading state visible (Skeleton components)
[ ] Empty state effective (page-specific message)
[ ] Error state effective (with retry)
[ ] Hover effects match design spec
[ ] All colors use CSS variables (no hardcoded hex)
```

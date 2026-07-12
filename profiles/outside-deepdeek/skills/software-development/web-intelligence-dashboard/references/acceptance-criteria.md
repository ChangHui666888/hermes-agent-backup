# Web V1 Task Acceptance Criteria (Frozen)

Each task must pass these checks before claiming completion:

```
[ ] Code compiles without error (npm run build / python -c "import main")
[ ] Page renders REAL data from event_registry (no mock data)
[ ] Loading state visible (Skeleton components)
[ ] Empty state works (0 results = custom empty message per page)
[ ] Error state works (API down = retry button)
[ ] Hover effects match dark theme design spec
[ ] All colors use CSS variables (not hardcoded hex)
```

## Per-Task Specific Criteria

### Task-001
- `uvicorn main:app --port 8000` → 200 OK /health
- `npm run dev` → localhost:3000 renders dark theme
- contracts/ 3 TypeScript files pass type-check

### Task-002
- Header shows "NEWS INTELLIGENCE" logo + UTC clock (updates every second)
- Sidebar 4 menus active-highlight (#1D4ED8 on current page)
- 5 empty route pages load without error

### Task-003
- All 6 curl commands return real data
- Event detail parses JSON fields correctly (evidence, source_chain, timeline)
- CORS allows localhost:3000

### Task-004
- 4 MetricCard show real counts
- GlobalEventMap shows 5+ markers with click→event detail
- EventGrid shows 6 EventCard with hover animation

### Task-005 ⭐⭐⭐
- EventHeader: title + stage badge + confidence bar
- FactPanel: 5 rows (Subject/Action/Object/Location/Time)
- Timeline: vertical nodes with time + description
- Evidence: quotes with source attribution
- SourceChain: flow graph (break → follow)
- IntelligencePanel: #172554 background with AI analysis

### Task-006
- Table with filter dropdowns (topic/country/stage)
- Pagination works
- Row click → event detail

### Task-007
- Source cards show name, authority, event_count, type badge
- Search debounce 300ms → result list

### Task-008
- npm run build passes with 0 errors/warnings
- All states (loading/empty/error) covered
- Mobile shows "use desktop browser" below 1024px
- Page transitions use framer-motion fadeIn

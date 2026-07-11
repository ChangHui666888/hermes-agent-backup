# Event Aggregation V4 (frozen)

## Algorithm: Event-Centric Incremental Clustering

Three-phase approach:

### Phase 1: Article → Event
- Articles sorted by time ascending (earliest first)
- Each article compared against EXISTING event centroid fingerprints
- Score ≥ 50 → join event; else → create new event
- Time window: article time vs event's `last_time` (event lifecycle, not fixed window)
- None-times (unparseable dates) skip time check entirely

### Phase 2: Event → Event Merge
- Union-Find across events (NOT articles — prevents chain pollution)
- Compare event centroid fingerprints
- Score ≥ 70 + within time window → merge events
- Eliminates split caused by article ordering

### Phase 3: Filter
- Remove single-article events
- Compute `impact_level` from max score

## EventFingerprint Dimensions (100 points)

| Dimension | Weight | Rule |
|-----------|:------:|------|
| Action | 35 | Exact match, non-OTHER |
| Subject | 25 | Exact or substring match |
| Object | 20 | Exact or substring match |
| Primary Topic | 15 | Exact match |
| Event Type | 5 | Exact match |
| **Location** | **Hard 0** | Different country → score = 0 (no merge) |

## SAEO Extraction

Subject-Action-Object-EventType extracted via keyword mapping:

| Action | EventType | Pattern |
|--------|-----------|---------|
| SUES | Legal | sues, lawsuit, alleges, accuses, files lawsuit |
| ATTACKS | Military | attacks, strikes, bomb, missile, drone strike |
| SANCTIONS | Economic | sanctions, tariffs, embargo, restricts, bans |
| NEGOTIATES | Diplomacy | talks, negotiation, ceasefire, peace deal |
| DIES | Leadership | dies, killed, death, funeral, assassinated |
| ANNOUNCES | Politics | announces, declares, reveals, launches |
| SURGES/CRASHES | Finance | surges, soars, plunges, crashes |

## Date Parsing Pitfall

RSS dates are often truncated ("Fri, 10 Ju") — `fromisoformat` fails, `parsedate_to_datetime` also fails. Fix: return `None` for unparseable dates, skip time checks. Without this, articles with broken dates use `utcnow()` and never merge with valid-dated articles across 24h+ windows.

## Topic Classification

12 topics (Legal, Military, Diplomacy, Economic, Finance, Politics, Technology, Energy, Health, Sports, Leadership, Disaster) via keyword matching. Primary + Secondary topics stored in fingerprint.

## Location Hard Constraint

Extract country from `entities.countries` + text regex. Different country → score = 0, no merge ever. Prevents "Modern Slavery Fund Albania" vs "Viet Nam" false merges.

## Configurable

- `EVENT_THRESHOLD = 50` (article → event)
- `MERGE_THRESHOLD = 70` (event → event)
- `window_hours = 24` (default, event lifecycle)

# Situational Awareness Dashboard Pattern

## The 4-Question Test

A dashboard passes V1 if a user can answer these 4 questions in 30 seconds:

1. **Where?** → Where in the world are important events happening?
2. **What's important?** → What is the most significant event right now?
3. **What's new?** → What just changed that deserves attention?
4. **Is my system healthy?** → Is the intelligence pipeline running?

## Component Mapping

| Question | Component | Data Source |
|----------|-----------|-------------|
| Where? | WorldMap (react-simple-maps) | GET /api/v1/map/events |
| What's important? | EventHeat (entity bar chart) | Dashboard hot_events |
| What's new? | IntelligenceFeed (NEW/UPDATE stream) | Dashboard hot_events, sorted by last_updated |
| Is system healthy? | Pipeline Status indicator | Header green dot |

## WorldMap Implementation

```tsx
// react-simple-maps with country → coordinate mapping
import { ComposableMap, Geographies, Geography, Marker } from "react-simple-maps";

// Maintain a COUNTRY_COORDS map (~40 countries)
const COUNTRY_COORDS: Record<string, [number, number]> = {
  "United States": [-95, 38],
  "China": [104, 35],
  "Iran": [53, 32],
  // ... ~40 entries
};

// Marker color by confidence:
// ≥80% → #EF4444 (critical), ≥60% → #F97316 (high), else #F59E0B (amber)
// Marker size: 4 + (confidence / maxConf) * 8 → proportionally scaled
```

**Geo URL**: `https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json`
**Dependency**: `npm install react-simple-maps --legacy-peer-deps` (peer dep conflict with React 19)

## EventHeat Implementation

Horizontal bar chart of entity occurrence frequency across all events:
- Aggregate entity names from subject, object, actors, related_entities
- Display as horizontal bars with count labels
- Color by average confidence: amber (≥80%), blue (≥60%), muted (<60%)

## IntelligenceFeed Implementation

Vertical stream of recent events with stage indicators:
- NEW (breaking) → red left border, red badge
- UPDATE (developing) → orange left border, orange badge  
- ACTIVE → blue left border, blue badge
- Show headline + relative time (date-fns formatDistanceToNow)
- Footer: "X breaking · Y developing · Z active" summary

## MetricCard Implementation

4 KPI cards at the top of Dashboard:
- Each 100px height, uppercase label, large number, optional detail text
- Color-coded: critical (red), high (orange), accent-blue, success (green)
- Numbers are `tabular-nums` for alignment
- Detail line shows context (e.g. "3 breaking" under "9 Active")

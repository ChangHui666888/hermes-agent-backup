# Event Aggregation v4.4 Schema & Architecture

Date: 2026-07-12 | Commit: 899e594

## Summary

V4.4 upgrades the News Intelligence Pipeline from Article-centric output to an Event-centric platform with:
1. **Event Registry** — persisted to SQLite (event_registry table)
2. **Source Entity ID** — `SRC_REUTERS` / `SRC_DW_NEWS`
3. **Entity ID** — `CTRY_UNITED_STATES` / `COMP_APPLE` / `PERS_DONALD_TRUMP`
4. **Event Dossier** — evidence, source_chain, timeline
5. **Event API** — push to cloud PostgreSQL via `POST /internal/events/batch`
6. **Event-level LLM** — analysis from dossier, not just article

## V4.4 Event Object (24 fields vs 21 in v4.3)

```json
{
  "event_id": "EVT-20260710-006",
  "subject": {"entity_id": "COMP_APPLE", "name": "Apple", "type": "Company"},
  "action":  {"type": "SUES", "detail": "OpenAI over stealing trade secrets"},
  "object":  {"entity_id": "COMP_OPENAI", "name": "OpenAI", "type": "Company"},
  "event_type": "Legal",
  "event_time": "2026-07-10T00:00:00",
  "location": {"country": null, "region": null},
  "source": {
    "primary_source": "DW News",
    "primary_source_id": "SRC_DW_NEWS",
    "authority": 16,
    "source_count": 8,
    "sources": ["DW News", "BBC News", "Al Jazeera"]
  },
  "doc_refs": [{"url": "...", "title": "..."}],
  "actors": [{"entity": "Apple", "type": "Company", "role": "Initiator"}, ...],
  "title": "Apple calls OpenAI...",
  "summary": "Apple has accused the company behind ChatGPT...",
  "keywords": ["Legal", "Technology"],
  "confidence": 0.89, "coherence": 95.7,
  "extraction_method": "v4.4-saeo",
  "related_entities": [{"entity_id": "COMP_APPLE", "name": "Apple", "type": "Company"}, ...],
  "article_count": 8, "article_ids": [142, 145, ...],
  "stage": "active",
  "first_seen": "2026-07-10T00:00:00",
  "last_updated": "2026-07-11T00:00:00",

  // ── NEW v4.4 fields ──
  "evidence": [
    {"quote": "Apple has accused the company behind ChatGPT...", "source": "DW News", "url": "https://..."},
    {"quote": "Apple filed a lawsuit alleging OpenAI...", "source": "BBC News", "url": "https://..."}
  ],
  "source_chain": [
    {"source_id": "SRC_DW_NEWS", "source_name": "DW News", "time": "2026-07-10T00:00:00", "role": "break", "url": "..."},
    {"source_id": "SRC_BBC_NEWS", "source_name": "BBC News", "time": "2026-07-10T02:00:00", "role": "follow", "url": "..."}
  ],
  "timeline": [
    {"time": "2026-07-10T00:00:00", "update": "Apple calls OpenAI hardware business rotten...", "source": "DW News"},
    {"time": "2026-07-10T04:00:00", "update": "Apple sues OpenAI over trade secrets", "source": "BBC News"}
  ]
}
```

## DB Schema (6 tables, new in v4.4)

### event_registry
```
event_id TEXT PK, title, summary, event_type, stage, confidence, coherence,
subject_name, subject_type, action_type, action_detail,
object_name, object_type, location_country,
primary_source_id, source_count, article_count,
article_ids JSON, doc_refs JSON, actors JSON,
keywords JSON, related_entities JSON,
evidence JSON, source_chain JSON, timeline JSON,
first_seen, last_updated, llm_analysis JSON,
extraction_method, created_at
```

### source_registry
```
source_id TEXT PK (e.g. SRC_REUTERS),
name, display_name, type (GOVERNMENT|MEDIA|RESEARCH|SOCIAL),
authority INT, country, language, url, first_seen, last_seen
```

### entity_registry
```
entity_id TEXT PK (e.g. CTRY_UNITED_STATES),
canonical_name, aliases JSON,
type (Company|Person|Country|Organization|Location|Other),
country, importance INT, first_seen, last_seen
```

## Entity ID Convention

| Type Prefix | Entity Type | Example |
|:-----------|:------------|:--------|
| `COMP_` | Company | `COMP_APPLE`, `COMP_OPENAI` |
| `PERS_` | Person | `PERS_DONALD_TRUMP` |
| `CTRY_` | Country | `CTRY_UNITED_STATES`, `CTRY_IRAN` |
| `ORG_` | Organization | `ORG_NATO`, `ORG_UN` |
| `LOC_` | Location | `LOC_TEHRAN` |
| `ENT_` | Other (fallback) | `ENT_CHATGPT` |

## Source ID Convention

`SRC_` + uppercase_name_replacing_spaces_and_special_chars_with_underscores

```
Reuters → SRC_REUTERS
DW News → SRC_DW_NEWS
BBC News → SRC_BBC_NEWS
UK Gov → SRC_UK_GOV
```

## Event-level LLM Prompt (EVENT_INTEL_PROMPT)

Input: Full event dossier (SAO + evidence quotes + timeline + source chain, max 3000 chars)
Output:
```json
{
  "event_summary": "50 chars",
  "significance": "strategic assessment 80 chars",
  "impact": {"geopolitical": "...", "market": "...", "industry": ["..."]},
  "risk_level": "low|medium|high|critical",
  "forecast": "next development 60 chars",
  "key_uncertainty": "biggest unknown 60 chars",
  "entities_affected": ["..."],
  "confidence": 0.0-1.0
}
```

## Cloud Push Endpoint

```
POST {NEWS_API_BASE}/internal/events/batch
X-Internal-Token: {NEWS_API_TOKEN}
Content-Type: application/json

body: [{event_id, title, summary, ... 20+ fields per event}]
```

Push commands:
```bash
# From Python
python -c "from news_intel.pusher import push_from_registry; print(push_from_registry(stage='active', limit=50))"

# From CLI after aggregation
python test_aggregator.py --hours 24 --window 6 --limit 100
# (events auto-persisted to event_registry)
```

## File Changes (v4.3 → v4.4)

| File | Change |
|------|--------|
| `news_intel/db.py` | +30% (3→6 tables, new CRUD: upsert_event, upsert_source, upsert_entity, seed_source_registry) |
| `news_intel/aggregator.py` | +30% (v4.4 helpers: source_id, entity_id, evidence, source_chain, timeline, persistence) |
| `news_intel/pusher.py` | +150% (new: push_events, push_event, push_from_registry, _event_to_push_format) |
| `news_intel/generator.py` | +100% (new: generate_intel, _format_event_dossier, EVENT_INTEL_PROMPT) |
| `config/source_scores.json` | +2 entries (DW News, Reddit WorldNews) |
| `test_aggregator.py` | +8 lines (display evidence/timeline/source_chain) |

## Known Limitation

Subject is sometimes empty for hub entities (Iran, Trump, US). Hub dampening reduces weight to ×0.3 but if multiple articles have only hub entities, subject may still fall below MIN_SUBJECT_WEIGHT=0.15. This is by design — "Trump" as subject in every article is uninformative, but the trade-off is occasional empty subjects for events where only hub entities are present.

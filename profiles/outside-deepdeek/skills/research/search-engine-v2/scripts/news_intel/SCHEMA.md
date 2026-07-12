# News Intelligence Platform — Phase 1 Event Schema (v4.3 SAEO)

##  Schema File: `frozen-schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://news-intel.hermes/schemas/event-v4.3.json",
  "title": "News Intelligence Platform — Frozen Event Object v4.3 SAEO",
  "description": "Phase 1 output: structured event object from rule-based aggregation of global news articles.",
  "type": "object",
  "required": [
    "event_id", "subject", "action", "object", "event_type", "source",
    "actors", "title", "summary", "confidence", "coherence",
    "article_count", "article_ids", "stage", "first_seen", "last_updated"
  ],
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Unique event identifier in format EVT-YYYYMMDD-NNN (NNN = sequential per day, 0-padded to 3 digits).",
      "pattern": "^EVT-20[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])-[0-9]{3}$",
      "examples": ["EVT-20260710-006"]
    },

    "subject": {
      "type": "object",
      "description": "Primary entity performing the action (weighted by entity rarity × global IDF).",
      "required": ["name", "type"],
      "properties": {
        "name": {
          "type": "string",
          "description": "Canonical entity name. Empty string if no entity meets MIN_SUBJECT_WEIGHT (0.15).",
          "examples": ["Apple", "Ukraine", "China", "Trump", "OpenAI", "Russian Federation"]
        },
        "type": {
          "type": "string",
          "description": "Entity type from known_entity_types dict or fallback 'Other'.",
          "enum": ["Company", "Person", "Country", "Location", "Organization", "Other"],
          "examples": ["Company", "Country", "Person"]
        }
      }
    },

    "action": {
      "type": "object",
      "description": "The action detected by first-match keyword matching on aggregated titles + descriptions.",
      "required": ["type", "detail"],
      "properties": {
        "type": {
          "type": "string",
          "description": "Standardized action category from enumerated action_map. Falls back to 'OTHER' if no pattern matches.",
          "enum": [
            "ATTACKS", "DIES", "NEGOTIATES", "SUES", "SANCTIONS",
            "ELECTED", "RESIGNS", "PROTESTS", "ANNOUNCES",
            "LAUNCHES", "BANS", "MERGE", "WARNS",
            "OTHER"
          ],
          "examples": ["ATTACKS", "DIES", "SUES", "NEGOTIATES", "SANCTIONS"]
        },
        "detail": {
          "type": "string",
          "description": "Up to 50 chars of context after the matched action keyword, extracted from combined title + description. Regex: keyword + (up to 50 non-newline chars). Falls back to fingerprinted text.",
          "maxLength": 55,
          "examples": [
            "OpenAI over stealing 'trade secrets' Apple has acc",
            "as Iran closes the Strait of Hormuz",
            "in Qatar and Oman to avert escalation"
          ]
        }
      }
    },

    "object": {
      "type": "object",
      "description": "Entity receiving the action. Selected from countries/companies weighted by entity rarity. Excludes subject. Hub entities dampened ×0.3.",
      "required": ["name", "type"],
      "properties": {
        "name": {
          "type": "string",
          "description": "Canonical entity name. Empty string if no candidate qualifies.",
          "examples": ["OpenAI", "Russian Federation", "China", "Iran", "United States"]
        },
        "type": {
          "type": "string",
          "enum": ["Company", "Person", "Country", "Location", "Organization", "Other"]
        }
      }
    },

    "event_type": {
      "type": "string",
      "description": "Mapped from action type via EVENT_TYPE_MAP.",
      "examples": ["Military", "Legal", "Political", "Diplomatic", "Technology", "Corporate", "Economic", "Other"]
    },

    "event_time": {
      "type": ["string", "null"],
      "description": "ISO 8601 timestamp of the estimated event time (start_time of the merged cluster).",
      "format": "date-time",
      "examples": ["2026-07-10T08:30:00"]
    },

    "location": {
      "type": "object",
      "description": "Geographic context. Country from L1 scorer. Region reserved for future.",
      "properties": {
        "country": {
          "type": ["string", "null"],
          "description": "Primary country associated with the event. Hard constraint in scorer: different country → score = 0.",
          "examples": ["United States", "China", "Iran", "Ukraine"]
        },
        "region": {
          "type": ["string", "null"],
          "description": "Sub-region or city (reserved: not yet implemented)."
        }
      }
    },

    "source": {
      "type": "object",
      "description": "Source authority and diversity metrics for confidence scoring.",
      "required": ["primary_source", "authority", "source_count", "sources"],
      "properties": {
        "primary_source": {
          "type": "string",
          "description": "The first article by published_at time (earliest source to report).",
          "examples": ["DW News", "Reuters", "UK Gov"]
        },
        "authority": {
          "type": "integer",
          "description": "Maximum authority score among clustered sources (0–20 scale).",
          "minimum": 0,
          "maximum": 20,
          "examples": [16, 20, 15]
        },
        "source_count": {
          "type": "integer",
          "description": "Number of unique sources clustered into this event.",
          "minimum": 1,
          "examples": [8, 4, 3]
        },
        "sources": {
          "type": "array",
          "items": { "type": "string" },
          "description": "First 10 unique source names in the cluster.",
          "maxItems": 10,
          "examples": [["DW News", "Reuters", "France 24", "BBC"]]
        }
      }
    },

    "doc_refs": {
      "type": "array",
      "description": "References to the first 5 constituent articles.",
      "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["url", "title"],
        "properties": {
          "url": { "type": "string", "format": "uri" },
          "title": { "type": "string" }
        }
      }
    },

    "actors": {
      "type": "array",
      "description": "Actor roles inferred from entity references relative to action/object.",
      "items": {
        "type": "object",
        "required": ["entity", "type", "role"],
        "properties": {
          "entity": { "type": "string", "description": "Canonical entity name." },
          "type": {
            "type": "string",
            "enum": ["Company", "Person", "Country", "Organization", "Other"]
          },
          "role": {
            "type": "string",
            "description": "Inferred role: first entity→Initiator, object match→Target, others→Participant.",
            "enum": ["Initiator", "Target", "Participant"]
          }
        }
      },
      "examples": [[
        {"entity": "Apple", "type": "Company", "role": "Initiator"},
        {"entity": "OpenAI", "type": "Company", "role": "Target"}
      ]]
    },

    "title": {
      "type": "string",
      "description": "Best title from merged cluster (the most descriptive title among members).",
      "examples": ["Apple calls OpenAI's hardware business 'rotten to its core' in trade secret suit"]
    },

    "summary": {
      "type": "string",
      "description": "Concatenated first 100 chars from up to 3 article summaries. HTML-filtered (<30% tag chars, no <table> prefixes). Falls back to best_title if empty.",
      "examples": ["Apple has accused the company behind ChatGPT and two of its former employees of misappropriating its..."]
    },

    "keywords": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Aggregated topics from merged cluster members.",
      "examples": [["Legal", "Technology", "Intellectual Property"]]
    },

    "confidence": {
      "type": "number",
      "description": [
        "Overall confidence score (0–1), weighted:",
        "  0.4 × normalized_source_authority (max_auth/20)",
        "  0.3 × normalized_coherence (coherence/100)",
        "  0.2 × source_diversity (min(source_count,5)/5)",
        "  0.1 × article_count_factor (min(article_count,10)/10)"
      ].join("\n"),
      "minimum": 0,
      "maximum": 1,
      "examples": [0.89, 0.76, 0.68]
    },

    "coherence": {
      "type": "number",
      "description": "Average pairwise coherence score among merged articles (1–100). Above 50 qualifies as EVENT. Above 75 triggers aggressive merge.",
      "minimum": 0,
      "maximum": 100,
      "examples": [95.7, 72.5, 51.7]
    },

    "extraction_method": {
      "type": "string",
      "description": "Fixed version tag for backward compatibility.",
      "const": "v4.3-saeo"
    },

    "related_entities": {
      "type": "array",
      "description": "Top 20 entity references from the merged cluster (for graph linking / Phase 2 entity resolution).",
      "maxItems": 20,
      "items": {
        "type": "object",
        "required": ["name", "type"],
        "properties": {
          "name": { "type": "string" },
          "type": { "type": "string", "enum": ["Company", "Person", "Country", "Location", "Organization", "Other"] }
        }
      }
    },

    "article_count": {
      "type": "integer",
      "description": "Number of articles merged into this event.",
      "minimum": 1,
      "examples": [8, 4, 3]
    },

    "article_ids": {
      "type": "array",
      "items": { "type": "integer" },
      "description": "Database row IDs of constituent articles (for traceability)."
    },

    "stage": {
      "type": "string",
      "description": [
        "Event lifecycle stage based on time since first_seen:",
        "  breaking:   < 2 hours",
        "  developing: 2–24 hours",
        "  active:     24 hours – 7 days",
        "  stable:     7–30 days",
        "  closed:     > 30 days"
      ].join("\n"),
      "enum": ["breaking", "developing", "active", "stable", "closed"],
      "examples": ["developing", "active"]
    },

    "first_seen": {
      "type": ["string", "null"],
      "description": "ISO 8601 timestamp of the earliest article in the cluster (start_time).",
      "format": "date-time"
    },

    "last_updated": {
      "type": ["string", "null"],
      "description": "ISO 8601 timestamp of the most recent article in the cluster (last_time).",
      "format": "date-time"
    }
  }
}
```

---

## Action Enumeration

| Enum Value | Detection Keyword | Event Type |
|:-----------|:------------------|:-----------|
| `ATTACKS` | 攻击, attack, strike, bomb, assault, invade, missile | Military |
| `DIES` | 死亡, die, kill, assassination, assassinate, dead, murder | Crisis |
| `NEGOTIATES` | 谈判, negotiate, talk, discuss, summit, meet, mediator | Diplomatic |
| `SUES` | 起诉, sue, lawsuit, court, indict, prosecute | Legal |
| `SANCTIONS` | 制裁, sanction, embargo, freeze, tariff | Economic |
| `ELECTED` | 当选, elect, vote, win election, inaugurated | Political |
| `RESIGNS` | 辞职, resign, step down, quit, oust | Political |
| `PROTESTS` | 抗议, protest, rally, demonstrate, march, riot | Social |
| `ANNOUNCES` | 宣布, announce, declare, unveil, launch plan | Political |
| `LAUNCHES` | 发射, launch, deploy, roll out, release | Technology |
| `BANS` | 禁止, ban, prohibit, block, restrict | Legal |
| `MERGE` | 合并, merge, acquire, takeover, buyout | Corporate |
| `WARNS` | 警告, warn, threaten, caution, alert | Diplomatic |
| `OTHER` | (no match) | Other |

---

## Full Output Example

```json
{
  "event_id": "EVT-20260710-006",
  "subject": {"name": "Apple", "type": "Company"},
  "action": {"type": "SUES", "detail": "OpenAI over stealing trade secrets Apple has acc"},
  "object": {"name": "OpenAI", "type": "Company"},
  "event_type": "Legal",
  "event_time": "2026-07-10T08:30:00",
  "location": {"country": "United States", "region": null},
  "source": {
    "primary_source": "DW News",
    "authority": 16,
    "source_count": 8,
    "sources": ["DW News", "AP", "Reuters", "France 24", "BBC"]
  },
  "doc_refs": [
    {"url": "https://dw.com/en/apple-sues-openai", "title": "Apple calls OpenAI's hardware business 'rotten to its core'..."},
    {"url": "https://apnews.com/...", "title": "Apple escalates legal fight with OpenAI"}
  ],
  "actors": [
    {"entity": "Apple", "type": "Company", "role": "Initiator"},
    {"entity": "OpenAI", "type": "Company", "role": "Target"}
  ],
  "title": "Apple calls OpenAI's hardware business 'rotten to its core' in trade secret suit",
  "summary": "Apple has accused the company behind ChatGPT and two of its former employees of misappropriating its...",
  "keywords": ["Legal", "Technology", "Intellectual Property"],
  "confidence": 0.89,
  "coherence": 95.7,
  "extraction_method": "v4.3-saeo",
  "related_entities": [
    {"name": "Apple", "type": "Company"},
    {"name": "OpenAI", "type": "Company"}
  ],
  "article_count": 8,
  "article_ids": [142, 145, 150, 155, 160, 165, 170, 175],
  "stage": "active",
  "first_seen": "2026-07-10T08:30:00",
  "last_updated": "2026-07-11T14:22:00"
}
```

---

## Confidence Scoring Formula

```
confidence = 0.4 × (source_authority / 20)        # max authority among cluster sources
           + 0.3 × (coherence / 100)               # avg pairwise text similarity
           + 0.2 × min(source_count, 5) / 5        # source diversity bonus (caps at 5)
           + 0.1 × min(article_count, 10) / 10     # volume bonus (caps at 10)
```

| Weight | Factor | Rationale |
|:------:|--------|-----------|
| 0.4 | Source authority | Most important: high-authority sources = reliable event |
| 0.3 | Coherence | Text similarity consistency = event is real |
| 0.2 | Source diversity | Multiple independent sources = corroboration |
| 0.1 | Article count | Volume confirms newsworthiness (but easy to spam) |

---

## File Paths

| File | Role |
|------|------|
| `news_intel/aggregator.py` | Main aggregation: schema output at lines 583–603 |
| `news_intel/scorer.py` | L1 scoring: entity weights + location constraint |
| `news_intel/enhancers.py` | Qwen3 qmerge + dedup |
| `news_intel/generator.py` | Event insight generation |
| `news_intel/architecture.html` | Interactive architecture diagram |
| `test_aggregator.py` | Test harness with --hours/--window/--single |

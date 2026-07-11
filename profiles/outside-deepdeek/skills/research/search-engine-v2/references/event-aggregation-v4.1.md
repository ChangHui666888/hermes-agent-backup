# Event Aggregation V4.1 — Entity Intelligence Layer

## Evolution

```
V3: Union-Find + SAO fingerprint (chain pollution problem)
V4: Event-Centric 3-phase (chain fixed, but entity weight too high)
V4.1: + Entity Intelligence Layer (canonicalizer + type weight + IDF + anchor)
```

## V4.1 Changes

Five mechanisms added to `aggregator.py`:

| # | Mechanism | Implementation | Effect |
|---|-----------|---------------|--------|
| 1 | Entity Canonicalizer | 30+ mappings (US→United States, UK→United Kingdom) | Same entity, different names → merged |
| 2 | Entity Type Weight | Person=0.3, Country=1.0, Company=0.8 | Trump no longer dominates |
| 3 | Entity IDF | `log(N/freq)` auto-downweights frequent entities | Hot figures get 0.39x weight |
| 4 | SAO Anchor | `subject|action|object|topic` exact match → 100pts | Same event → guaranteed merge |
| 5 | Date parser | ISO + email.utils `parsedate_to_datetime` | Handles truncated RSS dates |

## Key Pitfall: RSS Entity Over-tagging

RSS L1 scoring tags every article mentioning Trump with `persons: ["Trump"]`, even when the article is about a domestic US judge, not Trump foreign policy. This causes the Proud Boys article (country=None) to bridge Iran events via Location constraint bypass.

**Root cause**: data layer (entity extraction), NOT aggregation algorithm.

## Date Parsing Bug

RSS dates like "Fri, 10 Ju" (truncated) fail `datetime.fromisoformat()`. Using `email.utils.parsedate_to_datetime` as fallback fixes the time window check that was blocking Phase 2 event merging.

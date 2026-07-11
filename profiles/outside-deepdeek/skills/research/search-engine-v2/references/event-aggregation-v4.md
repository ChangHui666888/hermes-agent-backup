# Event Aggregator V4

## Architecture

Event-Centric 3-phase clustering. Replaces Union-Find chain-polluted v1-v3.

```
Phase 1: Article → Event (EventFingerprint score >= 50)
Phase 2: Event → Event merge (fingerprint >= 70 + time window)
Phase 3: Filter singles + impact_level
```

## EventFingerprint (SAEO)

| Dimension | Weight | Source |
|-----------|:------:|--------|
| Subject | 25 | entities.companies[0] or persons[0] |
| Action | 35 | regex word bank (15 categories) |
| Object | 20 | entities.countries[0] or companies |
| Primary Topic | 15 | keyword dictionary (12 categories) |
| Event Type | 5 | action -> type mapping |

**Hard constraint**: different country -> score = 0 (never merge).

## Action Word Bank

SUES / ATTACKS / SANCTIONS / NEGOTIATES / ANNOUNCES / ELECTS / DIES / CRASHES / SURGES / CUTS / REPORTS / DEVELOPS / BANS / FUNDS / WARNS

## Topic Dictionary

Legal / Military / Diplomacy / Economic / Finance / Politics / Technology / Energy / Health / Sports / Leadership / Disaster

## Known Issues

1. **Common entity pollution**: Articles sharing "Trump" or "US" may chain-merge unrelated events. Mitigation: entity frequency filter (future).
2. **Truncated RSS dates**: "Fri, 10 Ju" format unparseable -> returns None -> time check skipped.
3. **Apple-OpenAI split resolved**: Phase 2 merge now combines events with same SAEO fingerprint.

## Usage

```bash
python test_aggregator.py --hours 24 --window 12 --limit 50
python test_aggregator.py --hours 24 --window 12 --limit 50 --insight
```

**Benchmark**: 50 articles -> 15 events (0.0s, 42% coverage, zero LLM).

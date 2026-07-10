# Pipeline Report Format

`run_pipeline()` writes to `~/.hermes/news-pipeline-report.json`.

## Schema

```json
{
  "timestamp": "2026-07-10T20:10:55",
  "processed": 28,
  "duplicate": 32,
  "tier_a": 0,
  "tier_b": 11,
  "tier_c": 116,
  "enhanced": 2,
  "saved": 11,
  "failed": 0,
  "duration_sec": 27.4
}
```

## Fields

| Field | Source | Meaning |
|------|------|------|
| `processed` | sync_recent stats | New articles scored this run |
| `duplicate` | sync_recent dedup | Articles skipped (already scored) |
| `tier_a` | score_article | ≥90 points → DeepSeek V4 Flash |
| `tier_b` | score_article | 60-89 points → Qwen3-1.7B |
| `tier_c` | score_article | <60 points → Python rules |
| `enhanced` | route loop | Articles that got LLM enhancement |
| `saved` | cloud push ok count | Successfully POSTed to FastAPI |
| `failed` | cloud push fail count | Failed POSTs (3 consecutive → break) |
| `duration_sec` | time.monotonic | Wall clock time |

## Tier thresholds

```python
if total >= 90: tier = "A"      # DeepSeek V4 Flash
elif total >= 60: tier = "B"    # Qwen3-1.7B
else: tier = "C"                # Python rules
```

## Summary output format

Shell script reads the JSON and prints:
```
📊 News Pipeline Summary
  Processed  : 28
  DeepSeek V4 Flash: 0
     Qwen3-1.7B: 11
     Python 规则: 116
  Duplicate  : 32
  Enhanced   : 2
  Saved      : 11
  Failed     : 0
  Duration   : 27.4s
```

Tier labels are NOT hardcoded in the wrapper — they come from a tiers dict that maps report keys to display names.

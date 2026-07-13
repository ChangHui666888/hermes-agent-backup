# Pipeline Check Pattern

## YAML Output Format (Agent-readable)

```
STATUS: SUCCESS|FAILED
PIPELINE: news-intel
STAGE: FETCHER
RESULT: PASS|FAIL
DETAIL: articles=280 content_missing=280
ERROR_TYPE: EMPTY_CONTENT
REASON: 280 articles missing content
IMPACT: Aggregator may create incomplete events
ACTION: retry
COMMAND: python pipeline_check.py fetcher
VERIFY: python pipeline_check.py check
STOP: true
```

## Agent Usage Rules

1. First: `python pipeline_check.py check`
2. If STATUS=FAILED: only handle FAILED_STAGE
3. Execute COMMAND
4. Execute VERIFY
5. Never without confirmation: delete data, rebuild database, modify schema, skip failed stages

## Check Stages

| Stage | Check | Failure Meaning |
|-------|-------|----------------|
| RSS | articles > 0 in rss_raw | No source data |
| SCORER | score_total > 0 | Articles not scored |
| FETCHER | content_md non-null count | Missing full text |
| AGGREGATOR | events > 0 | No events aggregated |
| SQLITE | DB file exists, size, raw/events counts | Database issue |
| SYNC | local events == cloud events | Cloud data mismatch |
| API | Cloud dashboard reachable | Web is down |

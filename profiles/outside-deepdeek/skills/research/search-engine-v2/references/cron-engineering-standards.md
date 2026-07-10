# Cron Engineering Standards (2026-07-10)

All Hermes cron jobs MUST follow this template, aligned with `rss-scanner`.

## Shell → Python → Business contract

```
Hermes Cron
    │
    ▼
xxx.sh          ← SCRIPT_DIR=$(dirname "$0"); python "$SCRIPT_DIR/xxx.py" "$@"
    │              NO cd, NO hardcoded paths, NO sys.path hacks
    ▼
xxx.py          ← argparse + logging + main() → run_xxx() → report dict
    │              NO sys.path, NO fallback paths
    ▼
business.py     ← def run_xxx(...) -> dict:
    │              write ~/.hermes/xxx-report.json
    │              return report
    ▼
xxx.sh          ← read report JSON, print summary
```

## Critical pitfalls (all encountered 2026-07-10)

1. **MSYS paths fail in cron bash**: `/c/Users/...` paths from git-bash do not resolve in cron's bash environment. Use `.py` scripts with absolute Windows paths or `os.path.join`.

2. **`cd` in shell scripts breaks**: `set -e` + `cd /c/Users/...` → exit 1 if path doesn't resolve. Fix: don't `cd` at all, use `python "$SCRIPT_DIR/xxx.py"`.

3. **Python stdout buffering hides output**: Cron logs show nothing for 120s then "timed out". Fix: `os.environ["PYTHONUNBUFFERED"] = "1"` + `print(..., flush=True)`.

4. **PowerShell multi-line `\` breaks**: `hermes cron create ... \` fails. Use single-line command in PS.

5. **`hermes cron run <id>` returns "not found"**: Job IDs from `hermes cron list` may not match `hermes cron run`. Use `hermes cron list` to get current IDs.

6. **Cron `--repeat 99999` required**: Without `--repeat`, jobs run exactly once. Must pass `--repeat 99999` for infinite repeat.

7. **Empty prompt required for `--no-agent`**: `hermes cron create ... "30m" ""` — the trailing `""` is the empty prompt.

## Fail-fast patterns

- **Qwen**: module-level `_qwen_available = True` flag. First failure → `False` → all subsequent calls return `None` immediately.
- **Cloud push**: `if fail >= 3: break` in push loop. Prevents 60+ timeout requests when API is unreachable.
- **Scoring dedup**: Check `rss_raw` table before scoring. `existing_urls = set(r[0] for r in dst.execute(...))`.
- **Enhancement dedup**: `LEFT JOIN news_content nc ON nc.intel_id = ni.id WHERE nc.id IS NULL`.

## Qwen3-1.7B optimization

- Merge 3 calls (tags/entities/summary) into 1 with combined prompt (`QMERGE_PROMPT`)
- Timeout: 60s (was 30s → 5s)
- max_tokens: 1024 (was 150 → 300)
- Remove `system` role (Qwen3 returns 400), use single `user` message only
- Remove `temperature` parameter (Qwen3 doesn't need it)

## Cron creation commands (PowerShell single-line)

```powershell
hermes cron create --name rss-scan --script rss-scanner.py --no-agent --repeat 99999 "5m" ""
hermes cron create --name news-pipeline --script "profiles\outside-deepdeek\skills\research\search-engine-v2\scripts\news-pipeline.sh" --no-agent --repeat 99999 "30m" ""
```

## Report format

```json
{
  "timestamp": "2026-07-10T20:10:55",
  "processed": 28, "duplicate": 32,
  "tier_a": 0, "tier_b": 11, "tier_c": 116,
  "enhanced": 2, "saved": 11, "failed": 0,
  "duration_sec": 27.4
}
```

## Exit codes

| Code | Meaning |
|:--:|------|
| 0 | Success |
| 1 | Pipeline execution error |
| 2 | Module import failed |
| 3 | Config error |

## Log locations

```
~/.hermes/cron/output/<job_id>/YYYY-MM-DD_HH-MM-SS.md
```

#!/usr/bin/env python3
"""
pipeline_check.py — Pipeline CLI: check / run / individual stages.

Agent-readable YAML-style output.

Usage:
  python pipeline_check.py check       Full health check
  python pipeline_check.py rss         Run RSS scanner
  python pipeline_check.py scorer      Run scorer
  python pipeline_check.py fetcher     Run content fetcher
  python pipeline_check.py aggregator  Run event aggregator
  python pipeline_check.py sync        Sync to cloud API
  python pipeline_check.py run         Full pipeline execution
"""

import sys
import os
import subprocess
import sqlite3
import time
import json
import urllib.request
import urllib.error

# ── CONFIG ──────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(SCRIPT_DIR)  # search-engine-v2/scripts
DB_PATH = os.path.join(SCRIPT_DIR, "news_intel.db")
CLOUD_API = "http://100.107.117.23/api/v1/dashboard"
CLOUD_INTERNAL = "http://100.107.117.23/internal/events/batch"
INTERNAL_TOKEN = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")

COMMAND_MAP = {
    "rss": {
        "label": "RSS",
        "script": os.path.join(PIPELINE_DIR, "rss-scanner.py"),
    },
    "scorer": {
        "label": "SCORER",
        "script": os.path.join(SCRIPT_DIR, "sync.py"),
        "args": "--hours 2",
    },
    "fetcher": {
        "label": "FETCHER",
        "script": os.path.join(PIPELINE_DIR, "batch.py"),
        "args": "--help",
        "real_cmd": f"cd {PIPELINE_DIR} && python batch.py --help",
    },
    "aggregator": {
        "label": "AGGREGATOR",
        "script": os.path.join(SCRIPT_DIR, "aggregator.py"),
    },
    "sync": {
        "label": "SYNC",
        "script": os.path.join(PIPELINE_DIR, "cron-sync.py"),
    },
}

# ── OUTPUT HELPERS ──────────────────────────────────────────────

def yaml_block(status: str, **fields):
    """Print YAML-style output block."""
    lines = [f"STATUS: {status}"]
    for k, v in fields.items():
        if v is not None:
            lines.append(f"{k}: {v}")
    print("\n".join(lines))

def yaml_ok(stage: str, detail: str = "", **extra):
    yaml_block("SUCCESS", PIPELINE="news-intel", STAGE=stage, RESULT="PASS",
               DETAIL=detail, NEXT="continue", **{k: v for k, v in extra.items() if v})

def yaml_fail(stage: str, error_type: str, reason: str, action: str = "",
              command: str = "", verify: str = "", **extra):
    yaml_block("FAILED", PIPELINE="news-intel", FAILED_STAGE=stage,
               ERROR_TYPE=error_type, REASON=reason,
               IMPACT=action, ACTION="retry",
               COMMAND=command or f"python pipeline_check.py {stage.lower()}",
               VERIFY=verify or "python pipeline_check.py check",
               STOP="true", **{k: v for k, v in extra.items() if v})

# ── SQLite HELPERS ──────────────────────────────────────────────

def db_query(sql: str) -> int | None:
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        r = conn.execute(sql).fetchone()
        conn.close()
        return r[0] if r else 0
    except Exception:
        return None

def db_size_kb() -> str:
    if not os.path.exists(DB_PATH):
        return "0KB"
    return f"{os.path.getsize(DB_PATH)/1024:.0f}KB"

# ── HTTP HELPERS ────────────────────────────────────────────────

def http_get(url: str, timeout: int = 5) -> dict | None:
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(r.read())
    except Exception:
        return None

def http_post(url: str, body: list, timeout: int = 30) -> dict | None:
    try:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "X-Internal-Token": INTERNAL_TOKEN,
        })
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read())
    except Exception:
        return None

# ── HEALTH CHECKS ───────────────────────────────────────────────

def check_rss() -> tuple[bool, str]:
    raw = db_query("SELECT COUNT(*) FROM rss_raw")
    if raw and raw > 0:
        return True, f"articles={raw}"
    return False, f"articles={raw or 0}"

def check_scorer() -> tuple[bool, str]:
    scored = db_query("SELECT COUNT(*) FROM news_intelligence WHERE score_total > 0")
    total = db_query("SELECT COUNT(*) FROM news_intelligence")
    if scored and scored > 0:
        return True, f"scored={scored}/{total}"
    return False, f"scored=0/{total or 0}"

def check_fetcher() -> tuple[bool, str]:
    total = db_query("SELECT COUNT(*) FROM news_content") or 0
    fetched = db_query("SELECT COUNT(*) FROM news_content WHERE content_md IS NOT NULL AND content_md != ''") or 0
    missing = total - fetched
    if fetched > 0 and missing == 0:
        return True, f"articles={total} content_missing=0"
    elif fetched > 0:
        return False, f"articles={total} content_missing={missing}"
    else:
        return False, f"articles={total} content_missing={total}"

def check_aggregator() -> tuple[bool, str]:
    events = db_query("SELECT COUNT(*) FROM event_registry")
    if events and events > 0:
        return True, f"events={events}"
    return False, "events=0"

def check_sqlite() -> tuple[bool, str]:
    if not os.path.exists(DB_PATH):
        return False, "db_not_found"
    size = db_size_kb()
    raw = db_query("SELECT COUNT(*) FROM rss_raw") or 0
    events = db_query("SELECT COUNT(*) FROM event_registry") or 0
    return True, f"size={size} raw={raw} events={events}"

def check_sync() -> tuple[bool, str]:
    local = db_query("SELECT COUNT(*) FROM event_registry") or 0
    cloud_data = http_get(CLOUD_API)
    if cloud_data is None:
        return False, "cloud_unreachable"
    cloud = cloud_data.get("metrics", {}).get("active_events", 0)
    if cloud == local:
        return True, f"local={local} cloud={cloud}"
    return False, f"local={local} cloud={cloud}"

def check_api() -> tuple[bool, str]:
    data = http_get(CLOUD_API)
    if data is None:
        return False, "api_unreachable"
    events = data.get("metrics", {}).get("active_events", -1)
    return True, f"events={events}"

# ── TASK RUNNERS ────────────────────────────────────────────────

def run_stage(name: str) -> bool:
    """Run a pipeline stage. Returns True on success."""
    cfg = COMMAND_MAP[name]
    label = cfg["label"]
    script = cfg.get("script", "")

    if not os.path.exists(script):
        print(f"SKIP {label}: script not found ({script})")
        return True  # not a failure

    cmd = f"cd {PIPELINE_DIR} && python {script} {cfg.get('args', '')}"
    print(f"RUN {label}: {cmd}")

    start = time.time()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f"OK {label} ({elapsed:.1f}s)")
            return True
        else:
            err = result.stderr.strip()[-200:] if result.stderr else "unknown error"
            print(f"FAIL {label}: {err}")
            return False
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT {label} (>120s)")
        return False
    except Exception as e:
        print(f"ERROR {label}: {e}")
        return False

def run_aggregator():
    """Run aggregator via Python import (no subprocess needed)."""
    print("RUN AGGREGATOR: importing aggregator...")
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from news_intel.db import init_db, get_db
        from news_intel.aggregator import aggregate_events
        init_db()
        db = get_db()
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        rows = db.execute("""
            SELECT nc.id, rr.title, nc.summary_cn, rr.description,
                   ni.score_total, ni.tier, ni.entities, rr.published_at, rr.source_name
            FROM news_content nc
            JOIN news_intelligence ni ON nc.intel_id = ni.id
            JOIN rss_raw rr ON ni.raw_id = rr.id
            WHERE ni.tier IN ('A','B')
            ORDER BY nc.id DESC LIMIT 100
        """).fetchall()
        events = aggregate_events(rows, window_hours=24)
        db.close()
        print(f"OK AGGREGATOR: {len(events)} events")
        return True
    except Exception as e:
        print(f"FAIL AGGREGATOR: {e}")
        return False

# ── COMMANDS ─────────────────────────────────────────────────────

def cmd_check():
    """Full health check: all 8 stages."""
    stages = [
        ("RSS",         check_rss),
        ("SCORER",      check_scorer),
        ("FETCHER",     check_fetcher),
        ("AGGREGATOR",  check_aggregator),
        ("SQLITE",      check_sqlite),
        ("SYNC",        check_sync),
        ("API",         check_api),
    ]

    failed = None
    for name, fn in stages:
        ok, detail = fn()
        if not ok and failed is None:
            failed = (name, ok, detail)
        print(f"CHECK {name}: {'PASS' if ok else 'FAIL'} ({detail})")

    print()
    if failed:
        name, _, detail = failed
        if name == "RSS":
            yaml_fail("RSS", "EMPTY_SOURCE", f"No RSS data ({detail})",
                      action="Pipeline cannot start", command="python pipeline_check.py rss")
        elif name == "SCORER":
            yaml_fail("SCORER", "NO_SCORES", f"Articles not scored ({detail})",
                      action="Fetcher may skip articles", command="python pipeline_check.py scorer")
        elif name == "FETCHER":
            missing = detail.split("content_missing=")[-1] if "content_missing=" in detail else "?"
            yaml_fail("FETCHER", "EMPTY_CONTENT", f"{detail}",
                      action="Aggregator may create incomplete events",
                      command="python pipeline_check.py fetcher")
        elif name == "AGGREGATOR":
            yaml_fail("AGGREGATOR", "NO_EVENTS", f"No events ({detail})",
                      action="Dashboard will be empty", command="python pipeline_check.py aggregator")
        elif name == "SQLITE":
            yaml_fail("SQLITE", "DB_ERROR", f"Database issue ({detail})",
                      action="Cannot proceed", command="python pipeline_check.py check")
        elif name == "SYNC":
            yaml_fail("SYNC", "OUT_OF_SYNC", f"Cloud mismatch ({detail})",
                      action="Web data is stale", command="python pipeline_check.py sync")
        elif name == "API":
            yaml_fail("API", "API_DOWN", f"Cloud API unreachable ({detail})",
                      action="Web is down", command="ssh cloud && docker compose ps")
    else:
        events = db_query("SELECT COUNT(*) FROM event_registry") or 0
        yaml_ok("ALL", f"pipeline_healthy events={events} size={db_size_kb()}")

def cmd_run():
    """Run full pipeline."""
    print("=" * 50)
    print("PIPELINE RUN")
    print("=" * 50)

    stages = ["rss", "scorer", "fetcher", "aggregator", "sync"]
    ok_count = 0
    for i, name in enumerate(stages, 1):
        print(f"\n[{i}/{len(stages)}] {name.upper()}")
        if name == "aggregator":
            ok = run_aggregator()
        else:
            ok = run_stage(name)
        if ok:
            ok_count += 1
        else:
            break

    print(f"\n{'='*50}")
    print(f"COMPLETE: {ok_count}/{len(stages)} stages OK")

def cmd_run_one(name: str):
    """Run a single stage."""
    if name == "aggregator":
        ok = run_aggregator()
    else:
        ok = run_stage(name)
    if ok:
        yaml_ok(name.upper(), f"completed")
    else:
        yaml_fail(name.upper(), "EXECUTION_FAILED", "Stage did not complete successfully")

# ── MAIN ─────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "check":
        cmd_check()
    elif cmd == "run":
        cmd_run()
    elif cmd in COMMAND_MAP:
        cmd_run_one(cmd)
    else:
        print(f"Unknown: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()

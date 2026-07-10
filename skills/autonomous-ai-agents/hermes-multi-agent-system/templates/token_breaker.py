#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token daily-cost HARD circuit breaker for a Hermes multi-agent system.
Copy and adapt: HERMES_HOME, PRICE_PER_M, LOCAL_PROVIDER/LOCAL_MODEL, limit source.

What it does
------------
1. Aggregates today's cloud LLM spend from Hermes' own state.db
   (sessions.estimated_cost_usd / actual_cost_usd). For providers Hermes prices
   as 0/unknown (deepseek, local), token-estimates via PRICE_PER_M (over-estimate
   on purpose — safety first).
2. On trip (>= daily limit):
   - writes a lock file with unlock_ts = NEXT LOCAL MIDNIGHT
   - [enforce mode] switches Hermes default provider/model to a local free model
     (only affects NEW sessions/cron — Hermes freezes model per live session)
   - logs a high-risk action row to a governance DB (who/when/task/action)
   - prints a loud alert and exits 2
3. Auto-unlocks after midnight, or manual --reset restores the saved provider.

Run as a cron no_agent script every ~10 min (0 token). Modes:
  (default)   enforce (or BREAKER_MODE / TOKEN_DAILY_LIMIT_USD from env/.env)
  --detect    report only, never touch config
  --reset     remove lock + restore saved provider
  --status    print JSON state

Key lessons baked in:
  - .env is protected; read the limit from env var first, then .env text.
  - Use SYSTEM python (has pyyaml); Hermes venv python lacks 3rd-party pkgs.
  - Test with a temp HERMES_HOME copy of state.db + a tiny limit to prove
    trip->lock->auto-unlock without touching real config.
"""
import os, sys, json, sqlite3, datetime, subprocess, argparse

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
STATE_DB   = os.path.join(HERMES_HOME, "state.db")
GOV_DB     = os.path.join(HERMES_HOME, "workspace", "system", "governance.db")
LOCK_FILE  = os.path.join(HERMES_HOME, "BREAKER_LOCKED")
ENV_FILE   = os.path.join(HERMES_HOME, ".env")
STATE_FILE = os.path.join(HERMES_HOME, "workspace", "system", ".breaker_state.json")

# USD / 1M tokens. Over-estimate unknowns so the breaker trips early.
PRICE_PER_M = {
    "deepseek-v4-flash": {"in": 0.28, "out": 0.42},
    "deepseek-chat":     {"in": 0.28, "out": 0.42},
    "deepseek-reasoner": {"in": 0.55, "out": 2.19},
    "_local_free":       {"in": 0.0,  "out": 0.0},
    "_default_cloud":    {"in": 1.0,  "out": 3.0},
}
LOCAL_PROVIDER = "llm"                        # config.yaml providers.<key>
LOCAL_MODEL    = "gemma-4-E4B-it-Q4_K_M.gguf"


def read_env(key, default=None):
    if key in os.environ:                     # env var wins (test/cron override)
        return os.environ[key]
    try:
        for line in open(ENV_FILE, "r", encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return default


def local_midnight_ts(offset_days=0):
    d = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    d += datetime.timedelta(days=offset_days)
    return d.timestamp(), d


def compute_today_cost():
    midnight, _ = local_midnight_ts(0)
    con = sqlite3.connect(STATE_DB); cur = con.cursor()
    cur.execute("""SELECT model, billing_provider,
        COALESCE(actual_cost_usd, estimated_cost_usd, 0), cost_status,
        COALESCE(input_tokens,0), COALESCE(output_tokens,0),
        COALESCE(cache_read_tokens,0), COALESCE(cache_write_tokens,0)
        FROM sessions WHERE started_at >= ?""", (midnight,))
    rows = cur.fetchall(); con.close()
    total, agg = 0.0, {}
    for model, prov, c, status, tin, tout, cr, cw in rows:
        m = (model or "unknown").lower()
        if c and c > 0 and status in ("estimated", "actual"):
            cost, src = float(c), status
        else:
            p = PRICE_PER_M.get(m, PRICE_PER_M["_default_cloud"])
            cost = (tin + cr + cw) / 1e6 * p["in"] + tout / 1e6 * p["out"]
            src = "token_estimate"
        total += cost
        a = agg.setdefault(m, {"provider": prov, "cost": 0.0, "in": 0, "out": 0, "src": src})
        a["cost"] += cost; a["in"] += tin; a["out"] += tout
    bd = [{"model": k, **v, "cost": round(v["cost"], 4)} for k, v in agg.items()]
    bd.sort(key=lambda x: -x["cost"])
    return round(total, 4), bd


def ensure_gov_db():
    os.makedirs(os.path.dirname(GOV_DB), exist_ok=True)
    con = sqlite3.connect(GOV_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS high_risk_actions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT,
        trigger_task TEXT, action TEXT, detail TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS daily_cost_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT,
        total_usd REAL, limit_usd REAL, tripped INTEGER, breakdown TEXT)""")
    con.commit(); con.close()


def log_high_risk(actor, trigger, action, detail):
    ensure_gov_db(); con = sqlite3.connect(GOV_DB)
    con.execute("INSERT INTO high_risk_actions(ts,actor,trigger_task,action,detail) VALUES(?,?,?,?,?)",
                (datetime.datetime.now().isoformat(), actor, trigger, action,
                 json.dumps(detail, ensure_ascii=False)))
    con.commit(); con.close()


def log_daily(total, limit, tripped, bd):
    ensure_gov_db(); con = sqlite3.connect(GOV_DB)
    con.execute("INSERT INTO daily_cost_log(ts,day,total_usd,limit_usd,tripped,breakdown) VALUES(?,?,?,?,?,?)",
                (datetime.datetime.now().isoformat(), datetime.date.today().isoformat(),
                 total, limit, int(tripped), json.dumps(bd, ensure_ascii=False)))
    con.commit(); con.close()


def is_locked():
    if not os.path.exists(LOCK_FILE): return False, None
    try:
        info = json.load(open(LOCK_FILE, encoding="utf-8"))
        if datetime.datetime.now().timestamp() >= info.get("unlock_ts", 0):
            return False, info               # past midnight -> expired
        return True, info
    except Exception:
        return True, None


def write_lock(total, limit, bd):
    _, nm = local_midnight_ts(1)
    info = {"locked_at": datetime.datetime.now().isoformat(), "unlock_ts": nm.timestamp(),
            "unlock_at": nm.isoformat(), "total_usd": total, "limit_usd": limit, "breakdown": bd}
    json.dump(info, open(LOCK_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return info


def hermes_set(k, v):
    return subprocess.run(["hermes", "config", "set", k, str(v)], capture_output=True, text=True, timeout=60)


def save_prev_provider():
    try:
        import yaml
        cfg = yaml.safe_load(open(os.path.join(HERMES_HOME, "config.yaml"), encoding="utf-8"))
        prev = {"default": cfg.get("model", {}).get("default"), "provider": cfg.get("model", {}).get("provider")}
        json.dump(prev, open(STATE_FILE, "w", encoding="utf-8"))
        return prev
    except Exception as e:
        return {"error": str(e)}


def enforce_lock():
    prev = save_prev_provider()
    r1 = hermes_set("model.provider", LOCAL_PROVIDER); r2 = hermes_set("model.default", LOCAL_MODEL)
    return {"prev": prev, "set_provider_rc": r1.returncode, "set_model_rc": r2.returncode}


def restore_provider():
    if not os.path.exists(STATE_FILE): return {"restored": False, "reason": "no saved state"}
    prev = json.load(open(STATE_FILE, encoding="utf-8"))
    if prev.get("provider"): hermes_set("model.provider", prev["provider"])
    if prev.get("default"):  hermes_set("model.default", prev["default"])
    return {"restored": True, "prev": prev}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.reset:
        removed = os.path.exists(LOCK_FILE)
        if removed: os.remove(LOCK_FILE)
        r = restore_provider()
        log_high_risk("token_breaker", "manual_reset", "UNLOCK", {"removed_lock": removed, "restore": r})
        print(json.dumps({"reset": True, "removed_lock": removed, "restore": r}, ensure_ascii=False)); return

    limit = float(read_env("TOKEN_DAILY_LIMIT_USD", "10") or 10)
    mode = "detect" if a.detect else (read_env("BREAKER_MODE", "enforce") or "enforce")
    total, bd = compute_today_cost()
    locked_now, lock_info = is_locked()
    tripped = total >= limit
    status = {"day": datetime.date.today().isoformat(), "total_usd": total, "limit_usd": limit,
              "pct": round(total / limit * 100, 1) if limit else 0, "tripped": tripped,
              "locked": locked_now, "mode": mode, "breakdown": bd}
    if a.status:
        print(json.dumps(status, ensure_ascii=False, indent=2)); return

    log_daily(total, limit, tripped, bd)

    if os.path.exists(LOCK_FILE) and not locked_now:      # expired -> auto unlock
        restore_provider()
        try: os.remove(LOCK_FILE)
        except OSError: pass
        log_high_risk("token_breaker", "auto_reset_midnight", "UNLOCK", {})

    if tripped and not locked_now:
        info = write_lock(total, limit, bd)
        enf = enforce_lock() if mode == "enforce" else None
        log_high_risk("token_breaker", "daily_cost_limit",
                      "LOCK_AND_SWITCH_TO_LOCAL" if mode == "enforce" else "LOCK_DETECT_ONLY",
                      {"total": total, "limit": limit, "enforce": enf, "unlock_at": info["unlock_at"]})
        print(f"[TOKEN BREAKER TRIPPED] ${total} >= ${limit} | mode={mode} | unlock {info['unlock_at']}")
        if mode == "enforce":
            print(f"  default model -> local {LOCAL_MODEL} (free). Cloud API frozen for NEW sessions.")
        sys.exit(2)
    elif locked_now:
        print(f"[BREAKER] locked (${total}/${limit}). unlock {lock_info.get('unlock_at') if lock_info else 'midnight'}")
    else:
        print(f"[BREAKER] OK ${total}/${limit} ({status['pct']}%)")


if __name__ == "__main__":
    main()

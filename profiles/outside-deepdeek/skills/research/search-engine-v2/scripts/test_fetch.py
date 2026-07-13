#!/usr/bin/env python3
"""test_fetch.py — Fetch pipeline verification.

Usage:
  python test_fetch.py              Test 10 sample URLs
  python test_fetch.py --all        Test all unfetched Tier A/B
  python test_fetch.py --url URL    Test single URL
  python test_fetch.py --source SRC Test by source name

Checks:
  1. URL accessibility (cascade: direct → archive → scrapling)
  2. Content quality (>200 chars, no error pages)
  3. Strategy effectiveness per domain
  4. Timing and cost breakdown
"""

import sys
import os
import time
import sqlite3
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DB_PATH = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")

# ── Colors ──────────────────────────────────────────────────────
G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[0m"

# ── Fetch engine ────────────────────────────────────────────────

def fetch_one(url: str) -> dict:
    """Cascade fetch a single URL. Returns result dict."""
    from core.fetchers import fetch_direct, fetch_archive, fetch_scrapling, RateLimiter
    from config.settings import get_settings

    settings = get_settings()
    rl = RateLimiter(default_delay=1.0)
    strategies = [
        ("direct",   lambda: fetch_direct(url, rl)),
        ("archive",  lambda: fetch_archive(url, rl)),
        ("scrapling", lambda: fetch_scrapling(url, rl)),
    ]
    cost_map = {"direct": 1, "archive": 1, "scrapling": 2}
    trace = []

    for name, fn in strategies:
        t0 = time.time()
        try:
            content = fn()
            elapsed = time.time() - t0
            if content and len(content.strip()) >= 200:
                trace.append({"strategy": name, "ok": True, "time": round(elapsed, 1), "len": len(content)})
                return {"ok": True, "content": content, "strategy": name, "cost": cost_map[name], "trace": trace}
            else:
                trace.append({"strategy": name, "ok": False, "time": round(elapsed, 1),
                              "error": "empty" if content else "None"})
        except Exception as e:
            elapsed = time.time() - t0
            trace.append({"strategy": name, "ok": False, "time": round(elapsed, 1), "error": str(e)[:80]})

    return {"ok": False, "strategy": None, "cost": sum(cost_map[t["strategy"]] for t in trace), "trace": trace}

# ── Report ──────────────────────────────────────────────────────

def run_test(urls: list[tuple[str, str, str]], max_workers: int = 4):
    """Run fetch test and print report."""
    print(f"\n{'='*60}")
    print(f"FETCH VERIFICATION")
    print(f"{'='*60}")
    print(f"URLs: {len(urls)}  |  Workers: {max_workers}")
    print()

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_one, u[0]): u for u in urls}
        for i, f in enumerate(as_completed(futures), 1):
            url, tier, source = futures[f]
            r = f.result(timeout=60)
            r["url"] = url; r["tier"] = tier; r["source"] = source
            results.append(r)
            status = f"{G}OK{B}" if r["ok"] else f"{R}FAIL{B}"
            strat = r.get("strategy") or "-"
            print(f"  [{i:3d}/{len(urls)}] {status} {strat:10s} | {tier} | {source[:20]}")

    elapsed = time.time() - t0
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]

    # ── Summary ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"{G}SUCCESS:{B} {len(ok)}  {R}FAILED:{B} {len(fail)}  {len(ok)/(len(results) or 1)*100:.0f}%  {elapsed:.1f}s")
    print(f"{'='*60}")

    # By strategy
    strats = Counter(r.get("strategy") for r in results)
    print(f"\n  Strategy breakdown:")
    for s, c in strats.most_common():
        print(f"    {s or 'none':15s} {c}")

    # By tier
    tiers_ok = Counter(r["tier"] for r in ok)
    tiers_fail = Counter(r["tier"] for r in fail)
    print(f"\n  By tier:")
    for t in sorted(set(list(tiers_ok) + list(tiers_fail))):
        print(f"    {t}: {tiers_ok.get(t,0)} ok, {tiers_fail.get(t,0)} fail")

    # By source (top failures)
    if fail:
        src_fail = Counter(r["source"] for r in fail)
        print(f"\n  Top failed sources:")
        for s, c in src_fail.most_common(5):
            print(f"    {s[:40]:40s} {R}{c} failed{B}")

    # Error types
    all_errors = []
    for r in fail:
        for t in r.get("trace", []):
            if not t.get("ok"):
                all_errors.append(t.get("error", "?")[:60])
    if all_errors:
        err_types = Counter(all_errors)
        print(f"\n  Error types:")
        for e, c in err_types.most_common(5):
            print(f"    {e[:50]:50s} {c}")

    # Content quality
    if ok:
        lens = [len(r.get("content", "")) for r in ok]
        print(f"\n  Content quality ({len(ok)} articles):")
        print(f"    Min: {min(lens):,}  Max: {max(lens):,}  Avg: {sum(lens)//len(lens):,} chars")

    # Cost
    total_cost = sum(r.get("cost", 0) for r in results)
    print(f"\n  Total cost: {total_cost}")

    return results

# ── URL sources ─────────────────────────────────────────────────

def get_sample_urls(n: int = 10) -> list[tuple[str, str, str]]:
    """Get N sample URLs from DB, prioritizing Tier A/B unfetched."""
    if not os.path.exists(DB_PATH):
        print(f"{R}DB not found: {DB_PATH}{B}")
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT rr.article_url, ni.tier, rr.source_name
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B')
          AND (nc.id IS NULL OR nc.content_md IS NULL OR nc.content_md = '')
        ORDER BY ni.score_total DESC
        LIMIT ?
    """, (n,)).fetchall()
    conn.close()
    return [(r["article_url"], r["tier"], r["source_name"]) for r in rows if r["article_url"]]

def get_urls_by_source(source: str, n: int = 10) -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT rr.article_url, ni.tier, rr.source_name
        FROM rss_raw rr JOIN news_intelligence ni ON ni.raw_id = rr.id
        WHERE rr.source_name LIKE ?
        ORDER BY ni.score_total DESC LIMIT ?
    """, (f"%{source}%", n)).fetchall()
    conn.close()
    return [(r["article_url"], r["tier"], r["source_name"]) for r in rows if r["article_url"]]

# ── Main ─────────────────────────────────────────────────────────

def main():
    if "--url" in sys.argv:
        idx = sys.argv.index("--url")
        url = sys.argv[idx + 1]
        r = fetch_one(url)
        print(json.dumps({k: v for k, v in r.items() if k != "content"}, indent=2, ensure_ascii=False))
        if r["ok"]:
            print(f"\nContent preview: {r['content'][:300]}...")
        return

    if "--source" in sys.argv:
        idx = sys.argv.index("--source")
        source = sys.argv[idx + 1]
        urls = get_urls_by_source(source, 10)
        if not urls:
            print(f"No URLs found for source: {source}")
            return
        run_test(urls, max_workers=2)
        return

    if "--all" in sys.argv:
        urls = get_sample_urls(200)
    else:
        urls = get_sample_urls(10)

    if not urls:
        print("No URLs to test")
        return

    run_test(urls, max_workers=4)

if __name__ == "__main__":
    main()

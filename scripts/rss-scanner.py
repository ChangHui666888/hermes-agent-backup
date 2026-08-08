#!/usr/bin/env python3
"""Cron wrapper: dispatches to real rss-scanner.py in outside-deepdeek profile (2026-08-08).

Hermes cron requires scripts in ~/AppData/Local/hermes/scripts/, referenced by filename only.
此 wrapper 只负责跳转 — 真实 scanner + 依赖(config/news_intel) 均在生产 profile，不迁移到 cron 目录。
"""
import sys, os, subprocess

REAL = os.path.join(
    os.path.dirname(__file__),
    "../profiles/outside-deepdeek/skills/research/search-engine-v2/scripts/hermes-cron/rss-scanner.py"
)

if not os.path.exists(REAL):
    print("[FATAL] rss-scanner.py not found at %s" % REAL, file=sys.stderr)
    sys.exit(1)

os.chdir(os.path.dirname(REAL))
result = subprocess.run([sys.executable, "-u", REAL] + sys.argv[1:])
sys.exit(result.returncode)

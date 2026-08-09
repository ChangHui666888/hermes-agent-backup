#!/usr/bin/env python3
"""Cron wrapper: dispatches to real monitor_pipeline.py in outside-deepdeek profile.
   推送流水线监控指标到 VPS /internal/monitor (admin 看板展示)。"""
import sys, os, subprocess

REAL = os.path.join(
    os.path.dirname(__file__),
    "../profiles/outside-deepdeek/skills/research/search-engine-v2/scripts/monitor_pipeline.py"
)

if not os.path.exists(REAL):
    print("[FATAL] monitor_pipeline.py not found at %s" % REAL, file=sys.stderr)
    sys.exit(1)

os.chdir(os.path.dirname(REAL))
result = subprocess.run([sys.executable, REAL, "--push"] + [a for a in sys.argv[1:] if a != "--push"])
sys.exit(result.returncode)

#!/usr/bin/env python3
"""Cron wrapper: dispatches to the real auto-pipeline.py in outside-deepdeek profile."""
import sys, os, subprocess

REAL = os.path.join(
    os.path.dirname(__file__),
    "../profiles/outside-deepdeek/skills/research/search-engine-v2/scripts/auto-pipeline.py"
)

if not os.path.exists(REAL):
    print(f"[FATAL] auto-pipeline.py not found at {REAL}", file=sys.stderr)
    sys.exit(1)

os.chdir(os.path.dirname(REAL))
result = subprocess.run([sys.executable, REAL] + sys.argv[1:])
sys.exit(result.returncode)

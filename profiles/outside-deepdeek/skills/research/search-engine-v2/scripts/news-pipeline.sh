#!/usr/bin/env bash
# News Pipeline — triggered by Hermes cron
# Style: aligned with rss-scan.sh
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/bin:$PATH"
export NEWS_API_BASE="${NEWS_API_BASE:-http://100.107.117.23:8001}"

python "$SCRIPT_DIR/news-pipeline.py" "$@"
STATUS=$?

# ── 摘要 ──
REPORT="$HOME/.hermes/news-pipeline-report.json"
if [ -f "$REPORT" ]; then
    python3 -c "
import json
d = json.load(open('$REPORT'))
tiers = {'batch_tier_a':'DeepSeek V4 Flash','batch_tier_b':'Qwen3-1.7B','batch_tier_c':'Python 规则'}
print()
print('📊 News Pipeline Summary')
print(f\"  Batch Input   : {d.get('batch_input',0)}\")
print(f\"  New           : {d.get('batch_new',0)}\")
print(f\"  Duplicate     : {d.get('batch_duplicate',0)}\")
for k,label in tiers.items():
    v = d.get(k,0)
    if v: print(f\"  {label:>16s}: {v}\")
print(f\"  Enhanced      : {d.get('batch_enhanced',0)}\")
print(f\"  Pushed        : {d.get('batch_pushed',0)}\")
print(f\"  Push Failed   : {d.get('batch_push_failed',0)}\")
print(f\"  Total Articles: {d.get('total_articles',0)}\")
print(f\"  Duration      : {d.get('duration_sec',0)}s\")
"
fi

exit "$STATUS"

#!/usr/bin/env bash
# RSS Scanner — triggered by Hermes cron
# Script and scanner are in the same directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/bin:$PATH"
python "$SCRIPT_DIR/rss-scanner.py" 2>&1

# Show summary of new articles found
REPORT="$HOME/.hermes/rss-scanner-report.json"
if [ -f "$REPORT" ]; then
    NEW=$(python -c "import json; d=json.load(open('$REPORT')); print(d['articles_new'])")
    if [ "$NEW" -gt "0" ]; then
        echo ""
        echo "📰 $NEW new articles found across all feeds"
        python3 -c "
import json
d=json.load(open('$REPORT'))
for a in d['new_articles'][:5]:
    print(f'  • [{a[\"feed\"]}] {a[\"title\"][:80]}')
"
    else
        echo "✅ No new articles"
    fi
fi

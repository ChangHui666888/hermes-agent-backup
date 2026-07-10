#!/usr/bin/env bash
# news-pipeline.sh — Hermes cron job: RSS评分 → 增强 → 推送到云端

export NEWS_API_BASE="${NEWS_API_BASE:-http://100.107.117.23:8001}"

PIPELINE_DIR="C:/Users/ChangHui/AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2/scripts"

cd "$PIPELINE_DIR" 2>/dev/null || cd "C:\\Users\\ChangHui\\AppData\\Local\\hermes\\profiles\\outside-deepdeek\\skills\\research\\search-engine-v2\\scripts" 2>/dev/null || {
    echo "ERROR: cannot cd to pipeline dir"
    exit 1
}

python -m news_intel.pipeline --hours 1 --limit 200

#!/usr/bin/env bash
# git-backup.sh — 每日 Git 备份推送
set -Eeuo pipefail

HERMES_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERMES_DIR"

DATE=$(date +%Y-%m-%d_%H-%M)

git add -A
git commit -m "auto-backup: $DATE" || echo "(nothing to commit)"
git push origin master 2>&1 || echo "WARN: push failed (network?)"

echo "[$(date +%H:%M:%S)] git backup done"

#!/usr/bin/env bash
# git-backup.sh v2 — 生产版 Git 备份 (每天12:00, Windows Task Scheduler)
set -Eeuo pipefail

SOURCE="C:/Users/ChangHui/AppData/Local/hermes"
LOG_FILE="$SOURCE/scripts/logs/git-backup.log"

mkdir -p "$(dirname "$LOG_FILE")"

log()  { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG_FILE"; }
die()  { log "FATAL: $1"; exit 1; }

log "=== GIT BACKUP v2 START ==="

cd "$SOURCE" || die "cannot cd to $SOURCE"

# ── 验证 Git 仓库 ──
git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"

# ── 自动获取分支名 ──
BRANCH=$(git branch --show-current)
log "branch: $BRANCH"

# ── 暂存 + 提交 ──
git add -A
if git diff --cached --quiet; then
    log "nothing to commit"
else
    git commit -m "auto-backup: $DATE" 2>&1 | tee -a "$LOG_FILE"
    log "committed"
fi

# ── 推送 ──
if git push origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
    log "push OK"
else
    die "PUSH_FAILED"
fi

log "=== GIT BACKUP DONE ==="

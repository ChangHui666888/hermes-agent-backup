#!/usr/bin/env bash
# full-backup.sh v2 — 生产版全量备份 (每天18:00, Windows Task Scheduler)
set -Eeuo pipefail

SOURCE="C:/Users/ChangHui/AppData/Local/hermes"
DEST="F:/hermes-backup"
LOG_DIR="$SOURCE/scripts/logs"
STATE_DIR="$SOURCE/backup-state"
DATE=$(date +%Y-%m-%d_%H-%M)
BACKUP_NAME="hermes_${DATE}"
LOG_FILE="$LOG_DIR/full-backup.log"
STATE_FILE="$STATE_DIR/last-success"

mkdir -p "$DEST" "$LOG_DIR" "$STATE_DIR"

log()  { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG_FILE"; }
die()  { log "FATAL: $1"; exit 1; }

log "=== FULL BACKUP v2 START ==="
log "Source: $SOURCE"
log "Dest:   $DEST/$BACKUP_NAME"

# ── 执行备份 ──
if rsync -av --delete \
    --exclude='node_modules/' \
    --exclude='hermes-agent/node_modules/' \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='audio_cache/' \
    --exclude='image_cache/' \
    --exclude='cache/' \
    "$SOURCE/" "$DEST/$BACKUP_NAME/" >> "$LOG_FILE" 2>&1; then
    log "rsync OK"
else
    die "rsync failed"
fi

# ── 成功标记 ──
echo "$DATE" > "$STATE_FILE"
echo "OK" > "$DEST/$BACKUP_NAME/backup.ok"
log "marker written"

# ── 清理 14 天前旧备份 ──
DELETED=$(find "$DEST" -maxdepth 1 -name "hermes_*" -type d -mtime +14 2>/dev/null | wc -l)
find "$DEST" -maxdepth 1 -name "hermes_*" -type d -mtime +14 -exec rm -rf {} \; 2>/dev/null || true
log "cleanup: removed $DELETED old backups (14d+)"

log "=== FULL BACKUP DONE ==="

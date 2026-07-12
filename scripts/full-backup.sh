#!/usr/bin/env bash
# full-backup.sh v2 — 生产版全量备份 (每天18:00, Windows Task Scheduler)
#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE="C:/Users/ChangHui/AppData/Local/hermes"
DEST="F:/hermes-backup"
LOG_DIR="$DEST/logs"               # 移出源目录
STATE_DIR="$DEST/state"
LOCK_FILE="/tmp/hermes-fullbackup.lock"

# 依赖检测
command -v rsync >/dev/null || { echo "需要 rsync" >&2; exit 1; }

# 并发控制
exec 200>"$LOCK_FILE"
flock -n 200 || { echo "备份已在运行"; exit 1; }

# 目标盘检测
[ -d "F:/" ] || { echo "F: 盘不可用"; exit 1; }

mkdir -p "$DEST" "$LOG_DIR" "$STATE_DIR"

DATE=$(date +%Y-%m-%d_%H-%M)
BACKUP_NAME="hermes_${DATE}"
LOG_FILE="$LOG_DIR/full-backup.log"

log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG_FILE"; }
die() { log "FATAL: $1"; exit 1; }

log "=== FULL BACKUP START ==="

# 源完整性检查（按需调整标志文件）
[ -f "$SOURCE/package.json" ] || die "源目录哨兵文件缺失，终止备份"

# 备份
if rsync -av --delete \
    --exclude='node_modules/' \
    ... \
    "$SOURCE/" "$DEST/$BACKUP_NAME/" >> "$LOG_FILE" 2>&1; then
    log "rsync 成功"
else
    die "rsync 失败"
fi

echo "$DATE" > "$STATE_DIR/last-success"
echo "OK" > "$DEST/$BACKUP_NAME/backup.ok"

# 清理（基于目录名日期）
CUTOFF=$(date -d "-14 days" +%Y-%m-%d)
for bak in "$DEST"/hermes_????-??-??_??-??; do
    [ -d "$bak" ] || continue
    bname=$(basename "$bak")
    if [[ "${bname:6:10}" < "$CUTOFF" ]]; then
        log "清理旧备份: $bname"
        rm -rf "$bak"
    fi
done

log "=== FULL BACKUP DONE ==="
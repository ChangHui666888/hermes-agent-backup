#!/usr/bin/env bash
# full-backup.sh v3 — 生产版全量备份 (每天18:00, Windows Task Scheduler)
#
# v3 修复:
#   1. rsync 在 Git Bash 不存在, 且原命令残留未替换的 "..." 占位符
#      → 改用 Windows 自带 robocopy (MSYS_NO_PATHCONV=1 避免 /E 被转成 E:/)
#   2. 源哨兵文件原用 package.json, 但 hermes 根目录没有该文件 → 改用 config.yaml
#   3. 保留期清理 bname:6:10 起始索引错误(多含一个 "_"), 修正为 :7:10
#   4. flock 在 Git Bash 不存在 → 用 mkdir 原子锁防并发
#   5. 去掉 set -e, 每步显式检查并记录错误
set -uo pipefail

SOURCE="C:/Users/ChangHui/AppData/Local/hermes"
DEST="F:/hermes-backup"
LOG_DIR="$DEST/logs"
STATE_DIR="$DEST/state"
LOCK_FILE="/tmp/hermes-fullbackup.lock"
RETENTION_DAYS=14

# ── 目标盘检测 ──
[ -d "F:/" ] || { echo "[$(date '+%Y-%m-%d %H:%M:%S')] FATAL: F: 盘不可用" >&2; exit 1; }

mkdir -p "$DEST" "$LOG_DIR" "$STATE_DIR"

DATE=$(date +%Y-%m-%d_%H-%M)
BACKUP_NAME="hermes_${DATE}"
LOG_FILE="$LOG_DIR/full-backup.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }
die() { log "FATAL: $1"; exit 1; }

# ── 并发锁 (mkdir 原子性) ──
if mkdir "$LOCK_FILE" 2>/dev/null; then
    trap 'rmdir "$LOCK_FILE" 2>/dev/null || true' EXIT
else
    log "已有备份进程在运行, 本次跳过"
    exit 0
fi

log "=== FULL BACKUP v3 START ==="

# ── 源完整性检查 (v3: 哨兵改为 config.yaml) ──
[ -f "$SOURCE/config.yaml" ] || die "源目录哨兵文件缺失, 终止备份"

# ── robocopy 备份 ──
# /E 递归含空目录 /COPY:DAT 数据+属性+时间戳 /DCOPY:DAT 目录元数据
# /XD /XF 按名称匹配排除 (robocopy 支持裸名匹配)
# /R:3 /W:5 失败重试3次间隔5秒; /NFL /NDL /NJH /NJS /NP 精简日志
# 返回码: 0-7 成功(1=有文件复制), >=8 失败
log "备份到 $DEST/$BACKUP_NAME ..."
MSYS_NO_PATHCONV=1 robocopy "$SOURCE" "$DEST/$BACKUP_NAME" \
    /E /COPY:DAT /DCOPY:DAT /R:3 /W:5 \
    /NFL /NDL /NJH /NJS /NP \
    /XD .git node node_modules cache audio_cache image_cache sessions \
        sandboxes lsp mcp-installs gateway-service hermes-agent __pycache__ bk 新建文件夹 bin \
    /XF *.pyc *.log *.lock *.pid *.rar state.db-shm state.db-wal .update_check \
        models_dev_cache.json provider_models_cache.json ollama_cloud_models_cache.json >> "$LOG_FILE" 2>&1
RC=$?
if [ "$RC" -ge 8 ]; then
    die "robocopy 失败 (code=$RC)"
fi
log "robocopy 完成 (code=$RC)"

# ── 完成标记 ──
echo "$DATE" > "$STATE_DIR/last-success"
echo "OK" > "$DEST/$BACKUP_NAME/backup.ok"

# ── 清理旧备份 (v3: 修正子串索引 :7:10) ──
CUTOFF=$(date -d "-$RETENTION_DAYS days" +%Y-%m-%d)
log "保留期: $RETENTION_DAYS 天, 清理早于 $CUTOFF 的备份"
for bak in "$DEST"/hermes_????-??-??_??-??; do
    [ -d "$bak" ] || continue
    bname=$(basename "$bak")
    bdate="${bname:7:10}"   # hermes_YYYY-MM-DD_HH-MM → 第7字符起取10位 = YYYY-MM-DD
    if [ -n "$bdate" ] && [[ "$bdate" < "$CUTOFF" ]]; then
        log "清理旧备份: $bname"
        rm -rf "$bak"
    fi
done

log "=== FULL BACKUP DONE ==="

#!/usr/bin/env bash
# git-backup.sh v3 — 生产版 Git 备份 (每天12:00, Windows Task Scheduler)
#
# v3 修复:
#   1. $DATE 此前从未定义 → 提交信息为空; 现在显式生成 yyyy-MM-dd_HH-mm
#   2. gateway.lock/gateway.pid/gateway_state.json/state.db-shm/ticker_* 等
#      高频运行时文件此前被 git 跟踪 → git add -A 每次都会读到被 gateway
#      进程锁住的文件, 失败后 set -e 静默退出, 从不产生提交。
#      现在这些文件已在 .gitignore + git rm --cached 中解除跟踪。
#   3. 日志加入日期 (此前只有时分秒, 无法区分跨天运行)
#   4. 进程锁防并发 (flock 在 Git Bash 不存在, 用 mkdir 原子锁)
#   5. 去掉 set -e, 每步显式检查并记录错误, 失败不再静默
set -uo pipefail

SOURCE="C:/Users/ChangHui/AppData/Local/hermes"
LOG_FILE="$SOURCE/scripts/logs/git-backup.log"
LOCK_FILE="/tmp/hermes-gitbackup.lock"

mkdir -p "$(dirname "$LOG_FILE")"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }
die()  { log "FATAL: $1"; exit 1; }

# ── 并发锁 (mkdir 原子性) ──
if mkdir "$LOCK_FILE" 2>/dev/null; then
    trap 'rmdir "$LOCK_FILE" 2>/dev/null || true' EXIT
else
    log "已有备份进程在运行, 本次跳过"
    exit 0
fi

log "=== GIT BACKUP v3 START ==="

cd "$SOURCE" || die "cannot cd to $SOURCE"

# ── 验证 Git 仓库 ──
git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"

# ── 自动获取分支名 ──
BRANCH=$(git branch --show-current) || die "无法获取分支名"
[ -n "$BRANCH" ] || die "分支名为空"
log "branch: $BRANCH"

# ── 备份日期 (v3 修复点) ──
DATE=$(date +%Y-%m-%d_%H-%M)

# ── 暂存 ──
git add -A || die "git add 失败"
git diff --cached --quiet
if [ $? -eq 0 ]; then
    log "nothing to commit"
else
    if git commit -m "auto-backup: $DATE" >> "$LOG_FILE" 2>&1; then
        log "committed ($DATE)"
    else
        die "git commit 失败"
    fi
fi

# ── 推送 ──
if git push origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
    log "push OK ($BRANCH)"
else
    die "PUSH_FAILED"
fi

log "=== GIT BACKUP DONE ==="

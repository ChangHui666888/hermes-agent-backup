#!/usr/bin/env bash
# full-backup.sh — 全量备份到 F 盘
# 用法: bash full-backup.sh
# 每3天执行一次
set -Eeuo pipefail

SOURCE="$HOME/AppData/Local/hermes"
DEST="F:/hermes-backup"
DATE=$(date +%Y-%m-%d_%H-%M)
BACKUP_NAME="hermes_${DATE}"

echo "=== 全量备份 Hermes 到 F 盘 ==="
echo "源:   $SOURCE"
echo "目标: $DEST/$BACKUP_NAME"

mkdir -p "$DEST"

# rsync 全量拷贝（保留最近7个备份）
rsync -av --exclude='node_modules/' \
          --exclude='hermes-agent/node_modules/' \
          --exclude='.git/' \
          --exclude='__pycache__/' \
          --exclude='*.pyc' \
          --exclude='audio_cache/' \
          --exclude='image_cache/' \
          --exclude='cache/' \
          "$SOURCE/" "$DEST/$BACKUP_NAME/" 2>&1

# 删除 7 天前的旧备份
find "$DEST" -maxdepth 1 -name "hermes_*" -type d -mtime +7 -exec rm -rf {} \; 2>/dev/null || true

echo ""
echo "✅ 备份完成: $DEST/$BACKUP_NAME"
echo "   现存备份:"
ls -d "$DEST"/hermes_* 2>/dev/null | tail -5

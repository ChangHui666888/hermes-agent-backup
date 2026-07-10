#!/usr/bin/env bash
# ============================================
# Hermes Dashboard / Web UI 保活脚本
# 检查 dashboard 是否运行，若未运行则启动
# ============================================
set -e

DASHBOARD_PID=$(pgrep -f "hermes dashboard --skip-build" || true)

if [ -z "$DASHBOARD_PID" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Dashboard 未运行，正在启动..."
  nohup hermes dashboard --skip-build --port 9119 --host 127.0.0.1 \
    > "$HOME/.hermes/logs/dashboard.log" 2>&1 &
  sleep 3
  NEW_PID=$(pgrep -f "hermes dashboard --skip-build" || echo "FAILED")
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Dashboard 启动完成 (PID: $NEW_PID)"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Dashboard 运行中 (PID: $DASHBOARD_PID)"
fi

# 检查端口是否监听
if netstat -an 2>/dev/null | grep -q "127.0.0.1:9119.*LISTEN"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ Dashboard 端口 9119 正常监听"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠ Dashboard 端口 9119 未监听"
fi

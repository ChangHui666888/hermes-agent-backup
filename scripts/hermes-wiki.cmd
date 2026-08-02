@echo off
chcp 65001 >nul
title Hermes Agent + Wiki
echo =========================================
echo   Hermes Agent + Wiki 启动中心
echo =========================================
echo.
echo [1/4] 验证 Wiki 环境变量...
set WIKI_PATH=C:\Users\ChangHui\wiki
set OBSIDIAN_VAULT_PATH=C:\Users\ChangHui\wiki
echo   WIKI_PATH=%WIKI_PATH%
echo.
echo [2/4] 更新图谱数据...
cd /d C:\Users\ChangHui\wiki
python scripts\wiki-graph.py
echo.
echo [3/4] 注册 Cron 任务（后台同步）...
cd /d C:\Users\ChangHui
hermes cron list | findstr "wiki-sync" >nul
if %ERRORLEVEL% NEQ 0 (
    echo   → 注册 wiki 自动同步（每30分钟）
    hermes cron create "30m" --name "wiki-sync" --script "bash C:\Users\ChangHui\wiki\scripts\wiki-sync.sh" --no-agent 2>nul
) else (
    echo   ✓ Wiki 同步任务已存在
)
echo.
echo [4/4] 启动 Hermes Agent...
echo.
echo 如需启动 Gateway 让 Cron 自动执行:
echo   hermes gateway install  （需要管理员权限）
echo.
echo 默认启动: Hermes CLI
echo =========================================
echo.
hermes

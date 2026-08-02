@echo off
REM ============================================================
REM Hermes Agent 开机自启脚本 (Windows)
REM 启动: Gateway (后台) + Dashboard / Web UI (后台)
REM ============================================================
cd /d C:\Users\ChangHui

REM ---- 日志目录 ----
set LOG_DIR=C:\Users\ChangHui\.hermes\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set STARTUP_LOG=%LOG_DIR%\startup.log
echo [%date% %time%] Hermes 开机自启脚本执行中... > "%STARTUP_LOG%"

REM ---- 1. 启动 Hermes Gateway (后台, 用于 cron 调度) ----
echo [%date% %time%] 启动 Hermes Gateway... >> "%STARTUP_LOG%"
start /B "" "C:\Program Files\Git\usr\bin\bash.exe" -c "cd /c/Users/ChangHui && nohup hermes gateway run > /c/Users/ChangHui/.hermes/logs/gateway.log 2>&1 &"
echo [%date% %time%] Hermes Gateway 已启动 (后台) >> "%STARTUP_LOG%"

REM ---- 等待 gateway 就绪 ----
timeout /t 8 /nobreak > nul

REM ---- 2. 启动 Hermes Dashboard / Web UI (后台, 端口 9119) ----
echo [%date% %time%] 启动 Hermes Dashboard (Web UI)... >> "%STARTUP_LOG%"
start /B "" "C:\Program Files\Git\usr\bin\bash.exe" -c "cd /c/Users/ChangHui && nohup hermes dashboard --skip-build --port 9119 --host 127.0.0.1 > /c/Users/ChangHui/.hermes/logs/dashboard.log 2>&1 &"
echo [%date% %time%] Hermes Dashboard 已启动 (后台, http://127.0.0.1:9119) >> "%STARTUP_LOG%"

REM ---- 3. 可选的: 启动 Hermes Web UI (如果与 dashboard 分开) ----
REM 目前 hermes dashboard 即 Web UI, 无需额外启动

echo [%date% %time%] Hermes 开机自启完成 >> "%STARTUP_LOG%"

REM ---- 输出状态 ----
echo.
echo [Hermes] 开机自启完成!
echo [Hermes] Gateway 日志: .hermes\logs\gateway.log
echo [Hermes] Dashboard: http://127.0.0.1:9119
echo [Hermes] Dashboard 日志: .hermes\logs\dashboard.log
echo.

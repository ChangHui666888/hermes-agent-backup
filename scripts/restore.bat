@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set SOURCE=F:\hermes-backup
set TARGET=%LOCALAPPDATA%\hermes
set LOG_DIR=%TARGET%\scripts\logs
set LOG_FILE=%LOG_DIR%\restore.log

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :log "============================================"
call :log "  Hermes 一键恢复 v2"
call :log "============================================"
call :log ""

if not exist "%SOURCE%" (
    call :log "[错误] 备份目录不存在: %SOURCE%"
    pause
    exit /b 1
)

REM PowerShell 获取日期（不依赖区域设置）
for /f "delims=" %%d in ('powershell -Command "Get-Date -Format yyyyMMdd"') do set DATE_FMT=%%d

REM 查找最新备份（有 backup.ok 标记的）
set LATEST=
for /f "delims=" %%d in ('dir /b /ad /o-n "%SOURCE%\hermes_*" 2^>nul') do (
    if exist "%SOURCE%\%%d\backup.ok" (
        set LATEST=%SOURCE%\%%d
        goto :found
    )
)

:found
if "%LATEST%"=="" (
    call :log "[错误] 没有找到有效备份（缺少 backup.ok）"
    pause
    exit /b 1
)

call :log "最新有效备份: %LATEST%"
call :log "目标位置: %TARGET%"
call :log ""

REM ============================================
REM 第一次确认
REM ============================================
set /p CONFIRM1="输入 YES 确认要进行恢复操作: "
if /i not "%CONFIRM1%"=="YES" (
    call :log "已取消。"
    pause
    exit /b 0
)

call :log ""
call :log "即将从以下备份恢复:"
call :log "  %LATEST%"
call :log "当前 %TARGET% 将备份到 %TARGET%_old_%DATE_FMT%"
call :log ""

REM ============================================
REM 第二次确认
REM ============================================
set /p CONFIRM2="再次输入 YES 确认（此操作不可撤销）: "
if /i not "%CONFIRM2%"=="YES" (
    call :log "已取消。"
    pause
    exit /b 0
)

call :log ""
call :log "[1/3] 停止 Hermes 网关..."
taskkill /f /im "hermes-gateway.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

call :log "[2/3] 备份当前版本到 %TARGET%_old_%DATE_FMT% ..."
if exist "%TARGET%" (
    robocopy "%TARGET%" "%TARGET%_old_%DATE_FMT%" /E /NFL /NDL /NJH /NJS >nul 2>&1
)

call :log "[3/3] 镜像恢复中（/MIR：删除多余文件）..."
robocopy "%LATEST%" "%TARGET%" /MIR /NFL /NDL /NJH /NJS

call :log ""
call :log "============================================"
call :log "  恢复完成！"
call :log "============================================"
call :log "  Hermes: %TARGET%"
call :log "  旧版本: %TARGET%_old_%DATE_FMT%"
call :log "  日志:   %LOG_FILE%"
call :log ""
call :log "请手动重启 Hermes。"
pause
exit /b 0

:log
echo [%date% %time:~0,8%] %~1 >> "%LOG_FILE%"
echo %~1
goto :eof

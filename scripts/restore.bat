@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================
REM Hermes 一键恢复 v3 — 双目录恢复
REM 恢复主目录 %LOCALAPPDATA%\hermes + 用户目录 ~/.hermes
REM 本文件常驻备份盘 F:\hermes-backup\restore.bat (full-backup 每次刷新)
REM ============================================

set SOURCE=F:\hermes-backup
set TARGET=%LOCALAPPDATA%\hermes
set HOME_TARGET=%USERPROFILE%\.hermes
set LOG_DIR=%TARGET%\scripts\logs
set LOG_FILE=%LOG_DIR%\restore.log

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :log "============================================"
call :log "  Hermes 一键恢复 v3 (含 ~/.hermes)"
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
call :log "主目录恢复目标: %TARGET%"
call :log "用户目录恢复目标: %HOME_TARGET%"
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
call :log "当前 %TARGET%  将备份到 %TARGET%_old_%DATE_FMT%"
call :log "当前 %HOME_TARGET%  将备份到 %HOME_TARGET%_old_%DATE_FMT%"
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
call :log "[1/5] 停止 Hermes 网关..."
taskkill /f /im "hermes-gateway.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

call :log "[2/5] 备份当前主目录到 %TARGET%_old_%DATE_FMT% ..."
if exist "%TARGET%" (
    robocopy "%TARGET%" "%TARGET%_old_%DATE_FMT%" /E /NFL /NDL /NJH /NJS >nul 2>&1
)

call :log "[3/5] 镜像恢复主目录 (/MIR, 排除 .hermes-home) ..."
robocopy "%LATEST%" "%TARGET%" /MIR /XD .hermes-home /NFL /NDL /NJH /NJS
if %errorlevel% GEQ 8 (
    call :log "  [警告] 主目录 robocopy 返回 %errorlevel% (>=8 为失败), 请检查日志"
)

call :log "[4/5] 备份当前用户目录到 %HOME_TARGET%_old_%DATE_FMT% ..."
if exist "%HOME_TARGET%" (
    robocopy "%HOME_TARGET%" "%HOME_TARGET%_old_%DATE_FMT%" /E /NFL /NDL /NJH /NJS >nul 2>&1
)

call :log "[5/5] 恢复用户目录 ~/.hermes (rss-archive.db + config-agent 配置) ..."
if exist "%LATEST%\.hermes-home" (
    robocopy "%LATEST%\.hermes-home" "%HOME_TARGET%" /MIR /NFL /NDL /NJH /NJS
    if %errorlevel% GEQ 8 (
        call :log "  [警告] 用户目录 robocopy 返回 %errorlevel% (>=8 为失败)"
    )
) else (
    call :log "  备份中无 .hermes-home, 跳过用户目录恢复"
)

call :log ""
call :log "============================================"
call :log "  恢复完成！"
call :log "============================================"
call :log "  Hermes 主目录: %TARGET%"
call :log "  用户目录: %HOME_TARGET%"
call :log "  旧版本: %TARGET%_old_%DATE_FMT%"
call :log "         %HOME_TARGET%_old_%DATE_FMT%"
call :log "  日志:   %LOG_FILE%"
call :log ""
call :log "请手动重启 Hermes。"
pause
exit /b 0

:log
echo [%date% %time:~0,8%] %~1 >> "%LOG_FILE%"
echo %~1
goto :eof

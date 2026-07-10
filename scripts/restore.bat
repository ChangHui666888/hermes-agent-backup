@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   Hermes 一键恢复脚本
echo ============================================
echo.
echo ⚠️  警告：此操作将覆盖当前 Hermes 目录！
echo.

set SOURCE=F:\hermes-backup
set TARGET=%LOCALAPPDATA%\hermes

if not exist "%SOURCE%" (
    echo [错误] 备份目录不存在: %SOURCE%
    pause
    exit /b 1
)

REM 查找最新备份
set LATEST=
for /f "delims=" %%d in ('dir /b /ad /o-n "%SOURCE%\hermes_*" 2^>nul') do (
    set LATEST=%SOURCE%\%%d
    goto :found
)

:found
if "%LATEST%"=="" (
    echo [错误] 没有找到备份
    pause
    exit /b 1
)

echo 最新备份: %LATEST%
echo 目标位置: %TARGET%
echo.

REM ============================================
REM 第一次确认
REM ============================================
set /p CONFIRM1="输入 YES 确认要进行恢复操作: "
if /i not "%CONFIRM1%"=="YES" (
    echo 已取消。
    pause
    exit /b 0
)

echo.
echo 即将从以下备份恢复:
echo   %LATEST%
echo.
echo 当前 %TARGET% 将被备份到 %TARGET%_old_%date:~0,4%%date:~5,2%%date:~8,2%
echo.

REM ============================================
REM 第二次确认
REM ============================================
set /p CONFIRM2="再次输入 YES 确认（此操作不可撤销）: "
if /i not "%CONFIRM2%"=="YES" (
    echo 已取消。
    pause
    exit /b 0
)

echo.
echo [1/3] 停止 Hermes 相关进程...
taskkill /f /im "hermes.exe" >nul 2>&1
taskkill /f /im "python.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/3] 备份当前版本到 %TARGET%_old ...
if exist "%TARGET%" (
    robocopy "%TARGET%" "%TARGET%_old_%date:~0,4%%date:~5,2%%date:~8,2%" /E /NFL /NDL /NJH /NJS >nul 2>&1
)

echo [3/3] 恢复中...
robocopy "%LATEST%" "%TARGET%" /E /NFL /NDL /NJH /NJS

echo.
echo ============================================
echo   恢复完成！
echo ============================================
echo   Hermes 目录: %TARGET%
echo   当前版本已备份到: %TARGET%_old_%date:~0,4%%date:~5,2%%date:~8,2%
echo.
echo 请手动重启 Hermes。
pause

@echo off
REM Wiki 推送脚本 - 任意目录运行即可推送 wiki
cd /d C:\Users\ChangHui\wiki
git push %*
echo.
echo Wiki pushed! If you see "Everything up-to-date", wiki is already synced.

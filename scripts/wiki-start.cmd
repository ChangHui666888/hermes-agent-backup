@echo off
chcp 65001 >nul
title Hermes Wiki
echo ========================================
echo   Hermes Wiki - LLM Wiki + Obsidian + Graph
echo ========================================
echo.
echo [1/3] 更新图谱数据...
cd /d C:\Users\ChangHui\wiki
python scripts\wiki-graph.py
echo.
echo [2/3] 打开 Obsidian（Wiki 仓库）...
start "" "D:\Program Files\Obsidian\Obsidian.exe" "obsidian://open?vault=C:%5CUsers%5CChangHui%5Cwiki"
echo.
echo [3/3] 知识图谱已就绪！
echo.
echo   Obsidian Graph View: Obsidian 中 Ctrl+G 查看
echo   交互式 HTML 图谱:   graph.html (拖入浏览器)
echo.
echo ========================================
pause

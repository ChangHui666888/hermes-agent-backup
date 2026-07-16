import sys, os, time, json, sqlite3, subprocess, httpx
from collections import defaultdict, Counter
from datetime import datetime
from dotenv import load_dotenv   # 别忘了导入

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# === 第一步：明确当前工作目录 ===
print(f"当前工作目录: {os.getcwd()}")

# === 第二步：显式指定 .env 文件路径（放在脚本同目录）===
dotenv_path = os.path.join(SCRIPT_DIR, ".env")
load_dotenv(dotenv_path=dotenv_path)
print(f"尝试加载 .env 文件: {dotenv_path}")

# === 第三步：打印环境变量（只显示前几位）===
TOKEN = os.environ.get("NEWS_API_TOKEN") or ""
TAVILY_KEY = os.environ.get("TAVILY_KEY") or ""
print(f"NEWS_API_TOKEN 读取结果: {TOKEN[:10] if TOKEN else '未找到'}...")
print(f"TAVILY_KEY 读取结果: {TAVILY_KEY[:10] if TAVILY_KEY else '未找到'}...")

# 后面的代码保持不变 ...
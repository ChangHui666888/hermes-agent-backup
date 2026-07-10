#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron 入口: Token 每日费用硬熔断检测。
实际逻辑在 workspace/system/token_breaker.py, 这里只是 cron 调用的薄封装,
以 enforce 模式运行 (触顶自动切本地免费模型 + 记录高风险操作)。
no_agent 模式: stdout 直接作为 cron 投递内容, 0 token 消耗。
"""
import os, sys, subprocess

HERMES_HOME = os.environ.get("HERMES_HOME", r"C:\Users\ChangHui\AppData\Local\hermes")
BREAKER = os.path.join(HERMES_HOME, "workspace", "system", "token_breaker.py")
# 显式用系统 Python (含 pyyaml/pip); 不用 Hermes venv python (缺第三方包)
SYS_PY = r"C:\Users\ChangHui\AppData\Local\Programs\Python\Python311\python.exe"
PY = SYS_PY if os.path.exists(SYS_PY) else sys.executable

if not os.path.exists(BREAKER):
    print(f"[BREAKER-CRON] 找不到熔断器主脚本: {BREAKER}")
    sys.exit(1)

# 用系统 python 跑 (Hermes venv 无第三方包); 默认 enforce 模式
r = subprocess.run([PY, BREAKER], capture_output=True, text=True, timeout=120)
sys.stdout.write(r.stdout)
if r.stderr.strip():
    sys.stdout.write("\n[stderr] " + r.stderr)
# 传递退出码: 2=已熔断, 让 cron 记录里能区分
sys.exit(0 if r.returncode in (0, 2) else r.returncode)

"""RSS Scanner — Cron wrapper"""
import subprocess, sys, os

script_dir = os.path.dirname(os.path.abspath(__file__))
scanner = os.path.join(script_dir, "rss-scanner.py")

result = subprocess.run([sys.executable, scanner], capture_output=True, text=True, timeout=180)
print(result.stdout)
if result.returncode != 0:
    print(f"STDERR: {result.stderr[:200]}")
sys.exit(result.returncode)

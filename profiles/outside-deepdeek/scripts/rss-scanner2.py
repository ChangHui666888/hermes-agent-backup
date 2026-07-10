import sys
import os
import subprocess

# 定义目标脚本所在的目录
SCRIPT_DIR = r"C:\Users\ChangHui\AppData\Local\hermes\profiles\outside-deepdeek\scripts"

# 拼接完整的 Python 脚本路径
target_script = os.path.join(SCRIPT_DIR, "rss-scanner.py")

# 添加自定义的环境变量 PATH（对应原脚本中的 export PATH=$HOME/bin:$PATH）
home_dir = os.path.expanduser("~")
custom_path = os.path.join(home_dir, "bin") + os.pathsep + os.environ.get("PATH", "")

# 复制当前系统环境变量，并更新 PATH
current_env = os.environ.copy()
current_env["PATH"] = custom_path

try:
    # 执行目标 Python 脚本，并实时输出结果（2>&1 效果）
    result = subprocess.run(
        [sys.executable, target_script],
        env=current_env,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True
    )
    # 根据子进程的退出码退出
    sys.exit(result.returncode)
except Exception as e:
    print(f"执行脚本失败: {e}", file=sys.stderr)
    sys.exit(1)

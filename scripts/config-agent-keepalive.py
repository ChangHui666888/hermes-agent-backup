#!/usr/bin/env python3
"""config-agent 保活检查：如果 agent 没在运行则启动"""
import subprocess, socket, os, sys

def agent_running():
    try:
        s = socket.create_connection(("127.0.0.1", 8890), timeout=2)
        s.close()
        return True
    except Exception:
        return False

def main():
    if agent_running():
        return
    # 启动 agent
    agent_path = os.path.expanduser("~/AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2/scripts/hermes-cron/config-agent.py")
    if os.path.exists(agent_path):
        subprocess.Popen([sys.executable, "-u", agent_path],
                         stdout=open(os.path.expanduser("~/.hermes/config-agent.log"), "a"),
                         stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        print("config-agent restarted")

if __name__ == "__main__":
    main()

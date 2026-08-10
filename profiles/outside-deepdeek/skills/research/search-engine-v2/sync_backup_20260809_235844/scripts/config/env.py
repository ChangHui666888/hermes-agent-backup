"""
config/env.py — 环境参数加载器

所有主机 IP、端口、Token 等环境参数集中管理，禁止在代码中硬编码。
优先级: 环境变量 > .env 文件 > 内置默认值

用法:
    from config.env import get_env
    cloud_ip = get_env("CLOUD_IP", "100.107.117.23")
    local_ip = get_env("LOCAL_IP", "100.126.188.44")
"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """加载 .env 文件（若存在），不覆盖已有环境变量。"""
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",   # scripts/.env
        Path.home() / ".hermes" / ".env",                  # ~/.hermes/.env
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass


# 启动时加载一次 .env
_load_dotenv()


def get_env(key: str, default: str = "") -> str:
    """读取环境变量，缺失返回默认值。"""
    return os.environ.get(key, default)


# ── 关键环境参数（含默认值）─────────────────────────────────

# 云端主机 (VPS)
CLOUD_IP = get_env("CLOUD_IP", "100.107.117.23")
CLOUD_PORT = get_env("CLOUD_PORT", "80")
CLOUD_API = f"http://{CLOUD_IP}:{CLOUD_PORT}"

# 本地主机 (Windows)
LOCAL_IP = get_env("LOCAL_IP", "100.126.188.44")
LOCAL_AGENT_PORT = get_env("LOCAL_AGENT_PORT", "8890")
LOCAL_AGENT_URL = f"http://{LOCAL_IP}:{LOCAL_AGENT_PORT}/config/sync"

# Token / 密钥
INTERNAL_TOKEN = get_env("INTERNAL_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")
LOCAL_AGENT_TOKEN = get_env("LOCAL_AGENT_TOKEN", "hermes-config-sync-2026")

# 代理 / 外部服务
SOCKS5_PROXY = get_env("SOCKS5_PROXY", "socks5://127.0.0.1:10808")
SEARXNG_BASE = get_env("SEARXNG_BASE", f"http://{CLOUD_IP}:8080")

# DeepSeek / Qwen
DEEPSEEK_API_BASE = get_env("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = get_env("DEEPSEEK_API_KEY", "")
QWEN_BASE = get_env("QWEN_BASE", "http://127.0.0.1:1234/v1")

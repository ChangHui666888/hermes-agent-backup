#!/usr/bin/env python3
"""
config-agent.py — 本地配置接收 Agent

接收 VPS 配置中心推送的配置，写入本地 JSON 供脚本读取。
保证 VPS 挂了本地也能用最近一次配置继续生产。

用法:
  python config-agent.py            # 前台运行 (阻塞)
  python config-agent.py --daemon   # 后台运行 (Windows Task Scheduler)

端点:
  POST /config/sync  接收配置推送 {token, config, synced_at}
  GET  /config/status 健康检查
  GET  /config       返回本地当前配置
"""

import json
import os
import re
import sys
import time
import secrets
import threading
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

# ── 配置 ────────────────────────────────────────────────
AGENT_PORT = 8890
CONFIG_FILE = os.path.expanduser("~/.hermes/pipeline-config.json")
TOKEN = os.environ.get("LOCAL_AGENT_TOKEN", "hermes-config-sync-2026")

# ── 安全限制 ────────────────────────────────────────────
MAX_CONFIG_KEYS = 200        # 最大配置项数（防超大payload）
MAX_VALUE_LEN = 500          # 字符串值最大长度
MAX_PAYLOAD_BYTES = 256 * 1024  # 最大请求体 256KB

# 允许的配置键白名单（防注入未知键）
ALLOWED_KEYS = {
    # RSS
    "rss.max_workers", "rss.timeout", "rss.hot_timeout", "rss.cold_timeout",
    "rss.quarantine_failures", "rss.quarantine_seconds", "rss.proxy",
    # Pipeline
    "pipeline.batch_size", "pipeline.max_workers", "pipeline.batch_timeout",
    "pipeline.rate_delay", "pipeline.cloud_chunk", "pipeline.content_chunk",
    "pipeline.sync_hours",
    # AI
    "ai.tier_a_threshold", "ai.tier_b_threshold", "ai.qwen_base", "ai.qwen_model",
    "ai.qwen_timeout", "ai.qwen_max_tokens", "ai.deepseek_model",
    "ai.deepseek_timeout", "ai.deepseek_max_tokens", "ai.deepseek_temperature",
    # Scoring
    "scoring.source_weight", "scoring.impact_weight", "scoring.entity_weight",
    "scoring.market_weight", "scoring.velocity_weight", "scoring.velocity_window",
    "scoring.jaccard_threshold",
    # Aggregate
    "aggregate.event_threshold", "aggregate.merge_threshold", "aggregate.window_hours",
    # Crawl
    "crawl.min_content_len", "crawl.direct_timeout", "crawl.browser_timeout",
    "crawl.rate_limit", "crawl.cascade_timeout",
    # 视频抓取链路 (Step 3.6)
    "crawl.video_enabled", "crawl.video_batch_size", "crawl.video_workers",
    "crawl.video_min_score", "crawl.video_timeout", "crawl.video_max_content",
    "crawl.video_strategy", "crawl.video_patterns",
}


# 已知策略名（用于域名策略值校验）
KNOWN_STRATEGIES = {
    "direct", "archive", "google_cache", "jina", "scrapling",
    "tavily", "browser", "search_snippet", "searxng_alt", "computer_use",
}


def _validate_key(key: str) -> bool:
    """键名校验：模块参数 或 crawl.domain.{域名}.{strategy|failing} 或 rss.feeds。"""
    if key == "rss.feeds":
        return True
    # 域名策略键: crawl.domain.xxx.strategy / crawl.domain.xxx.failing
    if key.startswith("crawl.domain."):
        parts = key.split(".")
        # crawl.domain.<domain>.strategy|failing → domain 可含点
        if len(parts) < 4:
            return False
        field = parts[-1]
        if field not in ("strategy", "failing"):
            return False
        domain = ".".join(parts[2:-1])
        # 域名只允许字母数字点连字符
        return bool(re.fullmatch(r"[a-zA-Z0-9.-]+", domain))
    # 普通模块键: 必须在 whitelist
    if key not in ALLOWED_KEYS:
        return False
    parts = key.split(".")
    if len(parts) != 2:
        return False
    return all(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", p) for p in parts)


def _sanitize_feeds(value) -> list:
    """校验并规范化 RSS 源列表（接受 list 或 JSON 字符串）。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            raise ValueError("rss.feeds 不是有效JSON")
    if not isinstance(value, list):
        raise ValueError("rss.feeds 必须是数组")
    if len(value) > 200:
        raise ValueError("源数量超限")
    sanitized = []
    for s in value:
        if not isinstance(s, dict):
            raise ValueError("源必须是对象")
        name = str(s.get("name", ""))[:100]
        url = str(s.get("url", ""))[:500]
        if not name or not url.startswith("http"):
            raise ValueError("源缺少名称或非法URL")
        sanitized.append({
            "name": name, "url": url,
            "region": str(s.get("region", "intl"))[:20],
            "tier": str(s.get("tier", "warm"))[:20],
            "category": str(s.get("category", "其他"))[:50],
            # V4 Feed Registry 字段 (2026-08-07): 供评分 importance 联动 / 前端展示
            "subcategory": str(s.get("subcategory", ""))[:50],
            "country": str(s.get("country", ""))[:50],
            "language": str(s.get("language", "en"))[:10],
            "type": str(s.get("type", "rss"))[:20],
            "importance": str(s.get("importance", "C"))[:1],
            "enabled": bool(s.get("enabled", True)),
        })
    return sanitized


def _sanitize_value(key: str, value) -> object:
    """值校验：int/float/str/bool/list[str]/list[dict]。"""
    if key == "rss.feeds":
        return _sanitize_feeds(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) > MAX_VALUE_LEN:
            raise ValueError(f"值过长 ({len(value)} > {MAX_VALUE_LEN})")
        # 防注入：字符串值禁止控制字符
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("字符串值包含控制字符")
        return value
    if isinstance(value, list):
        # 通用 list：长度与元素类型校验；仅域名策略键要求已知策略名
        if not value or len(value) > 10:
            raise ValueError("列表长度非法")
        if not all(isinstance(v, str) for v in value):
            raise ValueError("含非字符串元素")
        if key.startswith("crawl.domain.") and not all(v in KNOWN_STRATEGIES for v in value):
            raise ValueError("含未知策略名")
        return value
    raise ValueError(f"不支持的值类型: {type(value).__name__}")

# ── 云端轮询配置（本地拉取模式，免防火墙入站）────────────
CLOUD_CONFIG_URL = os.environ.get("CLOUD_CONFIG_URL", "http://100.107.117.23/admin/pipeline/config/export-internal")
POLL_INTERVAL = int(os.environ.get("CONFIG_POLL_INTERVAL", "60"))  # 秒
# 轮询 VPS 用 INTERNAL_TOKEN（VPS 推送用 LOCAL_AGENT_TOKEN）
POLL_TOKEN = os.environ.get("POLL_TOKEN", os.environ.get("INTERNAL_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ"))


def _poll_cloud_config():
    """从 VPS 拉取配置并写入本地。失败保留最近配置。"""
    try:
        import httpx
        r = httpx.get(CLOUD_CONFIG_URL, headers={"X-Internal-Token": POLL_TOKEN}, timeout=10)
        if r.status_code != 200:
            print(f"[config-agent] 轮询失败 HTTP {r.status_code}")
            return
        data = r.json()
        config = data.get("config", {})
        if not isinstance(config, dict) or not config:
            print("[config-agent] 轮询返回空配置")
            return
        # 安全校验（复用推送的校验逻辑）
        sanitized: dict = {}
        for key, value in config.items():
            if _validate_key(key):
                try:
                    sanitized[key] = _sanitize_value(key, value)
                except ValueError:
                    pass
        if sanitized:
            atomic_write(sanitized)
            print(f"[config-agent] 轮询同步 {len(sanitized)} 项配置")
    except Exception as e:
        print(f"[config-agent] 轮询异常: {str(e)[:80]}")


def _poller_loop():
    while True:
        try:
            _poll_cloud_config()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


# ── 原子写入 ────────────────────────────────────────────


def atomic_write(data: dict) -> None:
    """原子写入配置 JSON，避免半写损坏。"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


def load_local_config() -> dict:
    """读取本地配置，文件不存在返回空。"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── HTTP Handler ────────────────────────────────────────


class ConfigHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # 静默日志，避免刷屏

    def _send_json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        if length > MAX_PAYLOAD_BYTES:
            return {"_error": "payload_too_large"}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def do_POST(self):
        if self.path != "/config/sync":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        body = self._read_body()
        if body.get("_error") == "payload_too_large":
            self._send_json(413, {"ok": False, "error": "Payload too large"})
            return
        # Token 强校验（常量时间比较防时序攻击）
        token = body.get("token")
        if not isinstance(token, str) or len(token) != len(TOKEN) or not secrets.compare_digest(token, TOKEN):
            self._send_json(403, {"ok": False, "error": "Invalid token"})
            return
        config = body.get("config", {})
        if not isinstance(config, dict) or not config:
            self._send_json(400, {"ok": False, "error": "Empty config"})
            return
        if len(config) > MAX_CONFIG_KEYS:
            self._send_json(400, {"ok": False, "error": f"配置项过多 ({len(config)} > {MAX_CONFIG_KEYS})"})
            return
        # 校验每个键值（防注入）
        sanitized: dict = {}
        rejected: list[str] = []
        for key, value in config.items():
            if not _validate_key(key):
                rejected.append(key)
                continue
            try:
                sanitized[key] = _sanitize_value(key, value)
            except ValueError as e:
                rejected.append(f"{key}:{e}")
        # 如果有注入尝试，拒绝全部并告警
        if rejected:
            print(f"[config-agent] ⚠️ 拒绝 {len(rejected)} 个非法配置项: {rejected[:10]}")
            self._send_json(422, {"ok": False, "error": "非法配置项", "rejected": rejected[:20]})
            return
        if not sanitized:
            self._send_json(400, {"ok": False, "error": "无有效配置项"})
            return
        # 写入
        atomic_write(sanitized)
        self._send_json(200, {"ok": True, "count": len(sanitized), "synced_at": datetime.now().isoformat()})
        print(f"[config-agent] 已接收 {len(sanitized)} 项配置 → {CONFIG_FILE}")

    def do_GET(self):
        if self.path == "/config/status":
            cfg = load_local_config()
            self._send_json(200, {"ok": True, "items": len(cfg), "file": CONFIG_FILE})
        elif self.path == "/config":
            cfg = load_local_config()
            self._send_json(200, cfg)
        else:
            self._send_json(404, {"ok": False, "error": "Not found"})


# ── 启动 ────────────────────────────────────────────────


def run(port: int = AGENT_PORT):
    # 启动轮询线程（拉取模式，VPS挂了保留最近配置）
    poller = threading.Thread(target=_poller_loop, daemon=True)
    poller.start()
    server = HTTPServer(("0.0.0.0", port), ConfigHandler)
    print(f"[config-agent] 监听 :{port} | 配置写入 {CONFIG_FILE} | 轮询 {POLL_INTERVAL}s")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="本地配置接收 Agent")
    parser.add_argument("--daemon", action="store_true", help="后台运行 (Windows: 用 pythonw)")
    parser.add_argument("--port", type=int, default=AGENT_PORT, help="监听端口")
    args = parser.parse_args()

    if args.daemon and hasattr(os, "fork"):
        # Unix 后台运行
        pid = os.fork()
        if pid == 0:
            run(args.port)
        else:
            print(f"[config-agent] 后台启动 PID={pid}")
    else:
        # Windows: 前台运行（用 Task Scheduler 或 nohup 后台）
        run(args.port)


if __name__ == "__main__":
    main()

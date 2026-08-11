"""
config/loader.py — 本地配置加载器

从本地 pipeline-config.json 读取配置（由 config-agent 从云端同步）。
读取失败或缺失时回退到代码内置默认值，保证 VPS 挂了也能生产。

用法:
    from config.loader import load_config, get_setting
    cfg = load_config()
    workers = get_setting(cfg, "pipeline.max_workers", default=5)
"""

import json
import os
from typing import Any

CONFIG_FILE = os.path.expanduser("~/.hermes/pipeline-config.json")

# ── 值规范化：容忍 JSON 字符串形式的 list ────────────────


def _normalize_value(value: Any) -> Any:
    """如果值是 JSON 字符串形式的数组，解析为 list。"""
    if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    return value

# ── 内置默认值（与云端 SEED_CONFIG 保持一致）─────────────
DEFAULTS: dict[str, Any] = {
    # RSS
    "rss.max_workers": 14,
    "rss.timeout": 10,
    "rss.hot_timeout": 6,
    "rss.cold_timeout": 15,
    "rss.quarantine_failures": 3,
    "rss.quarantine_seconds": 3600,
    "rss.deadlink_failures": 60,
    "rss.deadlink_probe_interval": 604800,
    "rss.tier_hot_interval": 300,
    "rss.tier_warm_interval": 900,
    "rss.tier_cold_interval": 900,
    "rss.proxy": "socks5://127.0.0.1:10808",
    # Pipeline
    "pipeline.batch_size": 20,
    "pipeline.max_workers": 5,
    "pipeline.batch_timeout": 600,
    "pipeline.rate_delay": 0.3,
    "pipeline.cloud_chunk": 50,
    "pipeline.content_chunk": 200,
    "pipeline.sync_hours": 2,
    # AI
    "ai.tier_a_threshold": 90,
    "ai.tier_b_threshold": 60,
    "ai.qwen_base": "http://127.0.0.1:1234/v1",
    "ai.qwen_model": "qwen3-1.7b-instruct",
    "ai.qwen_timeout": 60,
    "ai.qwen_max_tokens": 1024,
    "ai.deepseek_model": "deepseek-v4-flash",
    "ai.deepseek_timeout": 45,
    "ai.deepseek_max_tokens": 800,
    "ai.deepseek_temperature": 0.1,
    # Scoring
    "scoring.source_weight": 20,
    "scoring.impact_weight": 30,
    "scoring.entity_weight": 20,
    "scoring.market_weight": 20,
    "scoring.velocity_weight": 10,
    "scoring.velocity_window": 30,
    "scoring.jaccard_threshold": 0.5,
    # Aggregate
    "aggregate.event_threshold": 60,
    "aggregate.merge_threshold": 75,
    "aggregate.window_hours": 24,
    # Crawl
    "crawl.min_content_len": 200,
    "crawl.direct_timeout": 20,
    "crawl.browser_timeout": 30,
    "crawl.rate_limit": 1.0,
    "crawl.cascade_timeout": 60,
    # 视频抓取链路 (Step 3.6)
    "crawl.video_enabled": True,
    "crawl.video_batch_size": 6,
    "crawl.video_workers": 2,
    "crawl.video_min_score": 60,
    "crawl.video_timeout": 420,
    "crawl.video_max_content": 20000,
    "crawl.video_strategy": ["browser", "archive", "jina", "tavily"],
    "crawl.video_patterns": ["/video/", "/videos/"],
}

# ── 域名级策略默认值 — 单一来源: ../news-platform-v8/config/domain_strategies.json ──
# ⚠️ 与后端 admin_config.py 共享同一 JSON (改域名策略只改这一个文件)。
_DOMAIN_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "news-platform-v8", "config", "domain_strategies.json")
try:
    with open(_DOMAIN_JSON, "r", encoding="utf-8") as _f:
        DOMAIN_DEFAULTS: dict[str, dict] = json.load(_f)
except Exception:
    # JSON 缺失时回退最小默认（正常部署必含 news-platform-v8 子树）
    DOMAIN_DEFAULTS = {}

# 为每个域名生成配置键默认值
for _domain, _meta in DOMAIN_DEFAULTS.items():
    DEFAULTS[f"crawl.domain.{_domain}.strategy"] = _meta["strategy"]
    DEFAULTS[f"crawl.domain.{_domain}.failing"] = _meta["failing"]

# 缓存
_cache: dict[str, Any] | None = None


def _coerce_type(key: str, value: Any, default: Any) -> Any:
    """按默认值类型强转配置值（兼容字符串存储的数字）。"""
    if value is None:
        return default
    if isinstance(default, int) and not isinstance(value, bool):
        try: return int(value)
        except (ValueError, TypeError): return default
    if isinstance(default, float) and not isinstance(value, bool):
        try: return float(value)
        except (ValueError, TypeError): return default
    return value


def load_config(force: bool = False) -> dict[str, Any]:
    """读取本地配置，缺失的补默认值。带缓存。"""
    global _cache
    if _cache is not None and not force:
        return _cache
    cfg: dict[str, Any] = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    # 值规范化（容忍 JSON 字符串数组）
    cfg = {k: _normalize_value(v) for k, v in cfg.items()}
    # 按默认值类型强转（字符串数字 → int/float）
    for key, default in DEFAULTS.items():
        if key in cfg:
            cfg[key] = _coerce_type(key, cfg[key], default)
    # 补全默认值
    merged = {**DEFAULTS, **cfg}
    _cache = merged
    return merged


def get_setting(cfg: dict[str, Any], key: str, default: Any = None) -> Any:
    """读取单个配置项，缺失回退 default。"""
    return cfg.get(key, default)


def reload():
    """强制重新读取（用于运行中检测配置变化）。"""
    global _cache
    _cache = None
    return load_config()

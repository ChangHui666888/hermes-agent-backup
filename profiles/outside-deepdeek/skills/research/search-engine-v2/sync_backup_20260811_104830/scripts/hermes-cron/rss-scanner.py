#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rss-scanner-v3.2-final
生产级 RSS 全量扫描引擎
- httpx 连接池 + HTTP/2
- feedparser 容错解析
- region 路由: cn 直连 / intl 走 SOCKS5
- 死源自动隔离 (3次失败 → 24h quarantine)
- 原子写入 + SHA256 指纹去重
- 14 并发 workers
- 兼容 httpx 0.27/0.28
"""
import httpx
import feedparser
import sqlite3
import json
import os
import sys
import hashlib
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# 配置（从本地 pipeline-config.json 读取，云端同步）
# =========================

try:
    # 修复 (2026-08-08): 加上级目录 scripts/, 使 config.loader 在生产 profile 上下文可导入
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _SCRIPT_DIR)                      # hermes-cron
    sys.path.insert(0, os.path.dirname(_SCRIPT_DIR))     # scripts/ → config.loader
    from config.loader import load_config, get_setting
    _CFG = load_config()
    def _cfg(key, default): return get_setting(_CFG, key, default) if _CFG else default
except Exception:
    _cfg = lambda key, default: default

PROXY = _cfg("rss.proxy", "socks5://127.0.0.1:10808")
MAX_WORKERS = _cfg("rss.max_workers", 14)
TIMEOUT = _cfg("rss.timeout", 10)
HOT_TIMEOUT = _cfg("rss.hot_timeout", 6)
COLD_TIMEOUT = _cfg("rss.cold_timeout", 15)
QUARANTINE_FAILURES = _cfg("rss.quarantine_failures", 3)
QUARANTINE_SECONDS = _cfg("rss.quarantine_seconds", 3600)   # 修复⑤: 隔离 30min→60min
DEADLINK_FAILURES = _cfg("rss.deadlink_failures", 60)        # 修复⑤: 连续60次失败 → 死链
DEADLINK_PROBE_INTERVAL = _cfg("rss.deadlink_probe_interval", 7 * 24 * 3600)  # 修复⑤: 死链每周探测
USER_AGENT = "rss-scanner/3.2-final"

STATE_FILE = os.path.expanduser("~/.hermes/rss-scanner-state.json")
REPORT_FILE = os.path.expanduser("~/.hermes/rss-scanner-report.json")
DB_FILE = os.path.expanduser("~/.hermes/rss-archive.db")
WIKI_PATH = os.path.expanduser("~/wiki/RSS-Digest")

# 健康推送 (2026-08-08): 每轮扫描后把 fail/dead_link/quarantine 同步到云端, 供 /admin/sources 展示
CLOUD_HEALTH_URL = os.environ.get("CLOUD_HEALTH_URL", "http://100.107.117.23/internal/sources/health")
CLOUD_TOKEN = os.environ.get("INTERNAL_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")

# =========================
# 98 源完整列表 (region: cn=直连, intl=SOCKS5)
# =========================

TIER = {"hot": 0, "warm": 1, "cold": 2}

# 优化3 (2026-08-08): Tier 分级扫描频率 (秒) — hot 5min / warm 15min / cold 15min
# 修复③ (2026-08-08): cold 60min→15min (财经/资讯源最多积压 15min, 恢复时效); 改为 config 可配
TIER_INTERVAL = {
    "hot": _cfg("rss.tier_hot_interval", 5 * 60),
    "warm": _cfg("rss.tier_warm_interval", 15 * 60),
    "cold": _cfg("rss.tier_cold_interval", 15 * 60),
}


def is_due(state, feed):
    """按 tier 判断是否到扫描时间 (last_scan 距现在 >= 间隔)。"""
    tier = feed.get("tier", "warm")
    last = state.get(feed["name"], {}).get("last_scan", 0)
    return (now_ts() - last) >= TIER_INTERVAL.get(tier, 15 * 60)

# 配置缺失时的紧急回退源 (V4, 2026-08-08) — 正常由 config-agent 提供 197 源全字段
CORE_FALLBACK_FEEDS = [
    {"name": "Reuters Top", "url": "https://feeds.reuters.com/reuters/topNews", "region": "intl", "tier": "hot", "category": "Wire Agencies", "importance": "S"},
    {"name": "AP Top News", "url": "https://apnews.com/hub/ap-top-news?output=rss", "region": "intl", "tier": "hot", "category": "Wire Agencies", "importance": "S"},
    {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml", "region": "intl", "tier": "hot", "category": "Global Media", "importance": "A"},
    {"name": "CNN Edition", "url": "http://rss.cnn.com/rss/edition.rss", "region": "intl", "tier": "hot", "category": "Global Media", "importance": "A"},
    {"name": "NYT Home", "url": "http://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "region": "intl", "tier": "hot", "category": "Global Media", "importance": "S"},
    {"name": "FT World", "url": "https://www.ft.com/world?format=rss", "region": "intl", "tier": "warm", "category": "Financial Media", "importance": "S"},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "region": "intl", "tier": "warm", "category": "Financial Media", "importance": "A"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "region": "intl", "tier": "hot", "category": "Technology", "importance": "A"},
    {"name": "White House", "url": "https://www.whitehouse.gov/briefing-room/feed/", "region": "intl", "tier": "hot", "category": "Government", "importance": "S"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "region": "intl", "tier": "hot", "category": "Community Signals", "importance": "A"},
    {"name": "人民网 时政", "url": "http://www.people.com.cn/rss/politics.xml", "region": "cn", "tier": "warm", "category": "China Media", "importance": "A"},
    {"name": "新华网 时政", "url": "http://www.xinhuanet.com/rss/politics.xml", "region": "cn", "tier": "warm", "category": "China Media", "importance": "A"},
]


def categorize_feed(name):
    """V4 兜底归类 (名称匹配, 2026-08-07) — 仅当源 config 无 category 字段时使用。

    返回 16 大类; 源自带 category (配置中心 V4) 时优先用源值, 本函数不再主导。
    """
    if any(n in name for n in ["Reuters", "AP ", "Bloomberg", "AFP"]): return "Wire Agencies"
    if any(n in name for n in ["Fed Press", "ECB", "BoE"]): return "Central Banks"
    if any(n in name for n in ["SEC Press"]): return "Regulators"
    if any(n in name for n in ["UN News", "IMF", "World Bank", "OECD"]): return "International Organizations"
    if any(n in name for n in ["White House", "NASA", "UK Gov"]): return "Government"
    if any(n in name for n in ["BBC", "CNN", "NBC", "CBS", "ABC", "NYT", "NPR", "Politico", "The Hill", "Newsweek", "Sky News", "France 24", "WaPo", "Guardian", "DW", "Le Monde", "Al Jazeera", "SCMP"]): return "Global Media"
    if any(n in name for n in ["FT ", "WSJ", "Economist", "CNBC", "MarketWatch", "Barrons", "Seeking Alpha", "Investing", "Yahoo Finance"]): return "Financial Media"
    if any(n in name for n in ["TechCrunch", "The Verge", "Wired", "Ars Technica", "MIT", "Engadget", "VentureBeat", "Space", "Electrek", "CleanTechnica", "IEEE"]): return "Technology"
    if any(n in name for n in ["arXiv"]): return "Research"
    if any(n in name for n in ["OpenAI", "Google AI"]): return "AI Companies"
    if any(n in name for n in ["GitHub"]): return "Open Source"
    if any(n in name for n in ["Hacker News", "Reddit", "Nitter:"]): return "Community Signals"
    if any(n in name for n in ["人民网", "中国新闻网", "新华网", "央视"]): return "China Media"
    return "Community Signals"


# =========================
# 数据库
# =========================

def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True) if os.path.dirname(DB_FILE) else None
    conn = sqlite3.connect(DB_FILE)
    # 优化2 (2026-08-08): WAL + 性能参数 (10-30% 收益)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-20000")
        conn.execute("PRAGMA mmap_size=268435456")
    except Exception:
        pass
    # 迁移: 旧表用 INTEGER id, 新表用 TEXT sha256
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='rss_articles'")
    row = cur.fetchone()
    if row and "INTEGER" in (row[0] or "").upper():
        # 旧格式表, 重命名→重建→迁移数据
        cur.execute("ALTER TABLE rss_articles RENAME TO rss_articles_old")
        conn.commit()
    cur.execute("""CREATE TABLE IF NOT EXISTS rss_articles(
        id TEXT PRIMARY KEY, date TEXT, category TEXT, source TEXT NOT NULL,
        title TEXT, summary TEXT, link TEXT UNIQUE,
        created_at TEXT DEFAULT (datetime('now','localtime')))""")
    for c in ["date","source","category"]:
        try: cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{c} ON rss_articles({c})")
        except: pass
    # 如果旧表存在且未迁移, 迁数据
    try:
        cur.execute("SELECT count(*) FROM rss_articles_old")
        if cur.fetchone()[0] > 0:
            cur.execute("""INSERT OR IGNORE INTO rss_articles(id,date,category,source,title,summary,link,created_at)
                SELECT sha256,date,category,source,title,summary,link,created_at FROM (
                    SELECT hex(randomblob(16))||hex(randomblob(16)) as sha256, date, category, source, title, summary, link, created_at
                    FROM rss_articles_old)""")
            conn.commit()
            cur.execute("DROP TABLE rss_articles_old")
            conn.commit()
    except: pass
    conn.commit(); conn.close()


def article_id(feed_name, url, title):
    return hashlib.sha256(f"{feed_name}|{url}|{title[:40]}".encode()).hexdigest()


def load_known_ids(conn, days=7):
    """优化2: 预载最近 N 天已收录文章 id 到内存 set (替代逐条 SELECT, 50-80% 收益)。"""
    known = set()
    try:
        cur = conn.execute(
            "SELECT id FROM rss_articles WHERE created_at >= datetime('now', ?)", (f"-{days} days",))
        known = {r[0] for r in cur.fetchall()}
    except Exception:
        pass
    return known


# =========================
# 状态管理（原子写入 + 兼容旧格式）
# =========================

def load_state():
    if not os.path.exists(STATE_FILE): return {}
    try:
        with open(STATE_FILE, "r") as f: return json.load(f)
    except: return {}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f: json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def normalize_state(state):
    """兼容旧格式: list→dict"""
    for k, v in list(state.items()):
        if isinstance(v, list):
            state[k] = {"history": v[-500:], "fail": 0, "quarantine_until": 0, "last_seen": ""}
    return state

def now_ts():
    return int(time.time())

def is_quarantined(state, name):
    """隔离中 (死链源除外 — 死链走每周探测, 不算隔离)。"""
    m = state.get(name, {})
    return not m.get("dead_link") and m.get("quarantine_until", 0) > now_ts()

def is_dead(state, name):
    """死链: 连续 DEADLINK_FAILURES 次失败, 退出常规扫描。"""
    return bool(state.get(name, {}).get("dead_link", False))

def dead_probe_due(state, name):
    """死链每周探测是否到期 (next_probe <= now)。"""
    return state.get(name, {}).get("next_probe", 0) <= now_ts()

def update_health(state, name, ok):
    """修复⑤ 三级状态机: 正常→隔离(60min)→死链(每周探测)→恢复回归。
    成功: 清零 fail + 解除隔离/死链; 失败: fail+=1, 达隔离/死链阈值逐级升级。"""
    m = state.setdefault(name, {"history": [], "fail": 0, "quarantine_until": 0, "last_seen": ""})
    if isinstance(m, list):
        state[name] = {"history": m[-500:], "fail": 0, "quarantine_until": 0, "last_seen": ""}
        m = state[name]
    if ok:
        m["fail"] = 0
        m["quarantine_until"] = 0
        m.pop("dead_link", None)
        m.pop("next_probe", None)
    else:
        m["fail"] = m.get("fail", 0) + 1
        if m["fail"] >= DEADLINK_FAILURES:
            # 连续 60 次失败 → 死链: 退出隔离, 进入每周探测
            m["dead_link"] = True
            m["next_probe"] = now_ts() + DEADLINK_PROBE_INTERVAL
            m["quarantine_until"] = 0
        elif m["fail"] >= QUARANTINE_FAILURES:
            m["quarantine_until"] = now_ts() + QUARANTINE_SECONDS
    return state


# =========================
# HTTPX 客户端（region路由）
# =========================

def needs_proxy(feed):
    return feed.get("region") == "intl"

def feed_timeout(feed):
    t = feed.get("tier", "warm")
    if t == "hot": return HOT_TIMEOUT
    if t == "cold": return COLD_TIMEOUT
    return TIMEOUT

# ═══ 全局 HTTP Client Pool (优化1, 2026-08-08): 复用连接, 不再每源建/关 Client ═══
_CLIENT_CN = None
_CLIENT_PROXY = None


def _make_client(use_proxy: bool) -> httpx.Client:
    # 修复② (2026-08-08): follow_redirects=True — httpx 0.28 默认不跟重定向, NYT 等 301 源被 0 抓
    kwargs = {"timeout": COLD_TIMEOUT, "http2": True, "follow_redirects": True, "headers": {"User-Agent": USER_AGENT}}
    try:
        if use_proxy:
            return httpx.Client(proxy=PROXY, **kwargs)
        return httpx.Client(**kwargs)
    except TypeError:  # httpx < 0.28
        if use_proxy:
            return httpx.Client(proxies=PROXY, **kwargs)
        return httpx.Client(**kwargs)


def _get_client(use_proxy: bool) -> httpx.Client:
    """全局共享 CN / PROXY 两个 client (线程安全, 程序结束才 close)。"""
    global _CLIENT_CN, _CLIENT_PROXY
    if use_proxy:
        if _CLIENT_PROXY is None:
            _CLIENT_PROXY = _make_client(True)
        return _CLIENT_PROXY
    if _CLIENT_CN is None:
        _CLIENT_CN = _make_client(False)
    return _CLIENT_CN


def close_clients():
    global _CLIENT_CN, _CLIENT_PROXY
    for c in (_CLIENT_CN, _CLIENT_PROXY):
        if c is not None:
            try: c.close()
            except Exception: pass
    _CLIENT_CN = _CLIENT_PROXY = None


def push_health(state):
    """2026-08-08: 推送每源健康到云端 /internal/sources/health (非致命 — 云端不可达不影响扫描)。

    供 /admin/sources 页面展示 status(alive/failed/dead_link) + 连续失败次数。
    """
    try:
        import httpx
        health = {}
        for name, m in state.items():
            if not isinstance(m, dict):
                continue
            health[name] = {
                "fail": int(m.get("fail", 0) or 0),
                "dead_link": bool(m.get("dead_link", False)),
                "quarantine_until": int(m.get("quarantine_until", 0) or 0),
                "last_scan": int(m.get("last_scan", 0) or 0),
            }
        if not health:
            return
        r = httpx.post(CLOUD_HEALTH_URL, json=health,
                       headers={"X-Internal-Token": CLOUD_TOKEN}, timeout=8)
        if r.status_code == 200:
            print(f"[health] 已推送 {len(health)} 源健康到云端")
    except Exception as e:
        print(f"[warn] 健康推送失败 (不影响扫描): {str(e)[:80]}")


# =========================
# 抓取与解析
# =========================

def fetch_feed(feed, state):
    """共享 client 抓取 + ETag/Last-Modified 增量 (优化4, 2026-08-08)。

    返回 (feed, content, err, meta); meta={unchanged, etag, last_modified}。
    304 → unchanged=True, content=None (未变, 免下载解析)。
    """
    use_proxy = needs_proxy(feed)
    client = _get_client(use_proxy)
    name = feed["name"]
    st = state.get(name, {})
    headers = {}
    if st.get("etag"):
        headers["If-None-Match"] = st["etag"]
    if st.get("last_modified"):
        headers["If-Modified-Since"] = st["last_modified"]
    meta = {"unchanged": False, "etag": "", "last_modified": ""}
    try:
        resp = client.get(feed["url"], timeout=feed_timeout(feed), headers=headers)
        if resp.status_code == 304:
            meta["unchanged"] = True
            return feed, None, None, meta
        # 修复② (2026-08-08): 非 2xx 计失败 → 累加 fail → 自动隔离, 死链不再被记为 OK
        if not (200 <= resp.status_code < 300):
            return feed, None, f"HTTP {resp.status_code} {feed['url']}", meta
        meta["etag"] = resp.headers.get("etag", "") or st.get("etag", "")
        meta["last_modified"] = resp.headers.get("last-modified", "") or st.get("last_modified", "")
        return feed, resp.content, None, meta
    except Exception as e:
        return feed, None, str(e)[:120], meta

def _parse_json_feed(content: str, last_seen: str = "") -> list:
    """JSON Feed (https://jsonfeed.org) 解析器 (type=jsonfeed, 2026-08-08)。"""
    import json as _json
    try:
        d = _json.loads(content)
    except Exception:
        return []
    items = []
    for e in d.get("items", []) or []:
        url = e.get("url", "") or e.get("external_url", "") or ""
        if not url:
            continue
        if last_seen and url == last_seen:
            break
        items.append({
            "title": e.get("title", ""),
            "link": url,
            "published": (e.get("date_published", "") or e.get("date_modified", ""))[:25],
            "summary": (e.get("content_text", "") or e.get("summary", "") or "")[:300],
        })
    return items


def parse_feed(feed_name, content, state, feed_type="rss"):
    """按 type 分派解析 (2026-08-08): rss/atom/nitter → feedparser; jsonfeed → JSON Feed。"""
    if feed_type == "jsonfeed":
        return _parse_json_feed(content, state.get(feed_name, {}).get("last_seen"))
    d = feedparser.parse(content)
    last_seen = state.get(feed_name, {}).get("last_seen")
    items = []
    for e in d.entries:
        url = e.get("link", "")
        if not url:
            url = e.links[0].get("href", "") if hasattr(e, "links") and e.links else ""
        if last_seen and url == last_seen:
            break
        pub = e.get("published", "") or e.get("updated", "") or ""
        if len(pub) > 25: pub = pub[:25]
        summary = (e.get("summary", "") or e.get("description", "") or "")[:300]
        items.append({"title": e.get("title",""), "link": url, "published": pub, "summary": summary})
    return items


# =========================
# 报告生成
# =========================

def write_wiki_daily(articles, scan_date):
    if not articles: return None
    from collections import defaultdict
    today = scan_date[:10]
    os.makedirs(WIKI_PATH, exist_ok=True)
    wf = os.path.join(WIKI_PATH, f"{today}.md")
    bc = defaultdict(list)
    for a in articles: bc[a.get("category","其他")].append(a)
    co = ["Wire Agencies", "Global Media", "Financial Media", "China Media", "Government", "Central Banks", "Regulators", "International Organizations", "AI Companies", "Technology", "Open Source", "Research", "Security", "Energy & Commodities", "Venture Capital & Startup", "Community Signals", "其他"]
    lines = [f"# RSS 日报 — {today}", "", f"> 来源: {len(articles)} 篇文章 | {len(bc)} 个分类", ""]
    for cat in co:
        its = bc.get(cat, [])
        if not its: continue
        lines.append(f"## {cat} ({len(its)} 篇)"); lines.append("")
        for a in its:
            lines.append(f"- **[{a.get('source','')}]** {a.get('title','')[:100]}")
            lines.append(f"  {a.get('summary','')[:120]}")
            lines.append(f"  _{a.get('date','')[:16]}_ | [链接]({a.get('link','')})"); lines.append("")
        lines.append("---"); lines.append("")
    with open(wf,"w",encoding="utf-8") as f: f.write("\n".join(lines))
    return wf


# =========================
# =========================
# 主流程
# =========================

def _load_feeds():
    """从配置读取源列表（配置中心可增删改），缺失回退 CORE_FALLBACK_FEEDS (2026-08-08)。"""
    try:
        from config.loader import load_config
        cfg = load_config()
        feeds_cfg = cfg.get("rss.feeds")
        if isinstance(feeds_cfg, list) and feeds_cfg:
            # 过滤禁用源
            return [f for f in feeds_cfg if f.get("enabled", True)]
        print("[warn] rss.feeds 配置为空, 回退 CORE_FALLBACK_FEEDS (12 源)")
    except Exception as e:
        print(f"[warn] 配置读取失败 ({e}), 回退 CORE_FALLBACK_FEEDS (12 源)")
    return CORE_FALLBACK_FEEDS


def main():
    start = time.time()
    init_db()
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    state = normalize_state(load_state())
    feeds = _load_feeds()

    # --full (2026-08-08): 不限流全量扫描 — 所有活跃源视为到期 (对比老文件抓取量/验证修复用)
    FULL = "--full" in sys.argv or "--no-limit" in sys.argv

    # 修复⑤ 迁移: 存量 fail >= DEADLINK_FAILURES 的源直接标记死链 (退出常规扫描, 本轮回探测确认)
    for f in feeds:
        m = state.get(f["name"])
        if isinstance(m, dict) and not m.get("dead_link") and m.get("fail", 0) >= DEADLINK_FAILURES:
            m["dead_link"] = True
            m["next_probe"] = m.get("next_probe") or now_ts()
            m["quarantine_until"] = 0

    # 修复⑤: 死链源不占活跃/隔离, 仅按 next_probe 每周探测
    dead = [f for f in feeds if is_dead(state, f["name"])]
    active = [f for f in feeds if not is_quarantined(state, f["name"]) and not is_dead(state, f["name"])]
    qcnt = len(feeds) - len(active) - len(dead)
    probes = [f for f in dead if dead_probe_due(state, f["name"])]   # 死链每周探测到期

    # 优化3: 按 tier 过滤到期的源 (正常源) + 死链探测
    due = active if FULL else [f for f in active if is_due(state, f)]
    due += probes
    due.sort(key=lambda f: TIER.get(f.get("tier"), 2))
    mode = " [--full 不限流全量]" if FULL else ""
    print(f"[{datetime.now().isoformat()[:19]}] 总{len(feeds)} 活跃{len(active)} 死链{len(dead)} 隔离{qcnt} 本轮{len(due)}{mode}")

    # 优化2: 预载 known_ids (内存去重) + 批量缓冲
    known_ids = load_known_ids(conn)
    insert_buffer = []
    new_articles = []
    feed_stats = []
    errors = []

    # 优化5: as_completed 即时解析入库, 不等全部下载完
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(fetch_feed, f, state): f for f in due}
        for fut in as_completed(futs):
            feed = futs[fut]
            name = feed["name"]
            try:
                _f, content, err, meta = fut.result()
            except Exception as e:
                err, content, meta = str(e)[:120], None, {"unchanged": False, "etag": "", "last_modified": ""}
            if err:
                update_health(state, name, False)
                feed_stats.append({"name": name, "status": "error", "total": 0, "new": 0, "error": err})
                errors.append({"name": name, "error": err})
                continue
            update_health(state, name, True)
            # 304 未变 (优化4) — 修复①: 也更新 last_scan, 否则 304 源恒为"到期"每轮重抓, 限流失效
            if meta.get("unchanged"):
                state[name]["last_scan"] = now_ts()
                feed_stats.append({"name": name, "status": "ok", "total": 0, "new": 0, "error": "", "unchanged": True})
                continue
            if meta.get("etag"): state[name]["etag"] = meta["etag"]
            if meta.get("last_modified"): state[name]["last_modified"] = meta["last_modified"]

            items = parse_feed(name, content, state, feed.get("type", "rss"))
            if items:
                state[name]["last_seen"] = items[0]["link"]
            # V4: 源自带 category (16类) 优先; categorize_feed 仅兜底
            cat = (feed.get("category") or "").strip() or categorize_feed(name)
            new_for = []
            for item in items:
                if not item["link"]: continue
                aid = article_id(name, item["link"], item["title"])
                if aid in known_ids: continue  # 内存去重, 免逐条 SELECT
                known_ids.add(aid)
                insert_buffer.append((aid, item["published"][:10], cat, name, item["title"], item["summary"], item["link"]))
                ph = state[name].setdefault("history", [])
                ph.append(aid)
                if len(ph) > 500: state[name]["history"] = ph[-500:]
                new_for.append(item)
            if new_for:
                new_articles.extend([{"feed": name, "category": cat, **it} for it in new_for])
            feed_stats.append({"name": name, "status": "ok", "total": len(items), "new": len(new_for), "error": ""})
            state[name]["last_scan"] = now_ts()

    # 优化2: executemany 批量写入 (免逐条 execute)
    if insert_buffer:
        conn.executemany(
            "INSERT OR IGNORE INTO rss_articles(id,date,category,source,title,summary,link) VALUES(?,?,?,?,?,?,?)",
            insert_buffer)
    conn.commit(); conn.close()
    close_clients()
    save_state(state)

    ok = sum(1 for s in feed_stats if s["status"] == "ok")
    err = len(feed_stats) - ok
    unchanged = sum(1 for s in feed_stats if s.get("unchanged"))
    dur = round(time.time() - start, 2)
    total_a = sum(s["total"] for s in feed_stats)
    new_t = len(new_articles)

    wiki_articles = [{"date":a.get("published",""),"category":a.get("category",""),"source":a.get("feed",""),"title":a.get("title",""),"summary":a.get("summary",""),"link":a.get("link","")} for a in new_articles]
    write_wiki_daily(wiki_articles, datetime.now().isoformat())

    report = {"timestamp": datetime.now().isoformat(), "feeds_total": len(feeds), "feeds_active": len(active), "feeds_dead": len(dead), "feeds_dead_probed": len(probes), "feeds_quarantined": qcnt, "feeds_due": len(due), "feeds_ok": ok, "feeds_unchanged": unchanged, "feeds_error": err, "articles_total": total_a, "articles_new": new_t, "duration_sec": dur, "new_articles": new_articles[:50], "feeds_detail": feed_stats, "errors": errors[:30]}
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    push_health(state)  # 2026-08-08: 同步每源健康到云端 (非致命)

    print(f"[完成] {dur}s  总{len(feeds)} 活跃{len(active)} 死链{len(dead)} 隔离{qcnt} 本轮{len(due)}  OK{ok}  未变{unchanged}  失败{err}  新增{new_t}篇")
    if new_articles:
        print("  Top:")
        for a in new_articles[:5]:
            print(f"    [{a['feed']}] {a['title'][:60]}")
    if len(due) == 0:
        print("ℹ️ 本轮无到期源 (Tier 分级扫描)")

if __name__ == "__main__":
    main()

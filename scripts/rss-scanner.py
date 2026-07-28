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
# 配置
# =========================

PROXY = "socks5://127.0.0.1:10808"
MAX_WORKERS = 14
TIMEOUT = 10
HOT_TIMEOUT = 6
COLD_TIMEOUT = 15
USER_AGENT = "rss-scanner/3.2-final"

STATE_FILE = os.path.expanduser("~/.hermes/rss-scanner-state.json")
REPORT_FILE = os.path.expanduser("~/.hermes/rss-scanner-report.json")
DB_FILE = os.path.expanduser("~/.hermes/rss-archive.db")
WIKI_PATH = os.path.expanduser("~/wiki/RSS-Digest")

# =========================
# 98 源完整列表 (region: cn=直连, intl=SOCKS5)
# =========================

TIER = {"hot": 0, "warm": 1, "cold": 2}

FEEDS = [
    # ---- 通讯社 (7) ----
    {"name": "Reuters Top", "url": "https://feeds.reuters.com/reuters/topNews", "region": "intl", "tier": "hot"},
    {"name": "Reuters World", "url": "https://feeds.reuters.com/reuters/worldNews", "region": "intl", "tier": "warm"},
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "region": "intl", "tier": "warm"},
    {"name": "AP Top News", "url": "https://apnews.com/hub/ap-top-news?output=rss", "region": "intl", "tier": "hot"},
    {"name": "AP World", "url": "https://apnews.com/hub/world-news?output=rss", "region": "intl", "tier": "warm"},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "region": "intl", "tier": "warm"},

    # ---- 国家媒体 (17) ----
    {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml", "region": "intl", "tier": "hot"},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "region": "intl", "tier": "warm"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "region": "intl", "tier": "warm"},
    {"name": "CNN Edition", "url": "http://rss.cnn.com/rss/edition.rss", "region": "intl", "tier": "hot"},
    {"name": "CNN World", "url": "http://rss.cnn.com/rss/edition_world.rss", "region": "intl", "tier": "warm"},
    {"name": "NBC News", "url": "https://feeds.nbcnews.com/feeds/topstories", "region": "intl", "tier": "warm"},
    {"name": "CBS News", "url": "https://www.cbsnews.com/latest/rss/main", "region": "intl", "tier": "warm"},
    {"name": "ABC News", "url": "http://feeds.abcnews.com/abcnews/topstories", "region": "intl", "tier": "warm"},
    {"name": "NYT Home", "url": "http://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "region": "intl", "tier": "hot"},
    {"name": "NPR News", "url": "http://www.npr.org/rss/rss.php?id=1003", "region": "intl", "tier": "warm"},
    {"name": "Politico", "url": "http://www.politico.com/rss/politicopicks.xml", "region": "intl", "tier": "warm"},
    {"name": "The Hill", "url": "http://thehill.com/rss/syndicator/19110", "region": "intl", "tier": "warm"},
    {"name": "Newsweek", "url": "https://www.newsweek.com/rss", "region": "intl", "tier": "warm"},
    {"name": "Sky News", "url": "https://feeds.skynews.com/feeds/rss/world.xml", "region": "intl", "tier": "warm"},
    {"name": "France 24", "url": "https://www.france24.com/en/rss", "region": "intl", "tier": "warm"},
    {"name": "WaPo World", "url": "http://feeds.washingtonpost.com/rss/world", "region": "intl", "tier": "warm"},
    {"name": "WaPo Business", "url": "http://feeds.washingtonpost.com/rss/business", "region": "intl", "tier": "warm"},

    # ---- 金融媒体 (11) ----
    {"name": "FT World", "url": "https://www.ft.com/world?format=rss", "region": "intl", "tier": "warm"},
    {"name": "FT Markets", "url": "https://www.ft.com/markets?format=rss", "region": "intl", "tier": "warm"},
    {"name": "WSJ World", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "region": "intl", "tier": "warm"},
    {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "region": "intl", "tier": "warm"},
    {"name": "Economist", "url": "https://www.economist.com/feeds/print-sections/77/business.xml", "region": "intl", "tier": "cold"},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "region": "intl", "tier": "warm"},
    {"name": "MarketWatch", "url": "https://www.marketwatch.com/rss/topstories", "region": "intl", "tier": "warm"},
    {"name": "Barrons", "url": "https://www.barrons.com/feed", "region": "intl", "tier": "cold"},
    {"name": "Seeking Alpha", "url": "https://seekingalpha.com/feed.xml", "region": "intl", "tier": "cold"},
    {"name": "Investing.com", "url": "https://www.investing.com/rss/news.rss", "region": "intl", "tier": "cold"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "region": "intl", "tier": "warm"},

    # ---- 科技媒体 (12) ----
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "region": "intl", "tier": "hot"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "region": "intl", "tier": "warm"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "region": "intl", "tier": "warm"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "region": "intl", "tier": "warm"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "region": "intl", "tier": "warm"},
    {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "region": "intl", "tier": "warm"},
    {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "region": "intl", "tier": "warm"},
    {"name": "Space.com", "url": "https://www.space.com/feeds/all", "region": "intl", "tier": "cold"},
    {"name": "SpaceNews", "url": "https://spacenews.com/feed/", "region": "intl", "tier": "cold"},
    {"name": "Electrek", "url": "https://electrek.co/feed/", "region": "intl", "tier": "warm"},
    {"name": "CleanTechnica", "url": "https://cleantechnica.com/feed/", "region": "intl", "tier": "cold"},
    {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/feed", "region": "intl", "tier": "cold"},

    # ---- 地缘媒体 (5) ----
    {"name": "Guardian World", "url": "https://www.theguardian.com/world/rss", "region": "intl", "tier": "warm"},
    {"name": "DW News", "url": "https://rss.dw.com/rdf/rss-en-all", "region": "intl", "tier": "warm"},
    {"name": "Le Monde EN", "url": "https://www.lemonde.fr/en/rss_full.xml", "region": "intl", "tier": "warm"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "region": "intl", "tier": "warm"},
    {"name": "SCMP", "url": "https://www.scmp.com/rss/91/feed", "region": "intl", "tier": "warm"},

    # ---- 政府机构 (11) ----
    {"name": "White House", "url": "https://www.whitehouse.gov/briefing-room/feed/", "region": "intl", "tier": "hot"},
    {"name": "Fed Press", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "region": "intl", "tier": "hot"},
    {"name": "ECB Press", "url": "https://www.ecb.europa.eu/rss/press.html", "region": "intl", "tier": "warm"},
    {"name": "SEC Press", "url": "https://www.sec.gov/rss/news/press.xml", "region": "intl", "tier": "hot"},
    {"name": "UN News", "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "region": "intl", "tier": "warm"},
    {"name": "NASA News", "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss", "region": "intl", "tier": "cold"},
    {"name": "UK Gov", "url": "https://www.gov.uk/government/feed", "region": "intl", "tier": "cold"},
    {"name": "BoE", "url": "https://www.bankofengland.co.uk/rss", "region": "intl", "tier": "cold"},
    {"name": "IMF News", "url": "https://www.imf.org/en/News/RSS", "region": "intl", "tier": "cold"},
    {"name": "World Bank", "url": "https://www.worldbank.org/en/news/rss", "region": "intl", "tier": "cold"},
    {"name": "OECD News", "url": "https://www.oecd.org/newsroom/rss/", "region": "intl", "tier": "cold"},

    # ---- 科研/开源 (6) ----
    {"name": "arXiv AI", "url": "https://export.arxiv.org/rss/cs.AI", "region": "intl", "tier": "cold"},
    {"name": "arXiv ML", "url": "https://export.arxiv.org/rss/cs.LG", "region": "intl", "tier": "cold"},
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss/", "region": "intl", "tier": "warm"},
    {"name": "Google AI", "url": "https://blog.research.google/feed/", "region": "intl", "tier": "cold"},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/", "region": "intl", "tier": "cold"},

    # ---- 实时信号 (3) ----
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "region": "intl", "tier": "hot"},
    {"name": "Reddit WorldNews", "url": "https://www.reddit.com/r/worldnews/.rss", "region": "intl", "tier": "hot"},
    {"name": "Reddit Tech", "url": "https://www.reddit.com/r/technology/.rss", "region": "intl", "tier": "hot"},

    # ---- X/Nitter (18) ----
    {"name": "Nitter: Trump", "url": "https://nitter.freedit.eu/realDonaldTrump/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Biden", "url": "https://nitter.freedit.eu/POTUS/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Elon Musk", "url": "https://nitter.freedit.eu/elonmusk/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Bill Gates", "url": "https://nitter.freedit.eu/BillGates/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Fed Chair", "url": "https://nitter.freedit.eu/federalreserve/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: White House", "url": "https://nitter.freedit.eu/WhiteHouse/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: SECGov", "url": "https://nitter.freedit.eu/SECGov/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Reuters", "url": "https://nitter.freedit.eu/Reuters/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: BBC", "url": "https://nitter.freedit.eu/BBCBreaking/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: NASA", "url": "https://nitter.freedit.eu/NASA/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Kremlin", "url": "https://nitter.freedit.eu/KremlinRussia_E/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: UK PM", "url": "https://nitter.freedit.eu/10DowningStreet/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: EU", "url": "https://nitter.freedit.eu/EU_Commission/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: ECB", "url": "https://nitter.freedit.eu/ECB/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: IMF", "url": "https://nitter.freedit.eu/IMFNews/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: World Bank", "url": "https://nitter.freedit.eu/WorldBank/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Treasury", "url": "https://nitter.freedit.eu/USTreasury/rss", "region": "intl", "tier": "cold"},
    {"name": "Nitter: Kevin Warsh", "url": "https://nitter.freedit.eu/KevinWarsh/rss", "region": "intl", "tier": "cold"},

    # ---- 中文央媒 (6, cn=直连) ----
    {"name": "人民网 时政", "url": "http://www.people.com.cn/rss/politics.xml", "region": "cn", "tier": "warm"},
    {"name": "中国新闻网 时政", "url": "https://www.chinanews.com/rss/politics.xml", "region": "cn", "tier": "warm"},
    {"name": "中国日报 世界", "url": "http://www.chinadaily.com.cn/rss/world_rss.xml", "region": "cn", "tier": "warm"},
    {"name": "环球网 军事", "url": "https://www.huanqiu.com/rss/military.xml", "region": "cn", "tier": "cold"},
    {"name": "新华网 时政", "url": "http://www.xinhuanet.com/rss/politics.xml", "region": "cn", "tier": "warm"},
    {"name": "央视新闻", "url": "https://news.cctv.com/rss/", "region": "cn", "tier": "warm"},
]


def categorize_feed(name):
    if any(n in name for n in ["Reuters","AP ","Bloomberg","AFP"]): return "通讯社"
    elif any(n in name for n in ["BBC","CNN","NBC","CBS","ABC","NYT","NPR","Politico","The Hill","Newsweek","Sky News","France 24","WaPo"]): return "国家媒体"
    elif any(n in name for n in ["FT ","WSJ","Economist","CNBC","MarketWatch","Barrons","Seeking Alpha","Investing","Yahoo Finance"]): return "金融媒体"
    elif any(n in name for n in ["TechCrunch","The Verge","Wired","Ars Technica","MIT","Engadget","VentureBeat","Space","Electrek","CleanTechnica","IEEE"]): return "科技媒体"
    elif any(n in name for n in ["Guardian","DW","Le Monde","Al Jazeera","SCMP"]): return "地缘媒体"
    elif any(n in name for n in ["White House","Fed Press","ECB","SEC","UN News","NASA","UK Gov","BoE","IMF","World Bank","OECD"]): return "政府机构"
    elif any(n in name for n in ["arXiv","OpenAI","Google AI","GitHub"]): return "科研/开源"
    elif any(n in name for n in ["Hacker News","Reddit"]): return "实时信号"
    elif "Nitter:" in name: return "X/Nitter"
    elif any(n in name for n in ["人民网","中国新闻网","中国日报","环球网","新华网","央视"]): return "中文央媒"
    return "其他"


# =========================
# 数据库
# =========================

def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True) if os.path.dirname(DB_FILE) else None
    conn = sqlite3.connect(DB_FILE)
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
    return state.get(name, {}).get("quarantine_until", 0) > now_ts()

def update_health(state, name, ok):
    m = state.setdefault(name, {"history": [], "fail": 0, "quarantine_until": 0, "last_seen": ""})
    if isinstance(m, list):
        state[name] = {"history": m[-500:], "fail": 0, "quarantine_until": 0, "last_seen": ""}
        m = state[name]
    if ok: m["fail"] = 0
    else: m["fail"] = m.get("fail", 0) + 1
    if m["fail"] >= 3: m["quarantine_until"] = now_ts() + 1800
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

def create_client(feed):
    use_proxy = needs_proxy(feed)
    timeout = feed_timeout(feed)
    kwargs = {"timeout": timeout, "http2": True, "headers": {"User-Agent": USER_AGENT}}
    try:
        if use_proxy:
            return httpx.Client(proxy=PROXY, **kwargs)
        else:
            return httpx.Client(**kwargs)
    except TypeError:
        # httpx < 0.28 fallback
        if use_proxy:
            return httpx.Client(proxies=PROXY, **kwargs)
        else:
            return httpx.Client(**kwargs)


# =========================
# 抓取与解析
# =========================

def fetch_feed(feed):
    client = create_client(feed)
    try:
        resp = client.get(feed["url"])
        return feed, resp.content, None
    except Exception as e:
        return feed, None, str(e)[:120]
    finally:
        client.close()

def parse_feed(feed_name, content, state):
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
    co = ["通讯社","国家媒体","金融媒体","科技媒体","地缘媒体","政府机构","中文央媒","X/Nitter","实时信号","科研/开源","其他"]
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
# 主流程
# =========================

def main():
    start = time.time()
    init_db()
    conn = sqlite3.connect(DB_FILE)
    state = normalize_state(load_state())

    active = [f for f in FEEDS if not is_quarantined(state, f["name"])]
    qcnt = len(FEEDS) - len(active)
    active.sort(key=lambda f: TIER.get(f.get("tier"), 2))

    print(f"[{datetime.now().isoformat()[:19]}] 活跃: {len(active)}  隔离: {qcnt}")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f, c, err in [fut.result() for fut in as_completed({ex.submit(fetch_feed, f): f for f in active})]:
            results.append((f, c, err))

    new_articles = []
    feed_stats = []
    errors = []

    for feed, content, err in results:
        name = feed["name"]
        if err:
            update_health(state, name, False)
            feed_stats.append({"name": name, "status": "error", "total": 0, "new": 0, "error": err})
            errors.append({"name": name, "error": err})
            continue

        update_health(state, name, True)
        items = parse_feed(name, content, state)
        if items:
            state[name]["last_seen"] = items[0]["link"]

        cat = categorize_feed(name)
        new_for = []
        for item in items:
            if not item["link"]: continue
            aid = article_id(name, item["link"], item["title"])
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM rss_articles WHERE id=?", (aid,))
            if cur.fetchone(): continue
            conn.execute("INSERT OR IGNORE INTO rss_articles(id,date,category,source,title,summary,link) VALUES(?,?,?,?,?,?,?)",
                         (aid, item["published"][:10], cat, name, item["title"], item["summary"], item["link"]))
            ph = state[name].setdefault("history", [])
            ph.append(aid)
            if len(ph) > 500: state[name]["history"] = ph[-500:]
            new_for.append(item)

        if new_for:
            new_articles.extend([{"feed": name, "category": cat, **it} for it in new_for])
        feed_stats.append({"name": name, "status": "ok", "total": len(items), "new": len(new_for), "error": ""})

    conn.commit(); conn.close()
    save_state(state)

    ok = sum(1 for s in feed_stats if s["status"] == "ok")
    err = len(feed_stats) - ok
    dur = round(time.time() - start, 2)
    total_a = sum(s["total"] for s in feed_stats)
    new_t = len(new_articles)

    wiki_articles = [{"date":a.get("published",""),"category":a.get("category",""),"source":a.get("feed",""),"title":a.get("title",""),"summary":a.get("summary",""),"link":a.get("link","")} for a in new_articles]
    write_wiki_daily(wiki_articles, datetime.now().isoformat())

    report = {"timestamp": datetime.now().isoformat(), "feeds_total": len(FEEDS), "feeds_active": len(active), "feeds_quarantined": qcnt, "feeds_ok": ok, "feeds_error": err, "articles_total": total_a, "articles_new": new_t, "duration_sec": dur, "new_articles": new_articles[:50], "feeds_detail": feed_stats, "errors": errors[:30]}
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[完成] {dur}s  活跃{len(active)}  隔离{qcnt}  OK{ok}  失败{err}  新增{new_t}篇")
    if new_articles:
        print("  Top:")
        for a in new_articles[:5]:
            print(f"    [{a['feed']}] {a['title'][:60]}")
    if len(active) == 0:
        print("⚠️ 所有源被隔离, 检查代理或网络!")

if __name__ == "__main__":
    main()

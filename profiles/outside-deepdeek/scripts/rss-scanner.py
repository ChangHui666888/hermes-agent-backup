"""Hermes RSS Scanner — Python + SOCKS5 代理 + SQLite 归档 + Wiki 日报"""
import json, os, time, re, sqlite3
from datetime import datetime
from xml.etree import ElementTree
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ── 路径 ──
STATE_FILE = os.path.expanduser("~/.hermes/rss-scanner-state.json")
REPORT_FILE = os.path.expanduser("~/.hermes/rss-scanner-report.json")
DB_FILE = os.path.expanduser("~/.hermes/rss-archive.db")
WIKI_PATH = os.path.expanduser("~/wiki/RSS-Digest")
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 10808

# ── 98 个订阅源 ──
FEEDS = [
    # 通讯社 (7)
    ("Reuters Top", "https://feeds.reuters.com/reuters/topNews"),
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("AP Top News", "https://apnews.com/hub/ap-top-news?output=rss"),
    ("AP World", "https://apnews.com/hub/world-news?output=rss"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
    # 国家媒体 (17)
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("CNN Edition", "http://rss.cnn.com/rss/edition.rss"),
    ("CNN World", "http://rss.cnn.com/rss/edition_world.rss"),
    ("NBC News", "https://feeds.nbcnews.com/feeds/topstories"),
    ("CBS News", "https://www.cbsnews.com/latest/rss/main"),
    ("ABC News", "http://feeds.abcnews.com/abcnews/topstories"),
    ("NYT Home", "http://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("NPR News", "http://www.npr.org/rss/rss.php?id=1003"),
    ("Politico", "http://www.politico.com/rss/politicopicks.xml"),
    ("The Hill", "http://thehill.com/rss/syndicator/19110"),
    ("Newsweek", "https://www.newsweek.com/rss"),
    ("Sky News", "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("WaPo World", "http://feeds.washingtonpost.com/rss/world"),
    ("WaPo Business", "http://feeds.washingtonpost.com/rss/business"),
    # 金融 (11)
    ("FT World", "https://www.ft.com/world?format=rss"),
    ("FT Markets", "https://www.ft.com/markets?format=rss"),
    ("WSJ World", "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("Economist", "https://www.economist.com/feeds/print-sections/77/business.xml"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch", "https://www.marketwatch.com/rss/topstories"),
    ("Barrons", "https://www.barrons.com/feed"),
    ("Seeking Alpha", "https://seekingalpha.com/feed.xml"),
    ("Investing.com", "https://www.investing.com/rss/news.rss"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    # 科技 (12)
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("VentureBeat", "https://venturebeat.com/feed/"),
    ("Space.com", "https://www.space.com/feeds/all"),
    ("SpaceNews", "https://spacenews.com/feed/"),
    ("Electrek", "https://electrek.co/feed/"),
    ("CleanTechnica", "https://cleantechnica.com/feed/"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feed"),
    # 地缘 (5)
    ("Guardian World", "https://www.theguardian.com/world/rss"),
    ("DW News", "https://rss.dw.com/rdf/rss-en-all"),
    ("Le Monde EN", "https://www.lemonde.fr/en/rss_full.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("SCMP", "https://www.scmp.com/rss/91/feed"),
    # 政府机构 (11)
    ("White House", "https://www.whitehouse.gov/briefing-room/feed/"),
    ("Fed Press", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("ECB Press", "https://www.ecb.europa.eu/rss/press.html"),
    ("SEC Press", "https://www.sec.gov/rss/news/press.xml"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
    ("NASA News", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("UK Gov", "https://www.gov.uk/government/feed"),
    ("BoE", "https://www.bankofengland.co.uk/rss"),
    ("IMF News", "https://www.imf.org/en/News/RSS"),
    ("World Bank", "https://www.worldbank.org/en/news/rss"),
    ("OECD News", "https://www.oecd.org/newsroom/rss/"),
    # 科研 (5)
    ("arXiv AI", "https://export.arxiv.org/rss/cs.AI"),
    ("arXiv ML", "https://export.arxiv.org/rss/cs.LG"),
    ("OpenAI Blog", "https://openai.com/blog/rss/"),
    ("Google AI", "https://blog.research.google/feed/"),
    ("GitHub Blog", "https://github.blog/feed/"),
    # 实时 (3)
    ("Hacker News", "https://news.ycombinator.com/rss"),
    ("Reddit WorldNews", "https://www.reddit.com/r/worldnews/.rss"),
    ("Reddit Tech", "https://www.reddit.com/r/technology/.rss"),
    # X/Nitter (18) — 通过 SOCKS5
    ("Nitter: Trump", "https://nitter.freedit.eu/realDonaldTrump/rss"),
    ("Nitter: Elon Musk", "https://nitter.freedit.eu/elonmusk/rss"),
    ("Nitter: Bill Gates", "https://nitter.freedit.eu/BillGates/rss"),
    ("Nitter: Kremlin", "https://nitter.freedit.eu/KremlinRussia_E/rss"),
    ("Nitter: Fed Chair", "https://nitter.freedit.eu/federalreserve/rss"),
    ("Nitter: White House", "https://nitter.freedit.eu/WhiteHouse/rss"),
    ("Nitter: SEC", "https://nitter.freedit.eu/SECGov/rss"),
    ("Nitter: Kevin Warsh", "https://nitter.freedit.eu/KevinWarsh/rss"),
    # 中文央媒 (6) — 国内直连
    ("人民网 时政", "http://www.people.com.cn/rss/politics.xml"),
    ("中国新闻网 时政", "https://www.chinanews.com/rss/politics.xml"),
    ("中国日报 世界", "http://www.chinadaily.com.cn/rss/world_rss.xml"),
    ("环球网 军事", "https://www.huanqiu.com/rss/military.xml"),
    ("新华网 时政", "http://www.xinhuanet.com/rss/politics.xml"),
    ("央视新闻", "https://news.cctv.com/rss/"),
]

# ── 国内域名白名单（直连，不走代理）──
DOMESTIC_DOMAINS = [
    "stats.gov.cn", "people.com.cn", "xinhuanet.com", "cctv.com",
    "chinadaily.com.cn", "chinanews.com", "huanqiu.com", "ce.cn",
    "gov.cn", "pbc.gov.cn", "eastmoney.com",
    "36kr.com", "huxiu.com", "cls.cn", "xueqiu.com",
]

def needs_proxy(url):
    from urllib.parse import urlparse
    domain = urlparse(url).hostname or ""
    for d in DOMESTIC_DOMAINS:
        if domain.endswith(d):
            return False
    return True

def fetch_feed(name, url):
    import urllib.request
    try:
        if needs_proxy(url):
            import socks, socket
            socks.set_default_proxy(socks.SOCKS5, PROXY_HOST, PROXY_PORT)
            socket.socket = socks.socksocket
            resp = urllib.request.urlopen(url, timeout=10)
            socket.socket = socket._socket
        else:
            resp = urllib.request.urlopen(url, timeout=10)
        raw = resp.read()
    except Exception as e:
        return {"name": name, "status": "error", "error": str(e)[:80], "articles": []}

    articles = []
    try:
        root = ElementTree.fromstring(raw)
        for item in root.iter("item"):
            t = item.findtext("title", "")
            l = item.findtext("link", "")
            d = item.findtext("pubDate", "") or item.findtext("dc:date", "")
            s = item.findtext("description", "")[:300]
            if t:
                articles.append({"title": unescape(t), "url": l, "date": d[:25], "snippet": unescape(s)[:200]})
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            t = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
            le = entry.find("{http://www.w3.org/2005/Atom}link")
            l = le.attrib.get("href", "") if le is not None else ""
            d = entry.findtext("{http://www.w3.org/2005/Atom}published", "") or entry.findtext("{http://www.w3.org/2005/Atom}updated", "")
            s = entry.findtext("{http://www.w3.org/2005/Atom}summary", "")[:300]
            if t:
                articles.append({"title": unescape(t), "url": l, "date": d[:25], "snippet": unescape(s)[:200]})
    except:
        return {"name": name, "status": "parse_error", "articles": []}
    return {"name": name, "status": "ok", "articles": articles}

def categorize(name):
    if any(n in name for n in ["Reuters","AP ","Bloomberg","AFP"]): return "通讯社"
    if any(n in name for n in ["BBC","CNN","NBC","CBS","ABC","NYT","NPR","Politico","The Hill","Newsweek","Sky News","France 24","WaPo"]): return "国家媒体"
    if any(n in name for n in ["FT ","WSJ","Economist","CNBC","MarketWatch","Barrons","Seeking Alpha","Investing","Yahoo Finance"]): return "金融媒体"
    if any(n in name for n in ["TechCrunch","The Verge","Wired","Ars Technica","MIT","Engadget","VentureBeat","Space","Electrek","CleanTechnica","IEEE"]): return "科技媒体"
    if any(n in name for n in ["Guardian","DW","Le Monde","Al Jazeera","SCMP"]): return "地缘媒体"
    if any(n in name for n in ["White House","Fed Press","ECB","SEC","UN News","NASA","UK Gov","BoE","IMF","World Bank","OECD"]): return "政府机构"
    if any(n in name for n in ["arXiv","OpenAI","Google AI","GitHub"]): return "科研/开源"
    if any(n in name for n in ["Hacker News","Reddit"]): return "实时信号"
    if "Nitter:" in name: return "X/Nitter"
    if any(n in name for n in ["人民网","中国新闻网","中国日报","环球网","新华网","央视"]): return "中文央媒"
    return "其他"

def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""CREATE TABLE IF NOT EXISTS rss_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, category TEXT,
        source TEXT NOT NULL, title TEXT, summary TEXT, link TEXT UNIQUE,
        created_at TEXT DEFAULT (datetime('now','localtime')))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON rss_articles(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON rss_articles(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON rss_articles(category)")
    conn.commit()
    return conn

def save_to_sqlite(conn, articles):
    n = 0
    for a in articles:
        try:
            conn.execute("INSERT OR IGNORE INTO rss_articles (date,category,source,title,summary,link) VALUES (?,?,?,?,?,?)",
                (a.get("date","")[:10], a.get("category",""), a.get("source",""), a.get("title",""), a.get("summary","")[:300], a.get("link","")))
            n += 1
        except: pass
    conn.commit()
    return n

def write_wiki(articles, scan_date):
    today = scan_date[:10]
    os.makedirs(WIKI_PATH, exist_ok=True)
    by_cat = defaultdict(list)
    for a in articles:
        by_cat[a.get("category","其他")].append(a)
    cat_order = ["通讯社","国家媒体","金融媒体","科技媒体","地缘媒体","政府机构","中文央媒","X/Nitter","实时信号","科研/开源","其他"]
    lines = [f"# RSS 日报 — {today}", "", f"> 来源: {len(articles)} 篇文章 | {len(by_cat)} 个分类", ""]
    for cat in cat_order:
        items = by_cat.get(cat, [])
        if not items: continue
        lines.append(f"## {cat} ({len(items)} 篇)\n")
        for a in items:
            lines.append(f"- **[{a.get('source','')}]** {a.get('title','')[:100]}")
            lines.append(f"  {a.get('summary','')[:120]}")
            lines.append(f"  _{a.get('date','')[:16]}_ | [链接]({a.get('link','')})")
            lines.append("")
        lines.append("---\n")
    with open(os.path.join(WIKI_PATH, f"{today}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f: state = json.load(f)
    now = datetime.now().isoformat()

    feed_results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs = {ex.submit(fetch_feed, n, u): n for n, u in FEEDS}
        for f in as_completed(fs):
            n = fs[f]
            try: feed_results[n] = f.result(15)
            except: feed_results[n] = {"name": n, "status": "timeout", "articles": []}

    new_articles = []
    feed_stats = []
    for name, _ in FEEDS:
        r = feed_results.get(name, {"name": name, "status": "not_run", "articles": []})
        prev = set(state.get(name, []))
        fresh = []
        for a in r["articles"]:
            aid = f"{name}::{a['url']}"
            if aid not in prev:
                fresh.append(a)
                state.setdefault(name, []).append(aid)
        new_articles.extend([{"feed": name, "category": categorize(name), **a} for a in fresh])
        feed_stats.append({"name": name, "status": r.get("status",""), "total": len(r["articles"]), "new": len(fresh)})

    for k in state: state[k] = state[k][-500:]
    with open(STATE_FILE, "w") as f: json.dump(state, f)

    ok = sum(1 for s in feed_stats if s["status"] == "ok")
    err = sum(1 for s in feed_stats if s["status"] != "ok")
    new_total = len(new_articles)

    # SQLite
    conn = init_db()
    db_ok = save_to_sqlite(conn, [{
        "date": a.get("date",""), "category": a.get("category",""),
        "source": a.get("feed",""), "title": a.get("title",""),
        "summary": a.get("snippet",""), "link": a.get("url","")
    } for a in new_articles])
    conn.close()

    # Wiki
    write_wiki([{
        "date": a.get("date",""), "category": a.get("category",""),
        "source": a.get("feed",""), "title": a.get("title",""),
        "summary": a.get("snippet",""), "link": a.get("url","")
    } for a in new_articles], now)

    report = {
        "timestamp": now, "feeds_total": len(FEEDS), "feeds_ok": ok, "feeds_error": err,
        "articles_total": sum(s["total"] for s in feed_stats), "articles_new": new_total,
        "db_inserted": db_ok, "new_articles": new_articles[:50], "feeds_detail": feed_stats
    }
    with open(REPORT_FILE, "w") as f: json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[{now[:19]}] Feeds: {ok}/{len(FEEDS)} OK, {err} errors")
    print(f"  Articles: {report['articles_total']} found, {new_total} new")
    print(f"  DB: {db_ok} inserted")
    for a in new_articles[:5]:
        print(f"    [{a.get('feed','')}] {a.get('title','')[:70]}")

if __name__ == "__main__":
    main()

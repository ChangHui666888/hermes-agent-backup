"""Hermes RSS Scanner — Python + SOCKS5 代理
读取 blogwatcher 数据库中的所有订阅源，通过 SOCKS5 代理获取 RSS 更新。
由 Hermes cron job 定期调度。
"""
import json, os, time, re
from datetime import datetime
from xml.etree import ElementTree
from html import unescape

# SOCKS5 proxy
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 10808

# Output
STATE_FILE = os.path.expanduser("~/.hermes/rss-scanner-state.json")
REPORT_FILE = os.path.expanduser("~/.hermes/rss-scanner-report.json")

# All feeds (74 international + 18 Nitter + 6 domestic = 98 feeds)
FEEDS = [
    # ═══════════════════════════════════════════════════
    # 通讯社 (7)
    # ═══════════════════════════════════════════════════
    ("Reuters Top", "https://feeds.reuters.com/reuters/topNews"),
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("AP Top News", "https://apnews.com/hub/ap-top-news?output=rss"),
    ("AP World", "https://apnews.com/hub/world-news?output=rss"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),

    # ═══════════════════════════════════════════════════
    # 国家媒体 (17)
    # ═══════════════════════════════════════════════════
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

    # ═══════════════════════════════════════════════════
    # 金融媒体 (11)
    # ═══════════════════════════════════════════════════
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

    # ═══════════════════════════════════════════════════
    # 科技媒体 (12)
    # ═══════════════════════════════════════════════════
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

    # ═══════════════════════════════════════════════════
    # 地缘媒体 (5)
    # ═══════════════════════════════════════════════════
    ("Guardian World", "https://www.theguardian.com/world/rss"),
    ("DW News", "https://rss.dw.com/rdf/rss-en-all"),
    ("Le Monde EN", "https://www.lemonde.fr/en/rss_full.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("SCMP", "https://www.scmp.com/rss/91/feed"),

    # ═══════════════════════════════════════════════════
    # 政府机构 (11)
    # ═══════════════════════════════════════════════════
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

    # ═══════════════════════════════════════════════════
    # 科研/开源 (6)
    # ═══════════════════════════════════════════════════
    ("arXiv AI", "https://export.arxiv.org/rss/cs.AI"),
    ("arXiv ML", "https://export.arxiv.org/rss/cs.LG"),
    ("OpenAI Blog", "https://openai.com/blog/rss/"),
    ("Google AI", "https://blog.research.google/feed/"),
    ("GitHub Blog", "https://github.blog/feed/"),

    # ═══════════════════════════════════════════════════
    # 实时信号 (3)
    # ═══════════════════════════════════════════════════
    ("Hacker News", "https://news.ycombinator.com/rss"),
    ("Reddit WorldNews", "https://www.reddit.com/r/worldnews/.rss"),
    ("Reddit Tech", "https://www.reddit.com/r/technology/.rss"),

    # ═══════════════════════════════════════════════════
    # X/Nitter — 关键人物实时监控 (18)
    # 通过 Nitter 匿名 RSS，无需 X 账号，走 SOCKS5 代理
    # ═══════════════════════════════════════════════════
    ("Nitter: Trump @realDonaldTrump", "https://nitter.freedit.eu/realDonaldTrump/rss"),
    ("Nitter: Pres. Biden @POTUS", "https://nitter.freedit.eu/POTUS/rss"),
    ("Nitter: Elon Musk @elonmusk", "https://nitter.freedit.eu/elonmusk/rss"),
    ("Nitter: Bill Gates @BillGates", "https://nitter.freedit.eu/BillGates/rss"),
    ("Nitter: Fed Chair @federalreserve", "https://nitter.freedit.eu/federalreserve/rss"),
    ("Nitter: White House @WhiteHouse", "https://nitter.freedit.eu/WhiteHouse/rss"),
    ("Nitter: SECGov @SECGov", "https://nitter.freedit.eu/SECGov/rss"),
    ("Nitter: Reuters @Reuters", "https://nitter.freedit.eu/Reuters/rss"),
    ("Nitter: BBC Breaking @BBCBreaking", "https://nitter.freedit.eu/BBCBreaking/rss"),
    ("Nitter: NASA @NASA", "https://nitter.freedit.eu/NASA/rss"),
    ("Nitter: Kremlin @KremlinRussia_E", "https://nitter.freedit.eu/KremlinRussia_E/rss"),
    ("Nitter: UK PM @10DowningStreet", "https://nitter.freedit.eu/10DowningStreet/rss"),
    ("Nitter: EU Commission @EU_Commission", "https://nitter.freedit.eu/EU_Commission/rss"),
    ("Nitter: ECB @ECB", "https://nitter.freedit.eu/ECB/rss"),
    ("Nitter: IMF @IMFNews", "https://nitter.freedit.eu/IMFNews/rss"),
    ("Nitter: World Bank @WorldBank", "https://nitter.freedit.eu/WorldBank/rss"),
    ("Nitter: Treasury @USTreasury", "https://nitter.freedit.eu/USTreasury/rss"),
    ("Nitter: Kevin Warsh @KevinWarsh", "https://nitter.freedit.eu/KevinWarsh/rss"),

    # ═══════════════════════════════════════════════════
    # 中文央媒 — 国内直连 (6) （新增）
    # ═══════════════════════════════════════════════════
    ("人民网 时政", "http://www.people.com.cn/rss/politics.xml"),
    ("中国新闻网 时政", "https://www.chinanews.com/rss/politics.xml"),
    ("中国日报 世界", "http://www.chinadaily.com.cn/rss/world_rss.xml"),
    ("环球网 军事", "https://www.huanqiu.com/rss/military.xml"),
    ("新华网 时政", "http://www.xinhuanet.com/rss/politics.xml"),
    ("央视新闻", "https://news.cctv.com/rss/"),
]


def setup_proxy():
    """Don't set global proxy — per-feed routing instead"""
    pass


DOMESTIC_DOMAINS = [
    "stats.gov.cn", "people.com.cn", "xinhuanet.com", "cctv.com",
    "chinadaily.com.cn", "chinanews.com", "huanqiu.com", "ce.cn",
    "gov.cn", "pbc.gov.cn", "eastmoney.com", "10jqka.com.cn",
    "36kr.com", "huxiu.com", "sspai.com", "ifanr.com",
    "cls.cn", "gelonghui.com", "xueqiu.com",
]


def needs_proxy(url):
    """Check if a URL needs SOCKS5 proxy (blocked international) or direct (domestic)"""
    from urllib.parse import urlparse
    domain = urlparse(url).hostname or ""
    for d in DOMESTIC_DOMAINS:
        if domain.endswith(d):
            return False
    return True


def create_urlopener(url):
    """Create URL opener: direct or via SOCKS5 proxy depending on domain"""
    import urllib.request
    if needs_proxy(url):
        import socks
        import socket
        proxy_handler = urllib.request.ProxyHandler({})
        # Use SOCKS5 via socket patch for this request only
        orig_socket = socket.socket
        socks.set_default_proxy(socks.SOCKS5, PROXY_HOST, PROXY_PORT)
        socket.socket = socks.socksocket
        try:
            opener = urllib.request.build_opener(proxy_handler)
            return opener
        finally:
            socket.socket = orig_socket
    else:
        return urllib.request.build_opener()


def fetch_feed(name, url):
    """Fetch and parse an RSS feed, return list of articles"""
    import urllib.request
    try:
        if needs_proxy(url):
            import socks
            import socket
            socks.set_default_proxy(socks.SOCKS5, PROXY_HOST, PROXY_PORT)
            socket.socket = socks.socksocket
            resp = urllib.request.urlopen(url, timeout=10)
            socket.socket = socket._socket  # restore
        else:
            resp = urllib.request.urlopen(url, timeout=10)
        raw = resp.read()
    except Exception as e:
        return {"name": name, "status": "error", "error": str(e)[:80], "articles": []}
    
    articles = []
    try:
        root = ElementTree.fromstring(raw)
        # Handle RSS 2.0
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pubdate = item.findtext("pubDate", "") or item.findtext("dc:date", "")
            desc = item.findtext("description", "")[:300]
            if title:
                articles.append({"title": unescape(title), "url": link, "date": pubdate[:25], "snippet": unescape(desc)[:200]})
        # Handle Atom
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.attrib.get("href", "") if link_el is not None else ""
            date = entry.findtext("{http://www.w3.org/2005/Atom}published", "") or entry.findtext("{http://www.w3.org/2005/Atom}updated", "")
            summary = entry.findtext("{http://www.w3.org/2005/Atom}summary", "")[:300]
            if title:
                articles.append({"title": unescape(title), "url": link, "date": date[:25], "snippet": unescape(summary)[:200]})
    except Exception as e:
        return {"name": name, "status": "parse_error", "error": str(e)[:80], "articles": []}
    
    return {"name": name, "status": "ok", "articles": articles}


def main():
    # Setup SOCKS5 proxy
    setup_proxy()
    
    # Load previous state (article IDs we've already seen)
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    
    now = datetime.now().isoformat()
    
    # Fetch all feeds concurrently (8 workers)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    feed_results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_feed, name, url): name for name, url in FEEDS}
        for future in as_completed(futures):
            name = futures[future]
            try:
                feed_results[name] = future.result(timeout=15)
            except Exception as e:
                feed_results[name] = {"name": name, "status": "error", "error": str(e)[:80], "articles": []}
    
    new_articles = []
    feed_stats = []
    
    for name, _ in FEEDS:
        result = feed_results.get(name, {"name": name, "status": "not_run", "articles": []})
        prev_ids = set(state.get(name, []))
        
        new_for_feed = []
        for art in result["articles"]:
            art_id = f"{name}::{art['url']}"
            if art_id not in prev_ids:
                new_for_feed.append(art)
                # Track ID for dedup
                if name not in state:
                    state[name] = []
                state[name].append(art_id)
        
        if new_for_feed:
            new_articles.extend([{"feed": name, **a} for a in new_for_feed])
        
        feed_stats.append({
            "name": name,
            "status": result.get("status", "unknown"),
            "total": len(result["articles"]),
            "new": len(new_for_feed)
        })
    
    # Trim state (keep last 500 IDs per feed)
    for feed_name in state:
        state[feed_name] = state[feed_name][-500:]
    
    # Save state
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    
    # Generate report
    ok = sum(1 for s in feed_stats if s["status"] == "ok")
    err = sum(1 for s in feed_stats if s["status"] != "ok")
    total_arts = sum(s["total"] for s in feed_stats)
    new_total = len(new_articles)
    
    report = {
        "timestamp": now,
        "feeds_total": len(FEEDS),
        "feeds_ok": ok,
        "feeds_error": err,
        "articles_total": total_arts,
        "articles_new": new_total,
        "new_articles": new_articles[:50],  # Top 50 new
        "feeds_detail": feed_stats,
        "errors": [s for s in feed_stats if s["status"] != "ok"]
    }
    
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # Console summary
    print(f"[{now[:19]}] RSS Scanner Report")
    print(f"  Feeds: {ok}/{len(FEEDS)} OK, {err} errors")
    print(f"  Articles: {total_arts} found, {new_total} new")
    if new_articles:
        print(f"\n  Top new articles:")
        for art in new_articles[:10]:
            print(f"    [{art['feed']}] {art['title'][:70]}")
            print(f"      {art['url'][:80]}")


if __name__ == "__main__":
    main()

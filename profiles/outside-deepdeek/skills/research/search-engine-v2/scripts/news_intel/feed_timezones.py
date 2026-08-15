"""RSS 源 → 国家/地区 → IANA 时区 映射 (2026-08-14)。

用途: 当源日期**无时区标识** (naive) 时, 按源的国家/地区推断本地时区, 再转 UTC。
来源: scanner state 199 个 feed 名称 + CORE_FALLBACK 域名; 时区按各机构总部所在地。
⚠ 若 feed 名称含 'Nitter:'/'BBC中文' 等, 用主域名对应源。找不到的回落 None (保持 naive)。
"""

# feed 名称(或名称子串) → IANA 时区
FEED_TZ: dict[str, str] = {
    # ── 美国 (多数新闻机构在美东, 科技在美西) ──
    "NYT": "America/New_York", "Reuters": "America/New_York", "AP ": "America/New_York",
    "CNN": "America/New_York", "WaPo": "America/New_York", "Bloomberg": "America/New_York",
    "Politico": "America/New_York", "The Hill": "America/New_York", "ABC News": "America/New_York",
    "CBS News": "America/New_York", "NBC News": "America/New_York", "NPR": "America/New_York",
    "Newsweek": "America/New_York", "TIME": "America/New_York", "Axios": "America/New_York",
    "Fox News": "America/New_York", "WSJ": "America/New_York", "The Atlantic": "America/New_York",
    "Vox": "America/New_York", "ZeroHedge": "America/New_York", "CoinDesk": "America/New_York",
    "Cointelegraph": "America/New_York", "CNBC": "America/New_York", "Business Insider": "America/New_York",
    "Quartz": "America/New_York", "US News": "America/New_York", "Ars Technica": "America/New_York",
    "SEC": "America/New_York", "Fed ": "America/New_York", "FINRA": "America/New_York",
    "CFTC": "America/New_York", "Treasury": "America/New_York", "White House": "America/New_York",
    "CISA": "America/New_York", "NVD": "America/New_York", "Krebs": "America/New_York",
    "BleepingComputer": "America/New_York", "DarkReading": "America/New_York", "The Hacker News": "America/New_York",
    "S&P": "America/New_York", "EIA": "America/New_York", "TradingEconomics": "America/New_York",
    "Hacker News": "America/Los_Angeles", "TechCrunch": "America/Los_Angeles", "Y Combinator": "America/Los_Angeles",
    "a16z": "America/Los_Angeles", "Sequoia": "America/Los_Angeles", "Greylock": "America/Los_Angeles",
    "Accel": "America/Los_Angeles", "General Catalyst": "America/New_York", "Product Hunt": "America/Los_Angeles",
    "NVIDIA": "America/Los_Angeles", "Anthropic": "America/Los_Angeles", "OpenAI": "America/Los_Angeles",
    "Stability": "Europe/London", "HuggingFace": "America/New_York", "Meta AI": "America/Los_Angeles",
    "Microsoft": "America/Los_Angeles", "AWS": "America/Los_Angeles", "Google Blog": "America/Los_Angeles",
    "Apple Newsroom": "America/Los_Angeles", "Netflix Tech": "America/Los_Angeles", "Uber Eng": "America/Los_Angeles",
    "Stripe": "America/Los_Angeles", "GitLab": "America/Los_Angeles", "Docker": "America/Los_Angeles",
    "Cloudflare": "America/Los_Angeles", "CNCF": "America/Los_Angeles", "Kubernetes": "America/Los_Angeles",
    "Stack Overflow": "America/New_York", "Zacks": "America/Chicago", "Morningstar": "America/Chicago",
    "arXiv": "America/New_York", "PNAS": "America/New_York", "Science": "America/New_York",
    "NeurIPS": "America/Los_Angeles", "CVPR": "America/Los_Angeles", "ICML": "America/Los_Angeles",
    "Kitco": "America/Toronto",
    # ── 英国/爱尔兰 (Europe/London) ──
    "BBC": "Europe/London", "FT": "Europe/London", "Guardian": "Europe/London",
    "Independent": "Europe/London", "Sky News": "Europe/London", "Irish Times": "Europe/Dublin",
    "FCA UK": "Europe/London", "Nature": "Europe/London", "DeepMind": "Europe/London",
    "Lobsters": "Europe/London",
    # ── 欧洲大陆 ──
    "France 24": "Europe/Paris", "RFI": "Europe/Paris", "AFP": "Europe/Paris",
    "DW": "Europe/Berlin", "ESMA": "Europe/Paris", "ECB": "Europe/Berlin", "EU": "Europe/Brussels",
    "OPEC": "Europe/Vienna", "IEA": "Europe/Paris", "Mistral": "Europe/Paris",
    # ── 中国 (Asia/Shanghai) ──
    "人民网": "Asia/Shanghai", "新华网": "Asia/Shanghai", "环球网": "Asia/Shanghai",
    "界面": "Asia/Shanghai", "财新": "Asia/Shanghai", "第一财经": "Asia/Shanghai",
    "财联社": "Asia/Shanghai", "36Kr": "Asia/Shanghai", "澎湃": "Asia/Shanghai",
    "中国证券报": "Asia/Shanghai", "证券时报": "Asia/Shanghai", "上海证券报": "Asia/Shanghai",
    "经济观察报": "Asia/Shanghai", "People's Bank of China": "Asia/Shanghai", "央行": "Asia/Shanghai",
    # ── 俄罗斯 (Europe/Moscow) ──
    "TASS": "Europe/Moscow", "Interfax": "Europe/Moscow",
    # ── 日本 (Asia/Tokyo) ──
    "Kyodo": "Asia/Tokyo", "Japan Times": "Asia/Tokyo", "Bank of Japan": "Asia/Tokyo",
    # ── 印度 (Asia/Kolkata) ──
    "RBI": "Asia/Kolkata",
    # ── 新加坡 (Asia/Singapore) ──
    "MAS SG": "Asia/Singapore",
    # ── 加拿大 (America/Toronto) ──
    "Canadian Press": "America/Toronto", "Bank of Canada": "America/Toronto",
    # ── 澳大利亚 (Australia/Sydney) ──
    "RBA": "Australia/Sydney",
    # ── 土耳其 (Europe/Istanbul) ──
    "Anadolu": "Europe/Istanbul",
    # ── 国际组织 (总部) ──
    "IMF": "America/New_York", "World Bank": "America/New_York",
    # ── 开源/技术社区 (分散, 用主贡献方时区) ──
    "Rust": "America/New_York", "Python Insider": "America/New_York", "NodeJS": "America/New_York",
    "LLVM": "America/Los_Angeles", "Apache": "Europe/Vienna", "Linux Foundation": "America/Los_Angeles",
    "Dev.to": "America/New_York", "CoinDesk": "America/New_York",
    # ── 大宗/能源 ──
    "OilPrice": "Europe/London", "FXStreet": "Europe/Madrid",
    "Nitter: Bill Gates": "America/Los_Angeles", "Nitter: NASA": "America/New_York",
    "Nitter: UK PM": "Europe/London", "Nitter: Kremlin": "Europe/Moscow",
    "Nitter: Kevin Warsh": "America/New_York",
    # ── 补缺 (2026-08-14 全量) ──
    "中国新闻网": "Asia/Shanghai", "中国日报": "Asia/Shanghai", "央视新闻": "Asia/Shanghai",
    "Al Jazeera": "Asia/Qatar", "SCMP": "Asia/Hong_Kong",
    "UN News": "America/New_York", "OECD News": "Europe/Paris",
    "Le Monde": "Europe/Paris", "Economist": "Europe/London",
    "Seeking Alpha": "America/New_York", "Investing.com": "Asia/Jerusalem",
    "Space.com": "America/New_York", "IEEE Spectrum": "America/New_York",
    "CleanTechnica": "America/New_York", "NASA News": "America/New_York", "SpaceNews": "America/New_York",
    "UK Gov": "Europe/London", "BoE": "Europe/London", "Barrons": "America/New_York",
    "Nitter: Biden": "America/New_York", "Nitter: Trump": "America/New_York",
    "Google AI": "America/Los_Angeles", "GitHub Blog": "America/Los_Angeles",
    "Nitter: Elon Musk": "America/Los_Angeles", "Slashdot": "America/Los_Angeles",
    "Cohere": "America/Toronto", "Perplexity": "America/Los_Angeles", "xAI": "America/Los_Angeles",
    "The Diplomat": "America/New_York", "Foreign Policy": "America/New_York",
    "Reddit": "America/New_York", "MarketWatch": "America/New_York", "The Verge": "America/New_York",
    "Wired": "America/Los_Angeles", "Yahoo Finance": "America/Los_Angeles",
    "Engadget": "America/New_York", "VentureBeat": "America/Los_Angeles",
    "MIT Tech Review": "America/New_York", "Electrek": "America/New_York",
}


def get_feed_tz(feed_name: str) -> str | None:
    """按 feed 名称返回 IANA 时区; 找不到回落 None。"""
    if not feed_name:
        return None
    if feed_name in FEED_TZ:
        return FEED_TZ[feed_name]
    # 子串匹配 (如 'Reuters Top' → 'Reuters')
    for key, tz in FEED_TZ.items():
        if key in feed_name:
            return tz
    return None

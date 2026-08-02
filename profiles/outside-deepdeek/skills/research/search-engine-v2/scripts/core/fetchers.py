"""
core/fetchers.py — Real network implementations for every cascade strategy.
All fetchers respect a RateLimiter for per-domain throttling.
"""

from __future__ import annotations
import re
import time
import json
import logging
import random
from typing import Optional
from urllib.parse import urlparse
from dataclasses import dataclass, field

import httpx
import os

logger = logging.getLogger(__name__)

# ── Content extraction backends ────────────────────────────────────
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

try:
    from readability import Document as ReadabilityDoc
    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False

# ── Playwright (only) ─────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("Playwright not installed; browser strategy disabled")

# ── Browser Pool (单例，避免每次 launch/close 开销) ────────────
import threading as _threading

class BrowserPool:
    """进程级单例 Playwright 浏览器池。
    
    一个 Chromium 实例可连续抓取数千个页面。
    崩溃后自动重启。
    """
    _instance = None
    _lock = _threading.Lock()
    _launch_count = 0  # 类级别统计
    _crash_count = 0

    def __init__(self):
        self._playwright = None
        self._browser = None

    @classmethod
    def get_browser(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls.__new__(cls)
                    cls._instance._playwright = None
                    cls._instance._browser = None
                    cls._instance._ensure_browser()
        else:
            cls._instance._ensure_browser()
        return cls._instance._browser

    def _ensure_browser(self):
        try:
            if self._browser and self._browser.is_connected():
                return
        except Exception:
            self.__class__._crash_count += 1
            logger.warning(f"[browser_pool] browser crashed (total crashes={self.__class__._crash_count}), re-launching")
        # Launch fresh
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                '--disable-setuid-sandbox', '--disable-web-security',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
                '--disable-ipc-flooding-protection', '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows', '--disable-background-timer-throttling',
                '--disable-client-side-phishing-detection', '--disable-popup-blocking',
                '--disable-prompt-on-repost', '--disable-hang-monitor', '--disable-sync',
                '--disable-default-apps', '--disable-extensions', '--disable-plugins',
            ])
        self.__class__._launch_count += 1

    @classmethod
    def close_all(cls):
        if cls._instance and cls._instance._browser:
            try:
                cls._instance._browser.close()
            except Exception:
                pass
        if cls._instance and cls._instance._playwright:
            try:
                cls._instance._playwright.stop()
            except Exception:
                pass
        cls._instance = None
        cls._launch_count = 0
        cls._crash_count = 0

    @property
    def stats(self):
        return {"launches": self._launch_count, "crashes": self._crash_count}

import atexit
atexit.register(BrowserPool.close_all)

# ── Rate Limiter ──────────────────────────────────────────────────
@dataclass
class RateLimiter:
    default_delay: float = 1.0
    domain_delays: dict = field(default_factory=dict)
    _last_request: dict = field(default_factory=dict)
    _lock: object = field(default_factory=__import__("threading").Lock)

    def set_domain_delay(self, domain: str, delay: float):
        self.domain_delays[domain] = delay

    def wait(self, domain: str):
        delay = self.domain_delays.get(domain, self.default_delay)
        with self._lock:
            last = self._last_request.get(domain, 0)
            now = time.monotonic()
            remaining = delay - (now - last)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request[domain] = time.monotonic()

    def wait_for(self, key: str, delay: float):
        with self._lock:
            last = self._last_request.get(key, 0)
            now = time.monotonic()
            remaining = delay - (now - last)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request[key] = time.monotonic()


# ── Client Pool for direct ──────────────────────────────────────
class DirectClientPool:
    def __init__(self, max_domains: int = 50):
        self._clients: dict[str, httpx.Client] = {}
        self._access: dict[str, float] = {}
        self._max = max_domains
        self._lock = __import__("threading").Lock()

    def get(self, url: str) -> httpx.Client:
        domain = urlparse(url).netloc
        with self._lock:
            if domain not in self._clients:
                if len(self._clients) >= self._max:
                    self._evict_lru()
                self._clients[domain] = _make_client(url=url)
            self._access[domain] = time.monotonic()
            return self._clients[domain]

    def _extract_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _evict_lru(self):
        if not self._access:
            return
        oldest = min(self._access, key=self._access.get)
        try:
            self._clients[oldest].close()
        except Exception:
            pass
        del self._clients[oldest]
        del self._access[oldest]

    def close_all(self):
        with self._lock:
            for c in self._clients.values():
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
            self._access.clear()

    def __len__(self) -> int:
        return len(self._clients)

_direct_client_pool = DirectClientPool(max_domains=50)


# ── Scrapling Pool ──────────────────────────────────────────────
class ScraplingPool:
    def __init__(self):
        self._fetcher: object | None = None
        self._init_error: str | None = None
        self._lock = __import__("threading").Lock()

    def get(self):
        if self._init_error:
            return None
        if self._fetcher is not None:
            return self._fetcher
        with self._lock:
            if self._fetcher is not None:
                return self._fetcher
            if self._init_error:
                return None
            try:
                from scrapling import StealthyFetcher
                self._fetcher = StealthyFetcher()
                logger.info("[scrapling] StealthyFetcher singleton initialized")
            except ImportError as e:
                self._init_error = str(e)
                return None
            except Exception as e:
                self._init_error = str(e)
                logger.warning(f"[scrapling] init failed: {e}")
                return None
        return self._fetcher

_scrapling_pool = ScraplingPool()


# ── Extraction helper ────────────────────────────────────────────
def _extract_main_text(html: str, url: str = "") -> str:
    if not html or len(html.strip()) < 50:
        return ""

    if HAS_TRAFILATURA:
        text = trafilatura.extract(
            html,
            include_links=False,
            include_images=False,
            include_tables=False,
            output_format="markdown",
            url=url,
        )
        if text and len(text.strip()) > 100:
            return text.strip()

    if HAS_READABILITY:
        try:
            doc = ReadabilityDoc(html)
            title = doc.title() or ""
            content = doc.summary(html_partial=True)
            content = re.sub(r"<[^>]+>", "", content)
            content = re.sub(r"\n{3,}", "\n\n", content)
            text = f"# {title}\n\n{content}" if title else content
            if text.strip():
                return text.strip()
        except Exception:
            pass

    text = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── HTTP session factory ─────────────────────────────────────────
_CHINESE_TLDS = {".cn", ".com.cn", ".org.cn", ".gov.cn", ".edu.cn", ".net.cn"}
_CHINESE_DOMAINS = {
    "people.com.cn", "xinhuanet.com", "cctv.com", "cctv.cn",
    "chinanews.com", "chinadaily.com.cn", "huanqiu.com",
    "yicai.com", "thepaper.cn", "caixin.com", "jiemian.com",
    "sina.com.cn", "sohu.com", "163.com", "qq.com",
    "china.com.cn", "gmw.cn", "youth.cn", "ce.cn",
}

def _is_chinese_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if any(host.endswith(tld) for tld in _CHINESE_TLDS):
        return True
    if any(host == d or host.endswith("." + d) for d in _CHINESE_DOMAINS):
        return True
    return False

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_RETRIES = 3

def _make_client(url: str | None = None, timeout: httpx.Timeout | None = None) -> httpx.Client:
    import os
    if timeout is None:
        timeout = httpx.Timeout(connect=5, read=15, write=10, pool=5)
    kwargs = {
        "headers": DEFAULT_HEADERS,
        "follow_redirects": True,
        "timeout": timeout,
        "http2": False,  # httpx 0.28 on Windows + proxy has intermittent SSL handshake hangs
    }
    if url and not _is_chinese_domain(url):
        proxy = (os.environ.get("SOCKS5_PROXY") or "socks5://127.0.0.1:10808")
        if proxy:
            kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


# ═══════════════════════════════════════════════════════════════════
# Strategy Implementations
# ═══════════════════════════════════════════════════════════════════

def fetch_direct(url: str, rate_limiter: RateLimiter | None = None, timeout: float | None = None) -> str | None:
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    client = _direct_client_pool.get(url)
    try:
        for attempt in range(MAX_RETRIES):
            try:
                resp = client.get(url, timeout=timeout)
                if resp.status_code in RETRY_STATUS:
                    wait = 2 ** attempt
                    logger.info(f"[direct] {resp.status_code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                html = resp.text
                text = _extract_main_text(html, url=url)
                if text:
                    return text
                return _extract_main_text(html) or html[:5000]
            except httpx.HTTPStatusError as e:
                if e.response.status_code in RETRY_STATUS and attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                logger.warning(f"[direct] HTTP {e.response.status_code} for {url}")
                return None
        return None
    except Exception as e:
        logger.warning(f"[direct] {type(e).__name__}: {e}")
        return None

def fetch_archive(url: str, rate_limiter: RateLimiter | None = None) -> str | None:
    archive_url = f"https://web.archive.org/web/0/{url}"
    domain = "web.archive.org"
    if rate_limiter:
        rate_limiter.wait(domain)
    try:
        with _make_client(url=url) as client:
            resp = client.get(archive_url)
            resp.raise_for_status()
            html = resp.text
        if "Wayback Machine doesn't have that page" in html or "not been archived" in html:
            logger.info(f"[archive] Not archived: {url}")
            return None
        text = _extract_main_text(html, url=url)
        if text:
            return f"[Archived from web.archive.org]\n\n{text}"
        return None
    except Exception as e:
        logger.warning(f"[archive] {type(e).__name__}: {e}")
        return None

def fetch_google_cache(url: str, rate_limiter: RateLimiter | None = None) -> str | None:
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    domain = "webcache.googleusercontent.com"
    if rate_limiter:
        rate_limiter.wait(domain)
    try:
        with _make_client(url=url) as client:
            resp = client.get(cache_url)
            resp.raise_for_status()
            html = resp.text
        if "Page not available" in html or "404 Not Found" in html[:500]:
            logger.info(f"[google_cache] Not cached: {url}")
            return None
        text = _extract_main_text(html, url=url)
        if text:
            return f"[Google Cache]\n\n{text}"
        return None
    except Exception as e:
        logger.warning(f"[google_cache] {type(e).__name__}: {e}")
        return None

def fetch_scrapling(url: str, rate_limiter: RateLimiter | None = None, timeout: float = 45.0) -> str | None:
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    try:
        fetcher = _scrapling_pool.get()
        if fetcher is None:
            return None
        resp = fetcher.fetch(url, timeout=int(timeout * 1000))
        if resp is None:
            return None
        html = getattr(resp, "text", None) or getattr(resp, "content", None)
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        if not html:
            return None
        text = _extract_main_text(html, url=url)
        return text or None
    except Exception as e:
        logger.warning(f"[scrapling] {type(e).__name__}: {e}")
        return None

def fetch_browser(url: str, rate_limiter: RateLimiter | None = None, timeout: float = 30.0) -> str | None:
    """
    Playwright browser with BrowserPool singleton (avoids 3-5s launch per call).
    """
    if not HAS_PLAYWRIGHT:
        logger.warning("[browser] Playwright not installed")
        return None

    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
        rate_limiter.wait_for(f"browser:{domain}", delay=5.0)

    try:
        browser = BrowserPool.get_browser()
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            device_scale_factor=1,
            has_touch=False, is_mobile=False,
            java_script_enabled=True,
        )
        page = context.new_page()

        # Anti-detection: 优先 playwright-stealth (完整指纹伪装)
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception:
            # 降级: 手动基础反检测脚本
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(p) {
                    if (p === 37445) return 'Intel Inc.';
                    if (p === 37446) return 'Intel Iris OpenGL Engine';
                    return getParameter(p);
                };
                window.chrome = { runtime: {} };
            """)

        try:
            page.goto(url, wait_until="commit", timeout=int(timeout * 1000))
        except PlaywrightTimeoutError:
            logger.warning(f"[browser] commit timeout for {url}, retrying with domcontentloaded")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            except Exception:
                return None

        # Wait for content container — 逗号多 selector 单次等待
        # (避免串行 9×8s=72s 最坏等待; 任一 selector 匹配即返回)
        content_selector = ", ".join([
            "article", "[role='main']", ".article-body", ".post-content",
            "div.article", ".content", ".news-content", ".article-content",
            "main", ".story-body", ".story-content"
        ])
        found = False
        try:
            page.wait_for_selector(content_selector, timeout=8000)
            found = True
        except Exception:
            pass

        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        page.wait_for_timeout(1500 + random.randint(0, 1000))
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(800 + random.randint(0, 500))

        if not found:
            page.wait_for_timeout(3000)

        # 增强: 滚动加载 + 捕获视频转写 (时间戳内容)
        try:
            for _ in range(3):
                page.mouse.wheel(0, 800)
                page.wait_for_timeout(1200)
            page.wait_for_timeout(1500)
        except Exception:
            pass

        html = page.content()
        text = _extract_main_text(html, url=url)

        # 若正文过短或含时间戳, 用页面全文补充 (视频转写场景)
        try:
            body_text = page.inner_text("body")
            if not text or len(text.strip()) < 500:
                text = body_text.strip()
            elif _has_timestamps(body_text) and not _has_timestamps(text):
                # 正文无时间戳但页面含转写 → 优先转写
                text = body_text.strip()
        except Exception:
            pass
        context.close()

        if text and len(text.strip()) > 200:
            if "robot" in text.lower() or "please click" in text.lower():
                logger.warning(f"[browser] Verification page detected for {url}")
                return None
            return text
        return None
    except Exception as e:
        logger.warning(f"[browser] {type(e).__name__}: {e}")
        return None


def _has_timestamps(text: str) -> bool:
    """检测是否含视频时间戳 (如 0:00 / 1:23)"""
    import re
    return bool(re.search(r"\b\d+:\d{2}\b", text or ""))


def _get_crawl_config() -> dict:
    """读取配置中心 crawl.* 参数（VPS 挂了回退默认）。"""
    try:
        from config.loader import load_config
        return load_config()
    except Exception:
        return {}


def is_video_url(url: str, patterns: list[str] | None = None) -> bool:
    """判断视频页面 URL。pattern 来自配置 crawl.video_patterns（默认 /video/ /videos/）。"""
    if patterns is None:
        patterns = _get_crawl_config().get("crawl.video_patterns", ["/video/", "/videos/"])
    u = (url or "").lower()
    return any(p in u for p in patterns)


# 广告/追踪 URL 特征（jina 整页抓取时混入的噪音）
_TRACKING_URL_RE = re.compile(
    r"(ad\.gt|publisher_dmp|impr_match|amo_match|sync\.\w+\.?|scorecardresearch|"
    r"doubleclick|googlesyndication|googletagmanager|taboola|outbrain)",
    re.I,
)
_JUNK_LINES = {"## ACUMEN", "Cookie Policy", "Your Privacy Choices"}
# 导航/相关视频段落标题 (出现即视为噪音区开始; 注意避开转写内误报如 "## More"/"## Explore")
_NAV_SECTION_MARKERS = (
    "## Live Now", "## Around The Web", "## Top Videos", "## Recommended",
    "## Trending", "## Featured", "## About", "## Watch",
)


def _clean_video_content(text: str, max_len: int = 30000) -> str:
    """清洗视频抓取内容：转写在页面前部，去追踪/广告/相关视频卡片/导航噪音。

    策略:
      1. 行级: 去追踪 URL 行、已知组件行
      2. `[![Image` (相关视频卡片, 如 CBS 整页列表) → 直接断
      3. 段落级: 遇导航/相关标题 (## Live Now / ## About 等) → 截断
      4. 移除内嵌图片引用 ![..](..)
      5. 截断上限兜底
    """
    if not text:
        return text
    cleaned = []
    for line in text.split("\n"):
        s = line.strip()
        if "[![Image" in line:  # 相关视频卡片列表开始 → 后续全是噪音
            break
        if s in _JUNK_LINES:
            continue
        if _TRACKING_URL_RE.search(s):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    # 段落级导航标题截断
    for mark in _NAV_SECTION_MARKERS:
        i = text.find(mark)
        if i > 0:
            text = text[:i]
    # 移除内嵌图片引用
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    if len(text) > max_len:
        text = text[:max_len]
    return text.strip()

def fetch_search_snippet(url: str, search_func=None) -> str | None:
    """
    搜索摘要兜底。优先使用 Hermes search_func，无则用 SearXNG 自搜索。
    """
    if search_func is not None:
        try:
            results = search_func(url)
            if results:
                top = results[0]
                return f"# {top.get('title', '')}\n\n{top.get('snippet', '')}\n\n[Hermes 搜索摘要兜底]"
        except Exception as e:
            logger.warning(f"[search_snippet] hermes search failed: {e}")

    # 无 Hermes 时用 SearXNG 自搜索
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        SEARXNG_BASE = os.environ.get("SEARXNG_BASE") or "http://100.107.117.23:8080"
        with httpx.Client(timeout=10.0) as client:
            # 用域名提取搜索词
            path = urlparse(url).path
            segments = [s.replace('-', ' ') for s in path.split('/') if s and len(s) > 4]
            query = ' '.join(segments[:3]) if segments else domain
            resp = client.get(f"{SEARXNG_BASE}/search", params={"q": query, "format": "json", "pageno": 1},
                              headers={"User-Agent": "NewsIntelBot/1.0"})
        data = resp.json()
        for r in data.get("results", [])[:3]:
            if domain in r.get("url", "") and r.get("content", ""):
                return f"# {r.get('title', '')}\n\n{r.get('content', '')[:500]}\n\n[SearXNG 搜索摘要兜底]"
        # 未匹配到同域名，取第一条通用结果
        if data.get("results"):
            r = data["results"][0]
            return f"# {r.get('title', '')}\n\n{r.get('content', '')[:500]}\n\n[SearXNG 搜索摘要兜底]"
        return None
    except Exception as e:
        logger.warning(f"[search_snippet] searxng fallback failed: {e}")
        return None


# ── Jina Reader (轻量第三方 API 兜底) ──────────────────────────
# 免费 API: curl https://r.jina.ai/URL → markdown
# 专为 LLM 提取设计，自带 Cloudflare/反爬绕过能力
JINA_READER_BASE = os.environ.get("JINA_READER_BASE") or "https://r.jina.ai"

def fetch_jina_reader(url: str, rate_limiter: RateLimiter | None = None, timeout: float = 15.0) -> str | None:
    """
    Jina Reader — 轻量第三方 API，自带 Cloudflare/反爬绕过能力。
    从 curl 迁移到 httpx，提高 Windows 可靠性和错误处理。
    """
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    reader_url = f"{JINA_READER_BASE}/{url}"
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=10, read=timeout, write=10, pool=5)) as client:
            resp = client.get(
                reader_url,
                headers={"Accept": "text/plain, text/markdown, */*",
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                follow_redirects=True,
            )
        if resp.status_code >= 400:
            logger.info(f"[jina] HTTP {resp.status_code} for {url}")
            return None
        text = resp.text.strip()
        if len(text) < 100:
            return None
        return text
    except httpx.ConnectError as e:
        logger.warning(f"[jina] connect failed: {type(e).__name__} (Jina Reader may be blocked on this network)")
        return None
    except Exception as e:
        logger.warning(f"[jina] {type(e).__name__}: {e}")
        return None


# ── SearXNG 替代源恢复 (搜同一事件的其它报道源再抓取) ──────────
# 从 .env 读取，不硬编码 IP
try:
    from config.env import SEARXNG_BASE as _SEARXNG_DEFAULT
except Exception:
    _SEARXNG_DEFAULT = "http://100.107.117.23:8080"
SEARXNG_BASE = os.environ.get("SEARXNG_BASE") or _SEARXNG_DEFAULT

def _content_matches_title(title: str, text: str) -> bool:
    """校验替代源内容是否与标题相关（防抓错内容）。

    提取标题中的关键词（>2字符英文词，过滤停用词），
    检查正文是否包含至少 1 个关键词。
    中英混合标题：也检查中文子串。
    """
    if not title or not text:
        return True  # 无标题时不做校验（保持兼容）
    text_l = text.lower()
    t_l = title.lower()
    _STOP = {"the", "and", "for", "with", "that", "this", "has", "had", "have", "from", "said",
             "says", "was", "were", "are", "its", "his", "her", "not", "but", "into", "over"}
    words = [w for w in re.findall(r"[a-zA-Z]{3,}", t_l) if w not in _STOP]
    # 中文关键词
    cn_chars = [c for c in title if '一' <= c <= '鿿']
    if not words and not cn_chars:
        return True
    # 英文关键词至少命中 1 个
    if words:
        hits = sum(1 for w in words if w in text_l)
        if hits >= 1:
            return True
        # 标题核心词(最长2个)必须命中
        core = sorted(set(words), key=len, reverse=True)[:2]
        if any(c in text_l for c in core):
            return True
        return False
    # 中文：标题任意3字子串出现在正文
    for i in range(len(cn_chars) - 2):
        if "".join(cn_chars[i:i+3]) in text:
            return True
    return False


def fetch_searxng_alt(url: str, rate_limiter: RateLimiter | None = None,
                       timeout: float = 10.0, title: str | None = None) -> str | None:
    """当原始 URL 抓取失败时，用 SearXNG 搜索同一标题/事件的替代报道源，
    取前 2 个非原 URL 的结果直接请求并抽取正文。找到的内容必须与标题相关
    （防抓错内容），否则拒绝。找不到替代源或替代源本身抓取失败时返回 None。
    """
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    q = (title or url)[:80]
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{SEARXNG_BASE}/search", params={"q": q, "format": "json"},
                               headers={"User-Agent": "NewsIntelBot/1.0"})
        data = resp.json()
    except Exception as e:
        logger.warning(f"[searxng_alt] search failed: {type(e).__name__}: {e}")
        return None

    for alt in data.get("results", [])[:2]:
        alt_url = alt.get("url", "")
        if not alt_url or alt_url == url:
            continue
        try:
            with _make_client(url=alt_url) as client:
                r2 = client.get(alt_url)
            if r2.status_code == 200 and len(r2.text) > 500:
                text = _extract_main_text(r2.text, url=alt_url)
                if text and len(text) > 200:
                    # 关键校验：内容必须与标题相关，否则拒绝（防抓错内容）
                    if not _content_matches_title(title or "", text):
                        logger.warning(f"[searxng_alt] 内容与标题不相关, 拒绝: {alt_url}")
                        continue
                    return f"[SearXNG alt-source: {alt_url}]\n\n{text}"
        except Exception as e:
            logger.info(f"[searxng_alt] fetch {alt_url} failed: {type(e).__name__}: {e}")
            continue
    return None


# ── Tavily (AI 摘要 API, 自带搜索+反爬绕过) ────────────────────
TAVILY_DEV_KEY = "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"

def fetch_tavily(url: str, rate_limiter: RateLimiter | None = None, timeout: float = 10.0,
                  title: str | None = None) -> str | None:
    """Tavily search API via curl (httpx has SSL/SNI issues on this network).

    Prefers the article title for the search query when available — it's a much
    stronger signal than URL path segments (falls back to URL-derived query otherwise).
    """
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    if title and title.strip():
        query = title.strip()[:100]
    else:
        from urllib.parse import urlparse as _up
        path = _up(url).path
        segments = [s.replace('-', ' ') for s in path.split('/') if s and len(s) > 6]
        query = ' '.join(segments[:4]) if segments else url[:100]
    import json, subprocess
    payload = json.dumps({
        "api_key": TAVILY_DEV_KEY, "query": query,
        "search_depth": "basic", "max_results": 2, "include_answer": True,
    })
    try:
        result = subprocess.run(
            ["curl", "-4", "-s", "--max-time", str(int(timeout)),
             "https://api.tavily.com/search",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout + 2)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        answer = data.get("answer", "")
        if answer and len(answer) > 100:
            return f"[Tavily summary]\n\n{answer}"
        return None
    except Exception as e:
        logger.warning(f"[tavily] {type(e).__name__}: {e}")
        return None


# ── LLM Structured Extraction ──────────────────────────────────
def llm_extract_structured(content: str, prompt: str, api_key: str | None = None,
                           api_base: str = "https://api.deepseek.com/v1", model: str = "deepseek-chat",
                           max_chars: int = 8000) -> dict | list | None:
    import os
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("[llm_extract] No API key")
        return None
    truncated = content[:max_chars]
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": "只输出JSON。"},
                                 {"role": "user", "content": f"{prompt}\n\n{truncated}"}],
                    "temperature": 0.0,
                    "max_tokens": 2000,
                }
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if json_match:
                raw = json_match.group(1).strip()
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"[llm_extract] {e}")
        return None


# ── Batch convenience ────────────────────────────────────────────
def extract_single(
    url: str,
    rate_limiter: RateLimiter | None = None,
    force_strategy_order: list[str] | None = None,
    skip_expensive: bool = True,
    min_content_len: int | None = None,
    search_func=None,
    llm_api_key: str | None = None,
    llm_prompt: str | None = None,
    title: str | None = None,
    cascade_timeout: float | None = None,
    video_allow: bool = False,
) -> dict:
    from config.domain_profiles import get_profile
    from core.temporal import validate_temporal

    # 接线配置中心 crawl.* 参数（缺失回退默认）
    _cfg = _get_crawl_config()
    min_content_len = min_content_len if min_content_len is not None else _cfg.get("crawl.min_content_len", 200)
    cascade_timeout = cascade_timeout if cascade_timeout is not None else _cfg.get("crawl.cascade_timeout", 60)
    browser_timeout = float(_cfg.get("crawl.browser_timeout", 30))
    direct_timeout = float(_cfg.get("crawl.direct_timeout", 20))

    # 视频 URL 分流: video_allow=True 时走视频专用链路(browser+stealth)；
    # 否则保持旧行为硬跳过。图片/YouTube/播放器页永远不抓。
    ALWAYS_SKIP = ["/watch?", "youtube.com", "/photos/", "/gallery/"]
    video = is_video_url(url, _cfg.get("crawl.video_patterns"))
    if video and not video_allow:
        return {
            "ok": False, "url": url, "domain": "",
            "error": "视频页面，跳过抓取 (需 --video 模式)",
            "cost_trace": [],
            "strategies_tried": [],
        }
    for pat in ALWAYS_SKIP:
        if pat in url.lower():
            return {
                "ok": False, "url": url, "domain": "",
                "error": f"图片/播放器页面，跳过抓取 (matched: {pat})",
                "cost_trace": [],
                "strategies_tried": [],
            }

    profile = get_profile(url)
    if video and video_allow:
        # 视频专用链路：不套域名 failing，browser 优先抓转写
        order = force_strategy_order or list(_cfg.get("crawl.video_strategy", ["browser", "archive", "jina", "tavily"]))
        failing = set()
    else:
        order = force_strategy_order or list(profile.strategy_order)
        failing = set(profile.known_failing)
        if skip_expensive:
            failing.add("computer_use")
            # 仅在 Playwright 未安装时跳过 browser（可节省 ~60s）
            if not HAS_PLAYWRIGHT:
                failing.add("browser")
    order = [s for s in order if s not in failing]

    cost_trace = []
    STRATEGY_FN = {
        "direct": lambda u: fetch_direct(u, rate_limiter, timeout=direct_timeout),
        "archive": lambda u: fetch_archive(u, rate_limiter),
        "google_cache": lambda u: fetch_google_cache(u, rate_limiter),
        "scrapling": lambda u: fetch_scrapling(u, rate_limiter),
        "browser": lambda u: fetch_browser(u, rate_limiter, timeout=browser_timeout),
        "jina": lambda u: fetch_jina_reader(u, rate_limiter),
        "tavily": lambda u: fetch_tavily(u, rate_limiter, title=title),
        "searxng_alt": lambda u: fetch_searxng_alt(u, rate_limiter, title=title),
        "computer_use": lambda u: None,
        "search_snippet": lambda u: fetch_search_snippet(u, search_func),
    }
    COST = {"direct": 1, "archive": 1, "google_cache": 1, "search_snippet": 1,
            "scrapling": 2, "jina": 2, "tavily": 3, "searxng_alt": 2, "browser": 3, "computer_use": 5}

    content = None
    strategy_used = None
    deadline = time.monotonic() + cascade_timeout

    for strategy in order:
        # 级联总超时（软截止）：不中断正在执行的单个策略，
        # 仅在策略间检查。实际总耗时可能比 cascade_timeout
        # 多出一个最长策略的自身超时（当前最大约 30s）。
        if time.monotonic() >= deadline:
            attempt = {"strategy": strategy, "cost": COST.get(strategy, 0), "url": url,
                       "ok": False, "error": "cascade_timeout"}
            cost_trace.append(attempt)
            logger.info(f"[cascade] timeout after {cascade_timeout:.0f}s on {strategy}, "
                        f"tried {len(cost_trace)-1} strategies, "
                        f"got partial={len(content or ''):d}c")
            break
        fn = STRATEGY_FN.get(strategy)
        if fn is None:
            continue
        attempt = {"strategy": strategy, "cost": COST.get(strategy, 0), "url": url}
        try:
            result = fn(url)
        except Exception as e:
            attempt["ok"] = False
            attempt["error"] = str(e)
            cost_trace.append(attempt)
            continue

        if not result or len(result.strip()) < min_content_len:
            attempt["ok"] = False
            attempt["error"] = "内容为空/过短" if result else "返回 None"
            cost_trace.append(attempt)
            continue

        attempt["ok"] = True
        attempt["content_len"] = len(result)
        cost_trace.append(attempt)
        content = result
        strategy_used = strategy
        break

    if not content:
        return {
            "ok": False, "url": url, "domain": profile.domain,
            "error": "所有策略均失败", "cost_trace": cost_trace,
            "strategies_tried": [t["strategy"] for t in cost_trace],
        }

    # 视频内容清洗: 转写都在页面前部, 去追踪/广告噪音 + 截断 (jina 整页抓取可达 20 万字)
    if video:
        content = _clean_video_content(content, max_len=_cfg.get("crawl.video_max_content", 30000))

    # Structured extraction
    structured = None
    from core.extractor import extract_structured
    if llm_api_key and llm_prompt:
        structured = llm_extract_structured(content, llm_prompt, api_key=llm_api_key)
    else:
        structured = extract_structured(url, content)

    headline = (structured or {}).get("headline", "") if isinstance(structured, dict) else ""
    published_at = (structured or {}).get("published_at") if isinstance(structured, dict) else None
    temporal = validate_temporal(url=url, title=headline, published_at=published_at, content_snippet=content[:500])
    total_cost = sum(t.get("cost", 0) for t in cost_trace if t.get("ok"))

    return {
        "ok": True,
        "url": url,
        "domain": profile.domain,
        "content": content,
        "strategy_used": strategy_used,
        "total_cost": total_cost,
        "cost_trace": cost_trace,
        "structured": structured,
        "temporal_check": temporal,
    }
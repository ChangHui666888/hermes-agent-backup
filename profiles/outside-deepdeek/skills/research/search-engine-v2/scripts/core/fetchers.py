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

def fetch_direct(url: str, rate_limiter: RateLimiter | None = None) -> str | None:
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    client = _direct_client_pool.get(url)
    try:
        for attempt in range(MAX_RETRIES):
            try:
                resp = client.get(url)
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
    Playwright browser with anti-detection and resource-blocking optimization.
    - Blocks images/fonts/CSS/trackers for 3-5x speedup + lower detection surface
    - Uses wait_until='commit' then waits for content selectors
    - Reduces timeout from 60s→30s to fail fast on detected bots
    """
    if not HAS_PLAYWRIGHT:
        logger.warning("[browser] Playwright not installed")
        return None

    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
        rate_limiter.wait_for(f"browser:{domain}", delay=5.0)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=BlockInsecurePrivateNetworkRequests',
                    '--disable-ipc-flooding-protection',
                    '--disable-renderer-backgrounding',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-background-timer-throttling',
                    '--disable-client-side-phishing-detection',
                    '--disable-popup-blocking',
                    '--disable-prompt-on-repost',
                    '--disable-hang-monitor',
                    '--disable-sync',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--disable-plugins',
                ]
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                device_scale_factor=1,
                has_touch=False,
                is_mobile=False,
                java_script_enabled=True,
            )
            page = context.new_page()

            # Block heavy resources: images, fonts, css, media, trackers
            BLOCK_PATTERNS = [r'\.(png|jpg|jpeg|gif|svg|ico|webp|woff2?|ttf|eot|mp4|mp3)(\?|$)',
                              r'(google-analytics|gtag|fbcdn|doubleclick|amazon-adsystem)']
            async def _block_route(route):
                url_lower = route.request.url.lower()
                for pat in BLOCK_PATTERNS:
                    import re
                    if re.search(pat, url_lower):
                        await route.abort()
                        return
                rtype = route.request.resource_type
                if rtype in ('image', 'font', 'media', 'stylesheet', 'other'):
                    await route.abort()
                else:
                    await route.continue_()

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                page.route("**/*", lambda route: asyncio.run_coroutine_threadsafe(_block_route(route), loop))
            except RuntimeError:
                pass  # no running loop, skip interception

            # Anti-detection script
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                // WebGL vendor/renderer spoofing
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

            # Wait for content container
            content_selectors = [
                "article", "[role='main']", ".article-body", ".post-content",
                "div.article", ".content", ".news-content", ".article-content",
                "main", ".story-body", ".story-content"
            ]
            found = False
            for selector in content_selectors:
                try:
                    page.wait_for_selector(selector, timeout=8000)
                    found = True
                    break
                except:
                    continue

            # Brief human-like scroll
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
            page.wait_for_timeout(1500 + random.randint(0, 1000))
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(800 + random.randint(0, 500))

            # If no content selector found, wait a bit more for JS rendering
            if not found:
                page.wait_for_timeout(3000)

            html = page.content()
            browser.close()

            text = _extract_main_text(html, url=url)
            if text and len(text.strip()) > 200:
                if "robot" in text.lower() or "please click" in text.lower():
                    logger.warning(f"[browser] Verification page detected for {url}")
                    return None
                return text
            return None
    except Exception as e:
        logger.warning(f"[browser] {type(e).__name__}: {e}")
        return None

def fetch_search_snippet(url: str, search_func=None) -> str | None:
    if search_func is None:
        return None
    try:
        results = search_func(url)
        if not results:
            return None
        top = results[0]
        title = top.get("title", "")
        snippet = top.get("snippet", "")
        return f"# {title}\n\n{snippet}\n\n[搜索摘要兜底]"
    except Exception as e:
        logger.warning(f"[search_snippet] {e}")
        return None


# ── Jina Reader (轻量第三方 API 兜底) ──────────────────────────
# 免费 API: curl https://r.jina.ai/URL → markdown
# 专为 LLM 提取设计，自带 Cloudflare/反爬绕过能力
JINA_READER_BASE = os.environ.get("JINA_READER_BASE") or "https://r.jina.ai"

def fetch_jina_reader(url: str, rate_limiter: RateLimiter | None = None, timeout: float = 10.0) -> str | None:
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
    # Jina Reader via curl -4 (httpx SNI issue with raw IP on this network)
    reader_url = f"{JINA_READER_BASE}/{url}"
    try:
        import subprocess
        result = subprocess.run(
            ["curl", "-4", "-s", "--max-time", str(int(timeout)),
             reader_url, "-H", "Accept: text/plain, text/markdown, */*"],
            capture_output=True, text=True, timeout=timeout + 2)
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        if len(text) < 100:
            return None
        return text
    except Exception as e:
        logger.warning(f"[jina] {type(e).__name__}: {e}")
        return None


# ── Tavily (AI 摘要 API, 自带搜索+反爬绕过) ────────────────────
TAVILY_DEV_KEY = "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"

def fetch_tavily(url: str, rate_limiter: RateLimiter | None = None, timeout: float = 10.0) -> str | None:
    """Tavily search API via curl (httpx has SSL/SNI issues on this network)."""
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
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
    min_content_len: int = 200,
    search_func=None,
    llm_api_key: str | None = None,
    llm_prompt: str | None = None,
) -> dict:
    from config.domain_profiles import get_profile
    from core.temporal import validate_temporal

    profile = get_profile(url)
    order = force_strategy_order or list(profile.strategy_order)
    failing = set(profile.known_failing)
    if skip_expensive:
        failing.add("computer_use")   # 只移除 computer_use，保留 browser
    order = [s for s in order if s not in failing]

    cost_trace = []
    STRATEGY_FN = {
        "direct": lambda u: fetch_direct(u, rate_limiter),
        "archive": lambda u: fetch_archive(u, rate_limiter),
        "google_cache": lambda u: fetch_google_cache(u, rate_limiter),
        "scrapling": lambda u: fetch_scrapling(u, rate_limiter),
        "browser": lambda u: fetch_browser(u, rate_limiter),
        "jina": lambda u: fetch_jina_reader(u, rate_limiter),
        "tavily": lambda u: fetch_tavily(u, rate_limiter),
        "computer_use": lambda u: None,
        "search_snippet": lambda u: fetch_search_snippet(u, search_func),
    }
    COST = {"direct": 1, "archive": 1, "google_cache": 1, "search_snippet": 1,
            "scrapling": 2, "jina": 2, "tavily": 3, "browser": 3, "computer_use": 5}

    content = None
    strategy_used = None

    for strategy in order:
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
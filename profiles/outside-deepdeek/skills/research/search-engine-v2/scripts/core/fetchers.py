"""
core/fetchers.py — Real network implementations for every cascade strategy.

Replaces the Callable placeholders in HermesToolbox with actual Python code
that can run standalone — no Agent session needed.

Strategy → Implementation:
  direct         → httpx GET + trafilatura extract (cost=1)
  archive        → httpx GET web.archive.org + trafilatura (cost=1)
  scrapling      → Scrapling StealthyFetcher (cost=2, Cloudflare bypass)
  browser        → Playwright headless (cost=3, JS-rendered pages)
  search_snippet → search API + snippet extraction (cost=1)
  computer_use   → DISABLED in batch; only for manual trigger (cost=5)
  llm_extract    → DeepSeek API call + structured JSON extraction

All fetchers respect a RateLimiter for per-domain throttling.
"""

from __future__ import annotations
import re
import time
import json
import logging
from typing import Optional
from urllib.parse import urlparse
from dataclasses import dataclass, field

import httpx

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


# ── Rate Limiter (domain-aware token bucket) ───────────────────────
@dataclass
class RateLimiter:
    """Per-domain token bucket rate limiter for batch scraping.

    Thread-safe: all state access is protected by a threading.Lock.
    """

    default_delay: float = 1.0          # seconds between requests (same domain)
    domain_delays: dict = field(default_factory=dict)  # per-domain overrides
    _last_request: dict = field(default_factory=dict)  # domain → timestamp
    _lock: object = field(default_factory=__import__("threading").Lock)

    def set_domain_delay(self, domain: str, delay: float):
        """Override the delay for a specific domain (e.g. 0.5s for friendly sites)."""
        self.domain_delays[domain] = delay

    def wait(self, domain: str):
        """Block until the per-domain cooldown elapses. Thread-safe."""
        delay = self.domain_delays.get(domain, self.default_delay)
        with self._lock:
            last = self._last_request.get(domain, 0)
            now = time.monotonic()
            remaining = delay - (now - last)
        if remaining > 0:
            time.sleep(remaining)
        with self._lock:
            self._last_request[domain] = time.monotonic()

    def wait_for(self, key: str, delay: float):
        """Block on a named cooldown key (e.g. 'browser:domain.com'). Thread-safe."""
        with self._lock:
            last = self._last_request.get(key, 0)
            now = time.monotonic()
            remaining = delay - (now - last)
        if remaining > 0:
            time.sleep(remaining)
        with self._lock:
            self._last_request[key] = time.monotonic()


# ── Client Pool (domain-level client reuse) ────────────────────────

class DirectClientPool:
    """Domain-isolated httpx.Client pool for fetch_direct.

    Reuses Client per domain for cookie persistence.
    Thread-safe via lock. LRU eviction at max_domains.
    Does NOT apply to archive/google_cache/scrapling/browser.
    """

    def __init__(self, max_domains: int = 50):
        self._clients: dict[str, httpx.Client] = {}
        self._access: dict[str, float] = {}
        self._max = max_domains
        self._lock = __import__("threading").Lock()

    def get(self, url: str) -> httpx.Client:
        domain = self._extract_domain(url)
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


# Module-level singleton pool
_direct_client_pool = DirectClientPool(max_domains=50)


# ── Scrapling Pool (StealthyFetcher instance reuse) ──────────────────

class ScraplingPool:
    """Lazily-initialized singleton StealthyFetcher.

    Avoids per-URL cold start: StealthyFetcher() init (browser context,
    TLS fingerprint setup) happens once and is reused across calls.
    Thread-safe via lock.
    """

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


# ── Extraction helpers ─────────────────────────────────────────────
def _extract_main_text(html: str, url: str = "") -> str:
    """
    Extract main article text from HTML.
    Priority: trafilatura > readability-lxml > regex fallback.
    """
    if not html or len(html.strip()) < 50:
        return ""

    # 1. trafilatura (best quality, metadata-aware)
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

    # 2. readability-lxml
    if HAS_READABILITY:
        try:
            doc = ReadabilityDoc(html)
            title = doc.title() or ""
            content = doc.summary(html_partial=True)
            # Strip HTML tags from readability output
            content = re.sub(r"<[^>]+>", "", content)
            content = re.sub(r"\n{3,}", "\n\n", content)
            text = f"# {title}\n\n{content}" if title else content
            if text.strip():
                return text.strip()
        except Exception:
            pass

    # 3. Fallback: strip tags + blank-line normalization
    text = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── HTTP session factory ───────────────────────────────────────────

# 国内域名：直连，不走代理
_CHINESE_TLDS = {".cn", ".com.cn", ".org.cn", ".gov.cn", ".edu.cn", ".net.cn"}
_CHINESE_DOMAINS = {
    "people.com.cn", "xinhuanet.com", "cctv.com", "cctv.cn",
    "chinanews.com", "chinadaily.com.cn", "huanqiu.com",
    "yicai.com", "thepaper.cn", "caixin.com", "jiemian.com",
    "sina.com.cn", "sohu.com", "163.com", "qq.com",
    "china.com.cn", "gmw.cn", "youth.cn", "ce.cn",
}


def _is_chinese_domain(url: str) -> bool:
    """判断是否为国内域名，国内域名直连不走代理。"""
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()

    # TLD 后缀匹配
    if any(host.endswith(tld) for tld in _CHINESE_TLDS):
        return True
    # 精确域名匹配（不含 .cn 后缀的国内域名）
    if any(host == d or host.endswith("." + d) for d in _CHINESE_DOMAINS):
        return True
    return False


# ── Frozen Headers ────────────────────────────────────────────────

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
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
    """Create an httpx client with frozen browser headers and proxy awareness."""
    import os

    if timeout is None:
        timeout = httpx.Timeout(connect=5, read=15, write=10, pool=5)

    kwargs = {
        "headers": DEFAULT_HEADERS,
        "follow_redirects": True,
        "timeout": timeout,
    }

    if url and not _is_chinese_domain(url):
        proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
                 or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
        if proxy:
            kwargs["proxy"] = proxy

    return httpx.Client(**kwargs)


# ═══════════════════════════════════════════════════════════════════
# Strategy Implementations
# ═══════════════════════════════════════════════════════════════════

def fetch_direct(
    url: str,
    rate_limiter: RateLimiter | None = None,
) -> str | None:
    """Strategy: direct (cost=1). httpx GET + trafilatura extraction.

    Cookie persistence via reused Client. Retry on 408/429/5xx (NOT 403).
    Timeout controlled by _make_client() default (connect=5, read=15, write=10, pool=5).
    """
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
                    logger.info(f"[direct] {resp.status_code}, retry in {wait}s ({attempt+1}/{MAX_RETRIES})")
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
                    logger.info(f"[direct] {e.response.status_code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                logger.warning(f"[direct] HTTP {e.response.status_code} for {url}")
                return None
        return None
    except Exception as e:
        logger.warning(f"[direct] {type(e).__name__}: {e}")
        return None


def fetch_archive(
    url: str,
    rate_limiter: RateLimiter | None = None,
) -> str | None:
    """
    Strategy: archive (cost=1)
    Fetch from web.archive.org latest snapshot.
    Stable bypass for paywalled content (WSJ, Bloomberg, FT).
    """
    archive_url = f"https://web.archive.org/web/0/{url}"

    domain = "web.archive.org"
    if rate_limiter:
        rate_limiter.wait(domain)

    try:
        with _make_client(url=url) as client:
            resp = client.get(archive_url)
            resp.raise_for_status()
            html = resp.text

        # Check for Wayback Machine error page
        if "Wayback Machine doesn't have that page" in html or "not been archived" in html:
            logger.info(f"[archive] Not archived: {url}")
            return None

        text = _extract_main_text(html, url=url)
        if text:
            return f"[Archived from web.archive.org]\n\n{text}"
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"[archive] HTTP {e.response.status_code} for {url}")
        return None
    except Exception as e:
        logger.warning(f"[archive] {type(e).__name__}: {e}")
        return None


def fetch_google_cache(
    url: str,
    rate_limiter: RateLimiter | None = None,
) -> str | None:
    """
    Strategy: google_cache (cost=1)
    Fetch from Google's cached copy — highly effective for news articles.
    Most Bloomberg/WSJ articles appear in Google Cache within hours of publishing.
    """
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"

    domain = "webcache.googleusercontent.com"
    if rate_limiter:
        rate_limiter.wait(domain)

    try:
        with _make_client(url=url) as client:
            resp = client.get(cache_url)
            resp.raise_for_status()
            html = resp.text

        # Check for "page is not available" messages
        if "Page not available" in html or "404 Not Found" in html[:500]:
            logger.info(f"[google_cache] Not cached: {url}")
            return None

        text = _extract_main_text(html, url=url)
        if text:
            return f"[Google Cache]\n\n{text}"
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"[google_cache] HTTP {e.response.status_code} for {url}")
        return None
    except Exception as e:
        logger.warning(f"[google_cache] {type(e).__name__}: {e}")
        return None


def fetch_scrapling(
    url: str,
    rate_limiter: RateLimiter | None = None,
    timeout: float = 45.0,
) -> str | None:
    """Strategy: scrapling (cost=2)
    Scrapling StealthyFetcher — TLS fingerprint randomization + browserforge headers.
    Bypasses moderate Cloudflare protections.

    Uses a module-level singleton pool (ScraplingPool) to avoid per-URL
    cold-start cost of launching a browser context.
    """
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

        # Scrapling response: try .text first, then .content
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


def fetch_browser(
    url: str,
    rate_limiter: RateLimiter | None = None,
    timeout: float = 60.0,
) -> str | None:
    """Strategy: browser (cost=3)
    Playwright headless Chromium — for JS-rendered / SPA pages.
    Heaviest cost, use only when direct/scrapling both fail.

    Uses domcontentloaded (not networkidle) to avoid hanging forever
    on news sites with analytics/ads that never stop loading.
    """
    domain = urlparse(url).netloc
    if rate_limiter:
        rate_limiter.wait(domain)
        # Long cooldown for browser (expensive resource)
        rate_limiter.wait_for(f"browser:{domain}", delay=5.0)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, timeout=int(timeout * 1000))
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            # Wait for main article content if a selector pattern matches
            try:
                page.wait_for_selector("article, [role='main'], .article-body, .post-content",
                                       timeout=min(5000, int(timeout * 1000 * 0.3)))
            except Exception:
                pass  # no explicit article container found, use what we have
            html = page.content()
            browser.close()

        text = _extract_main_text(html, url=url)
        return text or None
    except ImportError:
        logger.warning("[browser] Playwright not installed; skipping")
        return None
    except Exception as e:
        logger.warning(f"[browser] {type(e).__name__}: {e}")
        return None


def fetch_search_snippet(
    url: str,
    search_func=None,  # Callable(query) → list[dict]
) -> str | None:
    """
    Strategy: search_snippet (cost=1)
    Search for the URL and return the snippet as a last-resort summary.
    Requires a search function to be injected (the only remaining external dependency).
    """
    if search_func is None:
        return None

    try:
        results = search_func(url)
        if not results:
            return None
        top = results[0]
        title = top.get("title", "")
        snippet = top.get("snippet", "")
        return f"# {title}\n\n{snippet}\n\n[注意：此为搜索摘要兜底，非完整正文]"
    except Exception as e:
        logger.warning(f"[search_snippet] {e}")
        return None


# ── LLM Structured Extraction ──────────────────────────────────────

def llm_extract_structured(
    content: str,
    prompt: str,
    api_key: str | None = None,
    api_base: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-chat",
    max_chars: int = 8000,
) -> dict | list | None:
    """
    Use DeepSeek API to extract structured JSON from article content.
    One LLM call per article; results should be cached by the caller.

    Args:
        content: markdown article text
        prompt: extraction prompt (JSON schema instructions)
        api_key: DeepSeek API key (defaults to DEEPSEEK_API_KEY env var)
        api_base: API base URL
        model: model name
        max_chars: truncate content to this length before sending

    Returns:
        Parsed JSON (dict or list) or None on failure.
    """
    import os

    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("[llm_extract] No API key configured")
        return None

    truncated = content[:max_chars]

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是一个精确的数据提取助手。只输出 JSON，不要其他内容。"},
                        {"role": "user", "content": f"{prompt}\n\n--- 内容 ---\n{truncated}"},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # Extract JSON from markdown code blocks if present
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if json_match:
                raw = json_match.group(1).strip()

            return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"[llm_extract] Invalid JSON response: {raw[:200]}")
        return None
    except Exception as e:
        logger.warning(f"[llm_extract] {type(e).__name__}: {e}")
        return None


# ── Batch convenience ──────────────────────────────────────────────

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
    """One-shot: extract a single URL with cascade + optional LLM structuring.

    Returns a dict compatible with SkillResult shape:
      {ok, url, domain, content, strategy_used, total_cost, cost_trace, structured?, temporal_check?}
    """
    from config.domain_profiles import get_profile
    from core.temporal import validate_temporal

    profile = get_profile(url)
    order = force_strategy_order or list(profile.strategy_order)
    failing = set(profile.known_failing)
    if skip_expensive:
        failing |= {"computer_use", "browser"}
    order = [s for s in order if s not in failing]

    cost_trace = []
    STRATEGY_FN = {
        "direct": lambda u: fetch_direct(u, rate_limiter),
        "archive": lambda u: fetch_archive(u, rate_limiter),
        "google_cache": lambda u: fetch_google_cache(u, rate_limiter),
        "scrapling": lambda u: fetch_scrapling(u, rate_limiter),
        "browser": lambda u: fetch_browser(u, rate_limiter),
        "computer_use": lambda u: None,  # disabled by default
        "search_snippet": lambda u: fetch_search_snippet(u, search_func),
    }
    COST = {"direct": 1, "archive": 1, "google_cache": 1, "search_snippet": 1, "scrapling": 2, "browser": 3, "computer_use": 5}

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

    # Structured extraction: 默认走纯脚本规则引擎（零LLM），--llm-extract 时才调DeepSeek
    structured = None
    from core.extractor import extract_structured

    if llm_api_key and llm_prompt:
        structured = llm_extract_structured(content, llm_prompt, api_key=llm_api_key)
    else:
        structured = extract_structured(url, content)

    # Temporal validation
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

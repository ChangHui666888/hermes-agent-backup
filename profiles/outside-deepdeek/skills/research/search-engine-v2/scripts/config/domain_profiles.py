"""config/domain_profiles.py — 域名画像知识库

核心设计思路：
  不让每个URL都跑一遍"完整降级链路"，而是先查表。
  命中已知域名画像后，直接给出"最优策略顺序"，
  提前跳过"明知会失败"的工具，不做无用调用。

数据来源：Hermes 工具文档《WSJ 场景各工具对比》实测结论：
  - web_extract 直连：WSJ主页面✅偶尔 / 子卡片❌DataDome
  - archive.org：WSJ ✅稳定
  - browser_navigate：WSJ ❌DataDome
  - scrapling：WSJ ❌401
  - computer_use：WSJ ✅ (贵，终极兜底)

2026-07-16 实测更新：
  - bloomberg.com: direct/google_cache/archive 均失败 (403/429/404)，仅 browser 策略 (Playwright) 可稳定获取全文
  - 因此将 bloomberg.com 的 strategy_order 改为 ["browser", "archive", "google_cache", "search_snippet"]
  - 同时移除 known_failing 中的 "browser"
  - wsj.com, ft.com 也同步调整为 browser 优先（若后续发现 google_cache 仍有效，可再调整）
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DomainProfile:
    domain: str
    anti_bot: str                    # none | datadome | cloudflare | unknown
    strategy_order: List[str]        # 按优先级排列，命中即停
    paywall: bool = False
    is_live_blog_domain: bool = False  # 该域名常有直播流页面
    notes: str = ""
    known_failing: List[str] = field(default_factory=list)


KNOWN_PROFILES: dict[str, DomainProfile] = {

    # ── 强反爬 / 付费墙（需浏览器策略）──────────────────────────────
    "wsj.com": DomainProfile(
        domain="wsj.com",
        anti_bot="datadome",
        paywall=True,
        is_live_blog_domain=True,
        strategy_order=["browser", "archive", "google_cache", "search_snippet"],
        known_failing=["scrapling"],
        notes="DataDome防护。direct/google_cache/archive 部分可达，但 browser 最稳定；scrapling 必败",
    ),
    "bloomberg.com": DomainProfile(
        domain="bloomberg.com",
        anti_bot="datadome",
        paywall=True,
        strategy_order=["archive", "google_cache", "jina", "tavily", "search_snippet"],
        known_failing=["direct", "scrapling", "browser"],
        notes="2026-07-28 实测：browser 30s timeout 不够；direct 401；archive/jina/tavily 取代 browser 策略",
    ),

    # ── BBC（大量待抓取，scrapling/browser 均不可用）───────────────────
    "bbc.co.uk": DomainProfile(
        domain="bbc.co.uk",
        anti_bot="cloudflare",
        is_live_blog_domain=True,
        strategy_order=["direct", "jina", "tavily", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="2026-07-28 实测：direct 有时超时(SSL)，跳过 scrapling(挂起)和 browser(被检测)，jina/tavily 兜底",
    ),

    # ── DW（无特殊反爬但 scrapling 挂起）──────────────────────
    "dw.com": DomainProfile(
        domain="dw.com",
        anti_bot="none",
        strategy_order=["direct", "archive", "google_cache", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="DW 直连友好，跳过 scrapling/browser 避免挂起",
    ),
    "ft.com": DomainProfile(
        domain="ft.com",
        anti_bot="datadome",
        paywall=True,
        strategy_order=["browser", "archive", "google_cache", "search_snippet"],
        known_failing=["scrapling"],
        notes="FT付费墙。browser 最可靠，archive 次之。",
    ),

    # ── 中等反爬（Cloudflare/轻度防护）──────────────────────────────
    "cnbc.com": DomainProfile(
        domain="cnbc.com",
        anti_bot="cloudflare",
        strategy_order=["direct", "scrapling", "archive", "search_snippet"],
        notes="Cloudflare防护，Scrapling StealthyFetcher一般可绕过",
    ),
    "businessinsider.com": DomainProfile(
        domain="businessinsider.com",
        anti_bot="cloudflare",
        strategy_order=["direct", "scrapling", "archive", "search_snippet"],
        notes="Cloudflare防护",
    ),

    "investing.com": DomainProfile(
    domain="investing.com",
    anti_bot="cloudflare",
    strategy_order=["browser", "jina", "tavily", "search_snippet"],
    known_failing=["scrapling", "direct", "google_cache", "archive"],
    notes="Cloudflare强防护。browser 约50%成功率；direct/google_cache/archive 已知全部失败(403/429/404)，跳过直接走 jina/tavily",
    ),

    "investors.com": DomainProfile(
        domain="investors.com",
        anti_bot="cloudflare",
        strategy_order=["direct", "google_cache", "archive", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="Investor's Business Daily — 同investing.com级别Cloudflare。浏览器可访问但headless被检测→load事件永不触发→45s超时",
    ),

    "seekingalpha.com": DomainProfile(
        domain="seekingalpha.com",
        anti_bot="cloudflare",
        strategy_order=["direct", "google_cache", "archive", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="Seeking Alpha — Cloudflare+反爬。direct/archive/scrapling/search_snippet全失败。靠RSS描述+SearXNG恢复",
    ),

    # ── 新增：付费墙/强反爬站点（browser 策略已验证）──────────────────
    "reuters.com": DomainProfile(
        domain="reuters.com",
        anti_bot="datadome",
        paywall=True,
        strategy_order=["archive", "google_cache", "jina", "tavily", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="2026-07-27 实测: direct 401, browser Target crashed, archive 可兜底(老快照), jina/tavily 第三方兜底",
    ),
    "marketwatch.com": DomainProfile(
        domain="marketwatch.com",
        anti_bot="datadome",
        strategy_order=["direct", "archive", "google_cache", "jina", "tavily", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="2026-07-27 实测: direct 401, browser Target crashed, archive 404, google_cache 空页, jina/tavily 第三方兜底",
    ),

    # ── 无反爬 / 友好域名 ────────────────────────────────────────────
    "apnews.com": DomainProfile(
        domain="apnews.com",
        anti_bot="none",
        strategy_order=["direct"],
        notes="AP News 友好直连",
    ),
    "newsweek.com": DomainProfile(
        domain="newsweek.com",
        anti_bot="none",
        strategy_order=["direct", "archive", "search_snippet"],
        notes="Newsweek 无反爬，直连可达。2026-07-01 实测验证: July 4文章 direct✅成功(cost=1)",
    ),
    "aljazeera.com": DomainProfile(
        domain="aljazeera.com",
        anti_bot="none",
        strategy_order=["direct"],
        notes="Al Jazeera 友好直连",
    ),
    "theguardian.com": DomainProfile(
        domain="theguardian.com",
        anti_bot="none",
        strategy_order=["direct"],
        notes="The Guardian 友好直连",
    ),
    "bbc.com": DomainProfile(
        domain="bbc.com",
        anti_bot="none",
        is_live_blog_domain=True,
        strategy_order=["direct"],
        notes="BBC 友好直连",
    ),
    "bbc.co.uk": DomainProfile(
        domain="bbc.co.uk",
        anti_bot="none",
        is_live_blog_domain=True,
        strategy_order=["direct"],
        notes="BBC (英国域名)，友好直连",
    ),
    "cnn.com": DomainProfile(
        domain="cnn.com",
        anti_bot="none",
        strategy_order=["direct"],
        notes="CNN 友好直连",
    ),
    "arxiv.org": DomainProfile(
        domain="arxiv.org",
        anti_bot="none",
        strategy_order=["direct"],
        notes="Hermes web_extract 对 arxiv 有原生支持",
    ),

    # ── 付费墙但轻度反爬 ────────────────────────────────────────────
    "nytimes.com": DomainProfile(
        domain="nytimes.com",
        anti_bot="soft_paywall",
        paywall=True,
        strategy_order=["direct", "archive", "search_snippet"],
        notes="NYT软付费墙，direct偶尔可达",
    ),
    "washingtonpost.com": DomainProfile(
        domain="washingtonpost.com",
        anti_bot="soft_paywall",
        paywall=True,
        strategy_order=["direct", "archive", "search_snippet"],
        notes="WaPo软付费墙",
    ),
}

DEFAULT_STRATEGY_ORDER = [
    "direct",         # cost=1 ⚡  最便宜，先试
    "archive",        # cost=1 ⚡  同样便宜，常见于内容已下线
    "google_cache",   # cost=1 ⚡  搜索引擎缓存
    "jina",           # cost=2 🔶  第三方API，自带反爬绕过
    "tavily",         # cost=3 🔶  AI 搜索摘要，高价值兜底
    "search_snippet", # cost=1 ⚡  彻底兜底，拿摘要总比空手强
]


def get_profile(url: str) -> DomainProfile:
    """按 url 字符串匹配域名画像，未命中返回通用默认"""
    for domain, profile in KNOWN_PROFILES.items():
        if domain in url:
            return profile
    return DomainProfile(
        domain="*",
        anti_bot="unknown",
        strategy_order=list(DEFAULT_STRATEGY_ORDER),
        notes="未知域名，按通用成本梯度尝试",
    )
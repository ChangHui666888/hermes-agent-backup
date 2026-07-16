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

    # ── 强反爬 / 付费墙 ──────────────────────────────────────────────
    "wsj.com": DomainProfile(
        domain="wsj.com",
        anti_bot="datadome",
        paywall=True,
        is_live_blog_domain=True,
        strategy_order=["direct", "google_cache", "archive", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="DataDome防护。direct偶尔可达；google_cache覆盖大部分新闻；archive稳定全文路径；browser/scrapling必败",
    ),
    "bloomberg.com": DomainProfile(
        domain="bloomberg.com",
        anti_bot="datadome",
        paywall=True,
        strategy_order=["direct", "google_cache", "archive", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="同WSJ量级。google_cache是今日新闻最佳捷径（发表后数小时即可命中）",
    ),
    "ft.com": DomainProfile(
        domain="ft.com",
        anti_bot="datadome",
        paywall=True,
        strategy_order=["direct", "google_cache", "archive", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="FT付费墙。google_cache覆盖高",
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
        strategy_order=["direct", "google_cache", "archive", "search_snippet"],
        known_failing=["scrapling", "browser"],
        notes="Cloudflare强防护。direct返回403；scrapling超时(45s×3)。用archive+search_snippet兜底",
    ),

    # ── 无反爬 / 友好域名 ────────────────────────────────────────────
    "reuters.com": DomainProfile(
        domain="reuters.com",
        anti_bot="none",
        is_live_blog_domain=True,
        strategy_order=["direct"],
        notes="直连基本100%成功，无需兜底",
    ),
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
    "scrapling",      # cost=2 🔶  Cloudflare等中等防护
    "browser",        # cost=3 🔴  需JS渲染/表单交互
    "computer_use",   # cost=5 💀  终极兜底，模拟真人，贵
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
